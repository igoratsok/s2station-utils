import sys
import os
import time
import subprocess
import traceback
import ssl  # <--- IMPORTANTE: Adicionado para corrigir o erro
import whisper

# --- CORREÇÃO DE SSL PARA MACOS ---
# Isso permite baixar o modelo sem o erro CERTIFICATE_VERIFY_FAILED
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
    QMainWindow {
        background-color: #121212;
    }
    QWidget {
        color: #E0E0E0;
        font-family: 'Segoe UI', 'Inter', sans-serif;
        font-size: 14px;
    }
    /* Cards (Container) */
    QFrame#Card {
        background-color: #1E1E1E;
        border-radius: 12px;
        border: 1px solid #333333;
    }
    /* Drop Zone */
    QFrame#DropZone {
        background-color: #252526;
        border: 2px dashed #444444;
        border-radius: 12px;
    }
    QFrame#DropZone:hover {
        background-color: #2D2D30;
        border-color: #0078D4;
        border-style: solid;
    }
    /* Labels */
    QLabel#Title { font-size: 18px; font-weight: bold; color: #FFFFFF; }
    QLabel#Subtitle { color: #AAAAAA; font-size: 13px; }

    /* INPUTS */
    QComboBox {
        background-color: #2D2D2D;
        border: 1px solid #3E3E3E;
        border-radius: 6px;
        padding: 5px 10px;
        min-width: 100px;
    }
    QComboBox::drop-down { border: 0px; }
    
    /* SPINBOX CORRIGIDO */
    QSpinBox {
        background-color: #2D2D2D;
        border: 1px solid #3E3E3E;
        border-radius: 6px;
        padding: 5px 10px;
    }
    QSpinBox:disabled {
        background-color: #202020;
        color: #555555;
        border-color: #252525;
    }
    QSpinBox::up-button, QSpinBox::down-button {
        background-color: #383838;
        width: 20px;
        margin: 1px;
        border-radius: 2px;
    }
    QSpinBox::up-button:hover, QSpinBox::down-button:hover {
        background-color: #505050;
    }

    /* BOTOES */
    QPushButton {
        background-color: #333333;
        border: 1px solid #3E3E3E;
        border-radius: 6px;
        padding: 10px 20px;
        font-weight: 600;
    }
    QPushButton:hover { background-color: #444444; }
    
    QPushButton#PrimaryButton {
        background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #0078D4, stop:1 #005A9E);
        border: none; color: white;
    }
    QPushButton#PrimaryButton:hover {
        background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #1084E3, stop:1 #0066B4);
    }
    QPushButton#PrimaryButton:disabled { background-color: #2C2C2C; color: #555555; }
    
    QPushButton#DangerButton { background-color: #C42B1C; border: none; }
    QPushButton#DangerButton:hover { background-color: #B00020; }
    
    QProgressBar {
        border: none; background-color: #2D2D2D; border-radius: 4px; height: 8px; text-align: center;
    }
    QProgressBar::chunk { background-color: #0078D4; border-radius: 4px; }
"""

# --- WORKER THREAD (Lógica de Processamento) ---
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
            # 1. Carregar Modelo
            self.status_update.emit(f"🚀 Carregando modelo Whisper '{self.config['model']}'...")
            self.progress_update.emit(5)
            
            try:
                # O patch de SSL lá em cima permite que isso funcione no Mac agora
                model = whisper.load_model(self.config['model'])
            except Exception as e:
                self.finished.emit(False, f"Erro ao carregar modelo.\n{str(e)}")
                return

            if not self._is_running: return

            # 2. Transcrever
            self.status_update.emit("🎙️ Transcrevendo áudio... (Aguarde)")
            result = model.transcribe(self.config['file_path'], word_timestamps=True)
            
            if not self._is_running: return

            # 3. Gerar SRT (Com lógica inteligente de Maiúsculas)
            self.status_update.emit("📝 Processando e agrupando legendas...")
            self.progress_update.emit(80)
            
            self._generate_srt(result, self.config['srt_path'])

            if not self._is_running: return

            # 4. Renderizar Vídeo (Se selecionado)
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
        all_words = []
        for segment in result.get('segments', []):
            for word_data in segment.get('words', []):
                all_words.append(word_data)

        max_words = self.config['max_words']
        is_phrase_mode = self.config['subtitle_type'] == "Frases Completas"
        
        # Hard limit de segurança
        hard_limit = max_words + 4 

        with open(path, "w", encoding='utf-8') as f:
            counter = 1
            
            if not is_phrase_mode:
                for w in all_words:
                    start, end = w['start'], w['end']
                    if start >= end: end = start + 0.1
                    f.write(f"{counter}\n{self._fmt_time(start)} --> {self._fmt_time(end)}\n{w['word'].strip()}\n\n")
                    counter += 1
            
            else:
                current_chunk = []
                
                for i, w in enumerate(all_words):
                    current_chunk.append(w)
                    
                    current_text = w['word'].strip()
                    is_curr_cap = current_text and current_text[0].isupper()
                    
                    is_next_cap = False
                    if i < len(all_words) - 1:
                        next_text = all_words[i+1]['word'].strip()
                        if next_text and next_text[0].isupper():
                            is_next_cap = True

                    in_cap_sequence = is_curr_cap and is_next_cap
                    
                    should_break = False
                    chunk_len = len(current_chunk)

                    if chunk_len >= max_words:
                        should_break = True
                        if in_cap_sequence and chunk_len < hard_limit:
                            should_break = False
                    
                    if chunk_len >= hard_limit:
                        should_break = True
                        
                    if i == len(all_words) - 1:
                        should_break = True

                    if should_break:
                        if current_chunk:
                            start_time = current_chunk[0]['start']
                            end_time = current_chunk[-1]['end']
                            if end_time <= start_time: end_time = start_time + 1.0
                            
                            text_content = "".join([cw['word'] for cw in current_chunk]).strip()
                            
                            f.write(f"{counter}\n")
                            f.write(f"{self._fmt_time(start_time)} --> {self._fmt_time(end_time)}\n")
                            f.write(f"{text_content}\n\n")
                            
                            counter += 1
                            current_chunk = []

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

    def _fmt_time(self, seconds):
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

        # Header
        header = QVBoxLayout()
        title = QLabel("AI Caption Generator")
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(title)
        main_layout.addLayout(header)

        # Arquivo
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

        # Configurações
        settings_card = QFrame()
        settings_card.setObjectName("Card")
        sett_layout = QVBoxLayout(settings_card)
        sett_layout.addWidget(QLabel("2. Configurações"))

        grid = QHBoxLayout()
        
        # Col Esquerda
        col1 = QVBoxLayout()
        col1.addWidget(QLabel("Modelo AI:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large-v3"])
        self.model_combo.setCurrentText("small")
        col1.addWidget(self.model_combo)
        
        col1.addWidget(QLabel("Modo:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Apenas SRT", "SRT + Vídeo"])
        col1.addWidget(self.mode_combo)
        
        # Col Direita
        col2 = QVBoxLayout()
        col2.addWidget(QLabel("Estilo:"))
        self.style_combo = QComboBox()
        self.style_combo.addItems(["Frases Completas", "Palavra por Palavra"])
        self.style_combo.currentIndexChanged.connect(self.toggle_word_spin)
        col2.addWidget(self.style_combo)
        
        self.limit_label = QLabel("Max. Palavras:")
        col2.addWidget(self.limit_label)
        
        self.word_spin = QSpinBox()
        self.word_spin.setRange(1, 50)
        self.word_spin.setValue(10)
        self.word_spin.setCursor(Qt.CursorShape.PointingHandCursor)
        col2.addWidget(self.word_spin)

        grid.addLayout(col1)
        grid.addSpacing(20)
        grid.addLayout(col2)
        sett_layout.addLayout(grid)
        main_layout.addWidget(settings_card)

        # Status
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

        # Inicializa estado do spinbox
        self.toggle_word_spin()

    def toggle_word_spin(self):
        is_phrase_mode = self.style_combo.currentText() == "Frases Completas"
        self.word_spin.setEnabled(is_phrase_mode)
        if is_phrase_mode:
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
            'max_words': self.word_spin.value(),
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