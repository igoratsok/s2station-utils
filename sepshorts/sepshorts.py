import sys
import os
import shutil
import ffmpeg
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QLabel, QFileDialog, QProgressBar, QTextEdit, 
                             QMessageBox, QFrame)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QDragEnterEvent, QDropEvent, QPalette, QColor

# --- WORKER THREAD (Lógica de Processamento) ---
class OrganizerWorker(QThread):
    progress_signal = pyqtSignal(int)
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, folders):
        super().__init__()
        self.folders = folders

    def is_vertical_video(self, file_path):
        """
        Detecta se o vídeo é vertical (Shorts/Reels/TikTok).
        """
        try:
            probe = ffmpeg.probe(file_path)
            video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
            
            if not video_stream:
                return False

            width = int(video_stream['width'])
            height = int(video_stream['height'])
            
            rotation = 0
            
            # 1. Verifica tags padrão
            tags = video_stream.get('tags', {})
            if 'rotate' in tags:
                try:
                    rotation = float(tags['rotate'])
                except ValueError:
                    pass

            # 2. Verifica side_data_list (iPhone/Android Modernos)
            side_data_list = video_stream.get('side_data_list', [])
            for side_data in side_data_list:
                if 'rotation' in side_data:
                    try:
                        rotation = float(side_data['rotation'])
                        break 
                    except ValueError:
                        pass
            
            rotation = abs(rotation) % 360

            if rotation == 90 or rotation == 270:
                width, height = height, width

            return height > width

        except (ffmpeg.Error, KeyError, Exception):
            return False

    def run(self):
        total_folders = len(self.folders)
        
        video_exts = ('.mov', '.mp4', '.avi', '.wmv', '.flv', '.mkv', '.webm', '.MP4', '.MOV')
        photo_exts = ('.jpg', '.jpeg', '.heic', '.png', '.raw', '.dng', '.JPG', '.JPEG', '.HEIC')

        for i, folder in enumerate(self.folders):
            folder_name = os.path.basename(folder)
            self.log_signal.emit(f"📂 INICIANDO: {folder_name}")

            # 1. Criar estrutura de pastas
            dirs = {
                "360": os.path.join(folder, "360"),
                "Videos": os.path.join(folder, "Videos"),
                "Fotos": os.path.join(folder, "Fotos"),
                "LRF": os.path.join(folder, "LRF")
            }
            
            for path in dirs.values():
                os.makedirs(path, exist_ok=True)

            try:
                files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
            except Exception as e:
                self.log_signal.emit(f"❌ Erro ao acessar pasta: {e}")
                continue

            for file in files:
                # --- CORREÇÃO AQUI ---
                # Ignora arquivos de sistema do macOS (metadados)
                if file.startswith("._") or file == ".DS_Store":
                    continue
                # ---------------------

                file_path = os.path.join(folder, file)
                filename_lower = file.lower()

                try:
                    dest = None
                    if file.startswith("360-"):
                        dest = dirs["360"]
                    elif filename_lower.endswith(".lrf"):
                        dest = dirs["LRF"]
                    elif filename_lower.endswith(video_exts):
                        dest = dirs["Videos"]
                    elif filename_lower.endswith(photo_exts):
                        dest = dirs["Fotos"]
                    
                    if dest:
                        shutil.move(file_path, os.path.join(dest, file))
                        
                except Exception as e:
                    self.log_signal.emit(f"❌ Erro ao mover {file}: {str(e)}")

            # 3. Processar Shorts
            videos_path = dirs["Videos"]
            shorts_path = os.path.join(videos_path, "Shorts")
            
            try:
                video_files = [f for f in os.listdir(videos_path) if os.path.isfile(os.path.join(videos_path, f))]
            except FileNotFoundError:
                video_files = []

            if video_files:
                self.log_signal.emit(f"   🎥 Analisando {len(video_files)} vídeos para Shorts...")
                
                if not os.path.exists(shorts_path):
                    os.makedirs(shorts_path)

                count_shorts = 0
                for vid in video_files:
                    # Ignora arquivos ocultos aqui também por segurança
                    if vid.startswith("._"): continue

                    if vid.lower().endswith(video_exts):
                        vid_path = os.path.join(videos_path, vid)
                        
                        if self.is_vertical_video(vid_path):
                            try:
                                shutil.move(vid_path, os.path.join(shorts_path, vid))
                                count_shorts += 1
                                self.log_signal.emit(f"     📱 Short Detectado: {vid}")
                            except Exception as e:
                                self.log_signal.emit(f"❌ Erro ao mover Short {vid}: {e}")
                
                if count_shorts > 0:
                    self.log_signal.emit(f"   ✅ {count_shorts} Shorts movidos.")
                else:
                    self.log_signal.emit("   ℹ️ Nenhum vídeo vertical encontrado.")

            progress = int(((i + 1) / total_folders) * 100)
            self.progress_signal.emit(progress)

        self.finished_signal.emit()


# --- INTERFACE GRÁFICA (Mantida idêntica à versão moderna) ---
class ModernWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Organizador de Mídia")
        self.setMinimumSize(650, 550)
        self.setAcceptDrops(True)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(25)
        main_layout.setContentsMargins(40, 40, 40, 40)

        self.drop_frame = QFrame()
        self.drop_frame.setObjectName("DropFrame")
        self.drop_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        
        drop_layout = QVBoxLayout(self.drop_frame)
        drop_layout.setSpacing(15)
        
        self.lbl_icon = QLabel("📁")
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_icon.setObjectName("DropIcon")

        self.lbl_main_text = QLabel("Arraste pastas aqui")
        self.lbl_main_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_main_text.setObjectName("DropMainText")
        
        self.lbl_sub_text = QLabel("(ou clique para selecionar)")
        self.lbl_sub_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_sub_text.setObjectName("DropSubText")

        drop_layout.addStretch()
        drop_layout.addWidget(self.lbl_icon)
        drop_layout.addWidget(self.lbl_main_text)
        drop_layout.addWidget(self.lbl_sub_text)
        drop_layout.addStretch()

        self.drop_frame.mouseReleaseEvent = self.open_folder_dialog
        main_layout.addWidget(self.drop_frame, stretch=2)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setPlaceholderText("> Aguardando pastas...")
        self.log_box.setFixedHeight(160)
        main_layout.addWidget(self.log_box)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
            self.drop_frame.setProperty("hover", True)
            self.drop_frame.style().unpolish(self.drop_frame)
            self.drop_frame.style().polish(self.drop_frame)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.drop_frame.setProperty("hover", False)
        self.drop_frame.style().unpolish(self.drop_frame)
        self.drop_frame.style().polish(self.drop_frame)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self.drop_frame.setProperty("hover", False)
        self.drop_frame.style().unpolish(self.drop_frame)
        self.drop_frame.style().polish(self.drop_frame)

        folders = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isdir(path):
                folders.append(path)
        
        if folders:
            self.start_processing(folders)
        else:
            self.log_box.append("> ⚠️ Por favor, arraste apenas pastas.")

    def open_folder_dialog(self, event):
        folder = QFileDialog.getExistingDirectory(self, "Selecione uma Pasta")
        if folder:
            self.start_processing([folder])

    def start_processing(self, folders):
        self.drop_frame.setEnabled(False)
        self.log_box.clear()
        self.log_box.append(f"> 🚀 Iniciando organização em {len(folders)} pasta(s)...")
        self.progress_bar.setValue(0)

        self.worker = OrganizerWorker(folders)
        self.worker.log_signal.connect(self.update_log)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.finished_signal.connect(self.process_finished)
        self.worker.start()

    def update_log(self, message):
        self.log_box.append(f"> {message}")
        sb = self.log_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    def process_finished(self):
        self.drop_frame.setEnabled(True)
        self.progress_bar.setValue(100)
        QMessageBox.information(self, "Concluído", "Organização finalizada com sucesso!")
        self.log_box.append("> ✅ Processo finalizado.")

def apply_modern_style(app):
    font = QFont()
    font.setFamily(".AppleSystemUIFont") 
    font.setPointSize(13)
    app.setFont(font)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    app.setPalette(palette)

    stylesheet = """
    QMainWindow { background-color: #1E1E1E; }
    
    #DropFrame {
        border: 2px dashed #555;
        border-radius: 16px;
        background-color: #2A2A2A;
    }
    #DropFrame[hover="true"] {
        border-color: #007AFF;
        background-color: rgba(0, 122, 255, 0.15);
    }
    #DropFrame:hover {
        border-color: #777;
        background-color: #333;
    }
    #DropIcon { font-size: 64px; color: #888; }
    #DropMainText { font-size: 18px; font-weight: 600; color: #DDD; }
    #DropSubText { font-size: 14px; color: #999; }

    QProgressBar {
        border: none;
        background-color: #333;
        border-radius: 4px;
    }
    QProgressBar::chunk {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #007AFF, stop:1 #00C6FF);
        border-radius: 4px;
    }

    QTextEdit {
        border: 1px solid #444;
        border-radius: 10px;
        background-color: #121212;
        color: #00FF00;
        font-family: 'SF Mono', 'Menlo', 'Monaco', monospace;
        font-size: 12px;
        padding: 12px;
    }
    QMessageBox { background-color: #2A2A2A; color: #DDD; }
    QPushButton {
        background-color: #444; border: 1px solid #555; border-radius: 6px; color: #DDD; padding: 6px 16px;
    }
    """
    app.setStyleSheet(stylesheet)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_modern_style(app)
    window = ModernWindow()
    window.show()
    sys.exit(app.exec())