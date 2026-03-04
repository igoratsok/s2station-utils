import sys
import re
import math
from datetime import timedelta, datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                             QTableWidget, QTableWidgetItem, QHeaderView, 
                             QSpinBox, QMessageBox, QFrame, QSplitter)
from PyQt6.QtCore import Qt, QMimeData
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QFont

# --- Lógica de Manipulação de SRT ---

class SubtitleItem:
    def __init__(self, index, start, end, text):
        self.index = index
        self.start = start  # timedelta
        self.end = end      # timedelta
        self.text = text

    def duration(self):
        return self.end - self.start

    def __repr__(self):
        return f"{self.index} [{self.start} -> {self.end}]: {self.text}"

class SRTProcessor:
    def __init__(self):
        self.subtitles = []

    def parse_time(self, time_str):
        # Formato: 00:00:00,000
        time_str = time_str.replace(',', '.')
        try:
            t = datetime.strptime(time_str, "%H:%M:%S.%f")
            return timedelta(hours=t.hour, minutes=t.minute, seconds=t.second, microseconds=t.microsecond)
        except ValueError:
            return timedelta(0)

    def format_time(self, td):
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        microseconds = td.microseconds
        return f"{hours:02}:{minutes:02}:{seconds:02},{microseconds // 1000:03}"

    def load_from_file(self, filepath):
        self.subtitles = []
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Regex para capturar blocos de legenda
        pattern = re.compile(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n((?:.|\n)*?)(?=\n\d+\n|\Z)', re.MULTILINE)
        matches = pattern.findall(content)

        for match in matches:
            idx = int(match[0])
            start = self.parse_time(match[1])
            end = self.parse_time(match[2])
            text = match[3].strip()
            self.subtitles.append(SubtitleItem(idx, start, end, text))

    def save_to_file(self, filepath, subtitles):
        with open(filepath, 'w', encoding='utf-8') as f:
            for i, sub in enumerate(subtitles):
                f.write(f"{i + 1}\n")
                f.write(f"{self.format_time(sub.start)} --> {self.format_time(sub.end)}\n")
                f.write(f"{sub.text}\n\n")

    def split_subtitles(self, max_chars=40):
        new_subs = []
        
        for sub in self.subtitles:
            # Remove quebras de linha existentes para reprocessar
            clean_text = sub.text.replace('\n', ' ')
            
            # Se for curto o suficiente, mantém
            if len(clean_text) <= max_chars:
                new_subs.append(sub)
                continue

            # Processamento de divisão recursiva
            self._recursive_split(sub.start, sub.end, clean_text, max_chars, new_subs)
        
        # Reordenar índices
        for i, sub in enumerate(new_subs):
            sub.index = i + 1
            
        return new_subs

    def _recursive_split(self, start_time, end_time, text, max_chars, result_list):
        if len(text) <= max_chars:
            result_list.append(SubtitleItem(0, start_time, end_time, text))
            return

        # Encontrar o melhor ponto de corte
        split_idx = self._find_best_split_index(text)
        
        # Se não achou um ponto bom (texto muito denso sem espaços), corta no meio
        if split_idx == -1 or split_idx == 0 or split_idx == len(text):
            split_idx = len(text) // 2

        part1_text = text[:split_idx].strip()
        part2_text = text[split_idx:].strip()

        # Calcular tempo proporcional
        total_len = len(text)
        len1 = len(part1_text)
        
        total_duration = (end_time - start_time).total_seconds()
        
        # Evitar divisão por zero ou bugs de arredondamento
        if total_len == 0: ratio = 0.5
        else: ratio = len1 / total_len

        duration1 = total_duration * ratio
        
        mid_time = start_time + timedelta(seconds=duration1)

        # Recursão para garantir que as partes resultantes respeitem o limite
        self._recursive_split(start_time, mid_time, part1_text, max_chars, result_list)
        self._recursive_split(mid_time, end_time, part2_text, max_chars, result_list)

    def _find_best_split_index(self, text):
        # Tenta dividir ao meio, mas buscando pontuação próxima
        mid = len(text) // 2
        best_idx = -1
        min_dist = float('inf') # Começa infinito para garantir que pegamos o primeiro

        # Regex para encontrar posições de pontuação
        punctuations = [
            (r'[.?!]\s', 1.0), # Peso Baixo = Bom (prioriza pontos finais)
            (r'[,;:]\s', 1.5), # Peso Médio (prioriza vírgulas)
            (r'\s', 3.0)       # Peso Alto (só espaço, última opção)
        ]
        
        # Conectores comuns em nomes próprios (Torres del Paine, Rio de Janeiro, Statue of Liberty)
        connectors = {'of', 'the', 'del', 'da', 'de', 'do', 'in', 'on', 'at', 'e', 'and'}

        for pattern_str, penalty_weight in punctuations:
            for match in re.finditer(pattern_str, text):
                idx = match.end() # O corte acontece APÓS o match (ex: ". " -> corta depois do espaço)
                
                # Distância básica do centro
                dist = abs(idx - mid) * penalty_weight
                
                # --- NOVA LÓGICA DE PROTEÇÃO DE MAIÚSCULAS ---
                # Se estivermos cortando apenas num espaço (ou vírgula), vamos ver as palavras ao redor.
                # Não aplicamos isso para Ponto Final (.?!) pois lá DEVE quebrar mesmo.
                is_strong_punctuation = '.' in pattern_str or '?' in pattern_str or '!' in pattern_str
                
                if not is_strong_punctuation:
                    # O match.start() é o início do espaço/pontuação. O idx é o fim.
                    # Texto à esquerda termina em match.start()
                    left_context = text[:match.start()]
                    # Texto à direita começa em idx
                    right_context = text[idx:]
                    
                    # Pega a palavra imediatamente antes do corte e a imediatamente depois
                    match_before = re.search(r'(\w+)[^\w]*$', left_context)
                    match_after = re.search(r'^[^\w]*(\w+)', right_context)
                    
                    if match_before and match_after:
                        word_before = match_before.group(1)
                        word_after = match_after.group(1)
                        
                        # Regra 1: Maiúscula | Maiúscula (Ex: National | Park) -> EVITAR
                        if word_before[0].isupper() and word_after[0].isupper():
                            dist *= 8.0 # Penalidade muito alta
                            
                        # Regra 2: Conector no meio de maiúsculas (Ex: Torres | del | Paine)
                        # Caso A: Maiúscula | Conector (Torres | del)
                        elif word_before[0].isupper() and word_after.lower() in connectors:
                             dist *= 5.0 # Penalidade alta
                        
                        # Caso B: Conector | Maiúscula (del | Paine)
                        elif word_before.lower() in connectors and word_after[0].isupper():
                             dist *= 5.0 # Penalidade alta

                # Queremos o menor 'custo' (distância ajustada)
                if dist < min_dist:
                    min_dist = dist
                    best_idx = idx
            
            # Otimização: Se achamos um corte perfeito (pontuação perto do meio), paramos
            # Se a penalidade for baixa e a distância real for pequena
            if best_idx != -1 and min_dist < (len(text) * 0.2):
                break
        
        return best_idx


# --- Interface Gráfica (PyQt6) ---

class ModernStyle:
    STYLESHEET = """
    QMainWindow {
        background-color: #1e1e1e;
    }
    QWidget {
        color: #e0e0e0;
        font-family: 'Segoe UI', 'Roboto', sans-serif;
        font-size: 14px;
    }
    QFrame#Container {
        background-color: #2d2d2d;
        border-radius: 10px;
        border: 1px solid #3d3d3d;
    }
    QPushButton {
        background-color: #0078d4;
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 5px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #1084d9;
    }
    QPushButton:pressed {
        background-color: #006cc1;
    }
    QPushButton#Secondary {
        background-color: #3d3d3d;
        border: 1px solid #555;
    }
    QPushButton#Secondary:hover {
        background-color: #4d4d4d;
    }
    QTableWidget {
        background-color: #252526;
        gridline-color: #3d3d3d;
        border: none;
        selection-background-color: #0078d4;
    }
    QHeaderView::section {
        background-color: #333333;
        padding: 4px;
        border: 1px solid #3d3d3d;
        font-weight: bold;
    }
    QSpinBox {
        background-color: #3d3d3d;
        border: 1px solid #555;
        border-radius: 4px;
        padding: 4px;
        color: white;
    }
    QLabel#Title {
        font-size: 18px;
        font-weight: bold;
        color: #ffffff;
    }
    """

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SRT Smart Splitter")
        self.resize(1000, 700)
        self.setAcceptDrops(True)
        
        self.processor = SRTProcessor()
        self.processed_subs = []
        self.current_file = None

        self.init_ui()
        self.setStyleSheet(ModernStyle.STYLESHEET)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("SRT Smart Splitter")
        title.setObjectName("Title")
        header_layout.addWidget(title)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Controls Area
        controls_frame = QFrame()
        controls_frame.setObjectName("Container")
        controls_layout = QHBoxLayout(controls_frame)
        
        self.btn_load = QPushButton("Abrir SRT")
        self.btn_load.setIcon(QIcon.fromTheme("document-open"))
        self.btn_load.clicked.connect(self.load_file_dialog)
        
        self.lbl_chars = QLabel("Máx. Caracteres:")
        self.spin_chars = QSpinBox()
        self.spin_chars.setRange(10, 200)
        self.spin_chars.setValue(45) # Valor padrão razoável
        
        self.btn_process = QPushButton("Processar / Dividir")
        self.btn_process.clicked.connect(self.process_subtitles)
        self.btn_process.setEnabled(False)
        
        self.btn_save = QPushButton("Salvar Novo SRT")
        self.btn_save.setObjectName("Secondary")
        self.btn_save.clicked.connect(self.save_file)
        self.btn_save.setEnabled(False)

        controls_layout.addWidget(self.btn_load)
        controls_layout.addSpacing(20)
        controls_layout.addWidget(self.lbl_chars)
        controls_layout.addWidget(self.spin_chars)
        controls_layout.addWidget(self.btn_process)
        controls_layout.addStretch()
        controls_layout.addWidget(self.btn_save)
        
        main_layout.addWidget(controls_frame)

        # Preview Area (Splitter for Before/After)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left Table (Original)
        self.table_orig = self.create_table("Original")
        # Right Table (Processed)
        self.table_new = self.create_table("Processado")
        
        splitter.addWidget(self.wrap_table(self.table_orig, "Original"))
        splitter.addWidget(self.wrap_table(self.table_new, "Resultado (Dividido)"))
        splitter.setSizes([500, 500])
        
        main_layout.addWidget(splitter)
        
        # Status Bar
        self.status_label = QLabel("Arraste um arquivo .srt aqui ou clique em Abrir.")
        self.status_label.setStyleSheet("color: #888;")
        main_layout.addWidget(self.status_label)

    def create_table(self, title):
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Tempo", "Duração", "Texto"])
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        return table

    def wrap_table(self, table, title_text):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0,0,0,0)
        lbl = QLabel(title_text)
        lbl.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        layout.addWidget(lbl)
        layout.addWidget(table)
        return widget

    def load_file_dialog(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Abrir Legenda", "", "SRT Files (*.srt)")
        if fname:
            self.load_file(fname)

    def load_file(self, filepath):
        try:
            self.processor.load_from_file(filepath)
            self.current_file = filepath
            self.status_label.setText(f"Arquivo carregado: {filepath}")
            self.populate_table(self.table_orig, self.processor.subtitles)
            self.table_new.setRowCount(0)
            self.btn_process.setEnabled(True)
            self.btn_save.setEnabled(False)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao ler arquivo: {str(e)}")

    def process_subtitles(self):
        max_chars = self.spin_chars.value()
        self.processed_subs = self.processor.split_subtitles(max_chars=max_chars)
        self.populate_table(self.table_new, self.processed_subs)
        self.btn_save.setEnabled(True)
        self.status_label.setText(f"Processado! Linhas originais: {len(self.processor.subtitles)} -> Novas linhas: {len(self.processed_subs)}")

    def populate_table(self, table, subtitles):
        table.setRowCount(len(subtitles))
        for row, sub in enumerate(subtitles):
            time_str = f"{self.processor.format_time(sub.start)} -> {self.processor.format_time(sub.end)}"
            dur_str = f"{sub.duration().total_seconds():.2f}s"
            
            table.setItem(row, 0, QTableWidgetItem(time_str))
            table.setItem(row, 1, QTableWidgetItem(dur_str))
            table.setItem(row, 2, QTableWidgetItem(sub.text.replace('\n', ' ')))

    def save_file(self):
        if not self.processed_subs:
            return
        
        fname, _ = QFileDialog.getSaveFileName(self, "Salvar Legenda", self.current_file.replace(".srt", "_split.srt"), "SRT Files (*.srt)")
        if fname:
            try:
                self.processor.save_to_file(fname, self.processed_subs)
                QMessageBox.information(self, "Sucesso", "Arquivo salvo com sucesso!")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao salvar: {str(e)}")

    # Drag and Drop Support
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        for f in files:
            if f.endswith('.srt'):
                self.load_file(f)
                break

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())