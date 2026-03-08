import sys
import os
import time
import subprocess
import traceback
import ssl
import re
from datetime import timedelta, datetime
import whisper

# --- CORREÇÃO DE SSL PARA MACOS ---
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context
# ----------------------------------

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QMimeData
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor, QAction, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFileDialog, QWidget, QComboBox, QSpinBox, QProgressBar, QFrame, 
    QMessageBox, QGraphicsDropShadowEffect, QSizePolicy, QScrollArea
)

# --- CONFIGURAÇÃO DE ESTILO (CSS MODERN) ---
MODERN_STYLESHEET = """
    QMainWindow { background-color: #121212; }
    QWidget { color: #E0E0E0; font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 14px; }
    QFrame#Card { background-color: #1E1E1E; border-radius: 12px; border: 1px solid #333333; }
    QFrame#DropZone { background-color: #252526; border: 2px dashed #444444; border-radius: 12px; }
    QFrame#DropZone:hover { background-color: #2D2D30; border-color: #0078D4; border-style: solid; }
    QLabel#Title { font-size: 18px; font-weight: bold; color: #FFFFFF; }
    QComboBox { background-color: #2D2D2D; border: 1px solid #3E3E3E; border-radius: 6px; padding: 5px 10px; min-width: 100px; }
    QComboBox::drop-down { border: 0px; }
    QSpinBox { background-color: #2D2D2D; border: 1px solid #3E3E3E; border-radius: 6px; padding: 5px 10px; }
    QSpinBox:disabled { background-color: #202020; color: #555555; border-color: #252525; }
    QSpinBox::up-button, QSpinBox::down-button { background-color: #383838; width: 20px; margin: 1px; border-radius: 2px; }
    QSpinBox::up-button:hover, QSpinBox::down-button:hover { background-color: #505050; }
    QPushButton { background-color: #333333; border: 1px solid #3E3E3E; border-radius: 6px; padding: 10px 20px; font-weight: 600; }
    QPushButton:hover { background-color: #444444; }
    QPushButton#PrimaryButton { background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #0078D4, stop:1 #005A9E); border: none; color: white; }
    QPushButton#PrimaryButton:hover { background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #1084E3, stop:1 #0066B4); }
    QPushButton#PrimaryButton:disabled { background-color: #2C2C2C; color: #555555; }
    QPushButton#DangerButton { background-color: #C42B1C; border: none; }
    QPushButton#DangerButton:hover { background-color: #B00020; }
    QProgressBar { border: none; background-color: #2D2D2D; border-radius: 4px; height: 8px; text-align: center; }
    QProgressBar::chunk { background-color: #0078D4; border-radius: 4px; }
"""

# --- LÓGICA INTELIGENTE DE SRT ---
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

    def format_time(self, td):
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        microseconds = td.microseconds
        return f"{hours:02}:{minutes:02}:{seconds:02},{microseconds // 1000:03}"

    def save_to_file(self, filepath, subtitles):
        with open(filepath, 'w', encoding='utf-8') as f:
            for i, sub in enumerate(subtitles):
                f.write(f"{i + 1}\n")
                f.write(f"{self.format_time(sub.start)} --> {self.format_time(sub.end)}\n")
                f.write(f"{sub.text}\n\n")

    def split_subtitles(self, max_chars=40):
        new_subs = []
        
        # Regex para encontrar espaços que vêm logo antes de um número seguido de ponto (Ex: " 1. ", " 2. ")
        # (?<=\S)   -> Garante que há algo antes do espaço (não está no início da string)
        # \s+       -> O espaço em si onde o corte vai acontecer
        # (?=\d+\.\s) -> Garante que logo após o espaço vem um número, um ponto e outro espaço
        list_pattern = re.compile(r'(?<=\S)\s+(?=\d+\.\s)')

        for sub in self.subtitles:
            clean_text = sub.text.replace('\n', ' ')
            
            # --- PASSO 1: Força o corte antes de itens numerados ---
            parts = list_pattern.split(clean_text)
            
            total_len = len(clean_text)
            total_duration = (sub.end - sub.start).total_seconds()
            current_start = sub.start
            
            for i, part in enumerate(parts):
                part = part.strip()
                if not part:
                    continue
                    
                # Calcula o tempo proporcional apenas desta parte do texto
                ratio = len(part) / total_len if total_len > 0 else 0
                part_duration = total_duration * ratio
                
                if i == len(parts) - 1:
                    current_end = sub.end # Garante que a última parte pega o final exato do tempo
                else:
                    current_end = current_start + timedelta(seconds=part_duration)
                    
                # --- PASSO 2: Aplica a lógica de tamanho/inteligente na parte já separada ---
                if len(part) <= max_chars:
                    new_subs.append(SubtitleItem(0, current_start, current_end, part))
                else:
                    self._recursive_split(current_start, current_end, part, max_chars, new_subs)
                    
                # Atualiza o tempo inicial para o próximo bloco
                current_start = current_end
        
        # Reordena os índices da legenda no final
        for i, sub in enumerate(new_subs):
            sub.index = i + 1
            
        return new_subs

    def _recursive_split(self, start_time, end_time, text, max_chars, result_list):
        if len(text) <= max_chars:
            result_list.append(SubtitleItem(0, start_time, end_time, text))
            return

        split_idx = self._find_best_split_index(text)
        if split_idx == -1 or split_idx == 0 or split_idx == len(text):
            split_idx = len(text) // 2

        part1_text = text[:split_idx].strip()
        part2_text = text[split_idx:].strip()

        total_len = len(text)
        len1 = len(part1_text)
        total_duration = (end_time - start_time).total_seconds()
        
        ratio = len1 / total_len if total_len > 0 else 0.5
        duration1 = total_duration * ratio
        mid_time = start_time + timedelta(seconds=duration1)

        self._recursive_split(start_time, mid_time, part1_text, max_chars, result_list)
        self._recursive_split(mid_time, end_time, part2_text, max_chars, result_list)

    def _find_best_split_index(self, text):
        mid = len(text) // 2
        best_idx = -1
        min_dist = float('inf')

        punctuations = [
            (r'[.?!]\s', 1.0),
            (r'[,;:]\s', 1.5),
            (r'\s', 3.0)
        ]
        connectors = {'of', 'the', 'del', 'da', 'de', 'do', 'in', 'on', 'at', 'e', 'and'}

        for pattern_str, penalty_weight in punctuations:
            for match in re.finditer(pattern_str, text):
                idx = match.end()
                dist = abs(idx - mid) * penalty_weight
                is_strong_punctuation = '.' in pattern_str or '?' in pattern_str or '!' in pattern_str
                
                if not is_strong_punctuation:
                    left_context = text[:match.start()]
                    right_context = text[idx:]
                    match_before = re.search(r'(\w+)[^\w]*$', left_context)
                    match_after = re.search(r'^[^\w]*(\w+)', right_context)
                    
                    if match_before and match_after:
                        word_before = match_before.group(1)
                        word_after = match_after.group(1)
                        if word_before[0].isupper() and word_after[0].isupper():
                            dist *= 8.0
                        elif word_before[0].isupper() and word_after.lower() in connectors:
                             dist *= 5.0
                        elif word_before.lower() in connectors and word_after[0].isupper():
                             dist *= 5.0

                if dist < min_dist:
                    min_dist = dist
                    best_idx = idx
            
            if best_idx != -1 and min_dist < (len(text) * 0.2):
                break
        
        return best_idx


# --- WORKER THREAD ---
class TranscriptionWorker(QThread):
    status_update = pyqtSignal(str)
    progress_update = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._is_running = True

    def run(self):
        try:
            self.status_update.emit(f"🚀 Carregando modelo Whisper '{self.config['model']}'...")
            self.progress_update.emit(5)
            
            try:
                model = whisper.load_model(self.config['model'])
            except Exception as e:
                self.finished.emit(False, f"Erro ao carregar modelo.\n{str(e)}")
                return

            if not self._is_running: return

            self.status_update.emit("🎙️ Transcrevendo áudio... (Aguarde)")
            result = model.transcribe(self.config['file_path'], word_timestamps=True)
            
            if not self._is_running: return

            self.status_update.emit("📝 Processando legendas...")
            self.progress_update.emit(80)
            
            self._generate_srt(result, self.config['srt_path'])

            if not self._is_running: return

            if self.config['generate_video']:
                self.status_update.emit("🎬 Renderizando vídeo com FFmpeg...")
                self.progress_update.emit(90)
                self._render_video()
            
            self.progress_update.emit(100)
            msg = f"Processo concluído!\nSRT salvo em: {os.path.basename(self.config['srt_path'])}"
            self.finished.emit(True, msg)

        except Exception as e:
            traceback.print_exc()
            self.finished.emit(False, f"Erro inesperado: {str(e)}")

    def _generate_srt(self, result, path):
        is_phrase_mode = self.config['subtitle_type'] == "Frases Inteligentes"
        
        if is_phrase_mode:
            # Usa a lógica avançada do SRTProcessor
            processor = SRTProcessor()
            for i, segment in enumerate(result.get('segments', [])):
                start = timedelta(seconds=segment['start'])
                end = timedelta(seconds=segment['end'])
                text = segment['text'].strip()
                processor.subtitles.append(SubtitleItem(i+1, start, end, text))
            
            processed_subs = processor.split_subtitles(max_chars=self.config['max_chars'])
            processor.save_to_file(path, processed_subs)
            
        else:
            # Lógica simples Palavra por Palavra (Mantendo word_timestamps exatos)
            with open(path, "w", encoding='utf-8') as f:
                counter = 1
                for segment in result.get('segments', []):
                    for w in segment.get('words', []):
                        start, end = w['start'], w['end']
                        if start >= end: end = start + 0.1
                        f.write(f"{counter}\n{self._fmt_time_simple(start)} --> {self._fmt_time_simple(end)}\n{w['word'].strip()}\n\n")
                        counter += 1

    def _render_video(self):
        sub_path = self.config['srt_path'].replace("\\", "/").replace(":", "\\:")
        
        cmd = [
            "ffmpeg", "-y", "-i", self.config['file_path'],
            "-vf", f"subtitles='{sub_path}'",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            self.config['video_path']
        ]

        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
            text=True, encoding='utf-8', startupinfo=startupinfo
        )

        while self._is_running:
            if process.poll() is not None: break
            time.sleep(0.2)
        
        if not self._is_running:
            process.terminate()
            raise Exception("Cancelado pelo usuário.")
        
        if process.returncode != 0:
            err = process.stderr.read()
            raise Exception(f"Erro FFmpeg: {err}")

    def _fmt_time_simple(self, seconds):
        seconds = max(0, seconds)
        total_seconds = int(seconds)
        milliseconds = int((seconds - total_seconds) * 1000)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"
    
    def stop(self):
        self._is_running = False

# --- WIDGET DROP ZONE ---
class DropZone(QFrame):
    fileDropped = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)
        
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.icon_label = QLabel("📂")
        self.icon_label.setStyleSheet("font-size: 40px; background: transparent; border: none;")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.text_label = QLabel("Arraste um vídeo aqui ou clique")
        self.text_label.setStyleSheet("color: #888888; font-weight: bold; background: transparent; border: none;")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        self.setLayout(layout)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_file_dialog()

    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar Vídeo", "", "Media (*.mp4 *.mov *.mkv *.mp3 *.wav)")
        if path:
            self.fileDropped.emit(path)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
            self.setStyleSheet("background-color: #2D2D30; border-color: #0078D4; border-style: solid;")
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet("") 

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet("") 
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files:
            self.fileDropped.emit(files[0])

# --- JANELA PRINCIPAL ---
class ModernSubtitleApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.selected_file = None
        self.srt_path = None
        self.video_path = None
        
        self.setWindowTitle("Whisper Auto-Caption AI")
        self.resize(550, 780)
        self.setup_ui()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(30, 30, 30, 30)

        header = QVBoxLayout()
        title = QLabel("AI Caption Generator")
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(title)
        main_layout.addLayout(header)

        self.file_card = QFrame()
        self.file_card.setObjectName("Card")
        card_layout = QVBoxLayout(self.file_card)
        
        self.drop_zone = DropZone()
        self.drop_zone.fileDropped.connect(self.on_file_selected)
        
        self.file_label = QLabel("Nenhum arquivo selecionado")
        self.file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_label.setStyleSheet("color: #0078D4; font-weight: bold; margin-top: 5px;")
        self.file_label.setVisible(False)

        card_layout.addWidget(QLabel("1. Arquivo de Entrada"))
        card_layout.addWidget(self.drop_zone)
        card_layout.addWidget(self.file_label)
        main_layout.addWidget(self.file_card)

        settings_card = QFrame()
        settings_card.setObjectName("Card")
        sett_layout = QVBoxLayout(settings_card)
        sett_layout.addWidget(QLabel("2. Configurações"))

        grid = QHBoxLayout()
        
        col1 = QVBoxLayout()
        col1.addWidget(QLabel("Modelo AI:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large-v3"])
        self.model_combo.setCurrentText("small")
        col1.addWidget(self.model_combo)
        
        col1.addWidget(QLabel("Modo de Saída:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Apenas SRT", "SRT + Vídeo"])
        col1.addWidget(self.mode_combo)
        
        col2 = QVBoxLayout()
        col2.addWidget(QLabel("Estilo da Legenda:"))
        self.style_combo = QComboBox()
        self.style_combo.addItems(["Frases Inteligentes", "Palavra por Palavra"])
        self.style_combo.currentIndexChanged.connect(self.toggle_char_spin)
        col2.addWidget(self.style_combo)
        
        self.limit_label = QLabel("Máx. Caracteres:")
        col2.addWidget(self.limit_label)
        
        self.char_spin = QSpinBox()
        self.char_spin.setRange(10, 200)
        self.char_spin.setValue(45)
        self.char_spin.setCursor(Qt.CursorShape.PointingHandCursor)
        col2.addWidget(self.char_spin)

        grid.addLayout(col1)
        grid.addSpacing(20)
        grid.addLayout(col2)
        sett_layout.addLayout(grid)
        main_layout.addWidget(settings_card)

        status_layout = QVBoxLayout()
        self.status_label = QLabel("Aguardando...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pbar = QProgressBar()
        self.pbar.setValue(0)
        
        self.btn_action = QPushButton("INICIAR PROCESSO")
        self.btn_action.setObjectName("PrimaryButton")
        self.btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_action.clicked.connect(self.start_processing)
        self.btn_action.setEnabled(False)

        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.pbar)
        status_layout.addSpacing(5)
        status_layout.addWidget(self.btn_action)
        
        main_layout.addStretch()
        main_layout.addLayout(status_layout)

        self.toggle_char_spin()

    def toggle_char_spin(self):
        is_smart_mode = self.style_combo.currentText() == "Frases Inteligentes"
        self.char_spin.setEnabled(is_smart_mode)
        if is_smart_mode:
            self.limit_label.setStyleSheet("color: #E0E0E0;")
        else:
            self.limit_label.setStyleSheet("color: #555555;")

    def on_file_selected(self, path):
        self.selected_file = path
        name = os.path.basename(path)
        self.drop_zone.text_label.setText(name)
        self.drop_zone.icon_label.setText("🎞️")
        self.file_label.setText(path)
        self.file_label.setVisible(True)
        
        folder = os.path.dirname(path)
        base_name = os.path.splitext(name)[0]
        self.srt_path = os.path.join(folder, f"{base_name}.srt")
        self.video_path = os.path.join(folder, f"{base_name}_legendado.mp4")
        
        self.check_ready()

    def check_ready(self):
        if self.selected_file:
            self.btn_action.setEnabled(True)
            self.status_label.setText("Pronto para iniciar")

    def start_processing(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.btn_action.setText("Cancelando...")
            self.btn_action.setEnabled(False)
            return

        config = {
            'file_path': self.selected_file,
            'srt_path': self.srt_path,
            'video_path': self.video_path,
            'model': self.model_combo.currentText(),
            'subtitle_type': self.style_combo.currentText(),
            'max_chars': self.char_spin.value(),
            'generate_video': self.mode_combo.currentText() == "SRT + Vídeo"
        }

        self.btn_action.setText("CANCELAR")
        self.btn_action.setObjectName("DangerButton")
        self.btn_action.style().unpolish(self.btn_action)
        self.btn_action.style().polish(self.btn_action)
        
        self.worker = TranscriptionWorker(config)
        self.worker.status_update.connect(self.status_label.setText)
        self.worker.progress_update.connect(self.pbar.setValue)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_finished(self, success, message):
        self.btn_action.setText("INICIAR PROCESSO")
        self.btn_action.setObjectName("PrimaryButton")
        self.btn_action.setEnabled(True)
        self.btn_action.style().unpolish(self.btn_action)
        self.btn_action.style().polish(self.btn_action)

        if success:
            self.pbar.setValue(100)
            self.status_label.setText("Concluído!")
            QMessageBox.information(self, "Sucesso", message)
        else:
            self.pbar.setValue(0)
            self.status_label.setText("Status")
            if "Cancelado" not in message:
                QMessageBox.critical(self, "Erro", message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(MODERN_STYLESHEET)
    window = ModernSubtitleApp()
    window.show()
    sys.exit(app.exec())