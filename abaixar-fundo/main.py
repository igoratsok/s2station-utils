import sys
import os
import subprocess
import threading
import torch
import torchaudio
import re
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QPushButton, QSlider, QLabel, QFileDialog, QMessageBox, 
                             QHBoxLayout, QFrame, QProgressBar, QTabWidget)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
import pygame

class AudioTab(QWidget):
    """Representa uma aba individual para cada arquivo processado."""
    def __init__(self, main_app, base_name, voz_path, fundo_path):
        super().__init__()
        self.main_app = main_app
        self.base_name = base_name
        self.voz_path = voz_path
        self.fundo_path = fundo_path

        self.sound_voz = pygame.mixer.Sound(self.voz_path)
        self.sound_fundo = pygame.mixer.Sound(self.fundo_path)
        self.audio_length = self.sound_voz.get_length()

        self.is_playing = False
        self.current_time = 0.0
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_timeline)

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # 1. CARD DO PLAYER
        player_card = QFrame()
        player_card.setObjectName("Card")
        player_layout = QVBoxLayout(player_card)
        
        controls_layout = QHBoxLayout()
        self.btn_play = QPushButton("▶ Play")
        self.btn_play.clicked.connect(self.toggle_play)
        
        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.clicked.connect(self.stop_audio)
        
        controls_layout.addWidget(self.btn_play)
        controls_layout.addWidget(self.btn_stop)
        
        timeline_layout = QHBoxLayout()
        self.lbl_time = QLabel(f"00:00 / {self.format_time(self.audio_length)}")
        self.slider_timeline = QSlider(Qt.Orientation.Horizontal)
        self.slider_timeline.setObjectName("Timeline")
        self.slider_timeline.setRange(0, 1000)
        self.slider_timeline.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        timeline_layout.addWidget(self.slider_timeline)
        timeline_layout.addWidget(self.lbl_time)
        
        player_layout.addLayout(controls_layout)
        player_layout.addLayout(timeline_layout)
        layout.addWidget(player_card)

        # 2. CARD DOS VOLUMES
        sliders_card = QFrame()
        sliders_card.setObjectName("Card")
        sliders_layout = QVBoxLayout(sliders_card)
        sliders_layout.setSpacing(10)

        sliders_layout.addWidget(QLabel("🎤 Volume da Voz:"))
        self.slider_voz = QSlider(Qt.Orientation.Horizontal)
        self.slider_voz.setRange(0, 100)
        self.slider_voz.setValue(100)
        self.slider_voz.valueChanged.connect(self.update_volumes)
        sliders_layout.addWidget(self.slider_voz)

        sliders_layout.addWidget(QLabel("🎸 Volume do Fundo Musical:"))
        self.slider_fundo = QSlider(Qt.Orientation.Horizontal)
        self.slider_fundo.setRange(0, 100)
        self.slider_fundo.setValue(100)
        self.slider_fundo.valueChanged.connect(self.update_volumes)
        sliders_layout.addWidget(self.slider_fundo)

        layout.addWidget(sliders_card)
        layout.addStretch()

        # 3. BOTÃO EXPORTAR
        self.btn_export = QPushButton("↓ Salvar Mixagem MP3")
        self.btn_export.setObjectName("ActionBtn")
        self.btn_export.clicked.connect(self.export_mix)
        layout.addWidget(self.btn_export)

    def format_time(self, seconds):
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"

    def toggle_play(self):
        if self.is_playing:
            pygame.mixer.pause()
            self.is_playing = False
            self.btn_play.setText("▶ Play")
            self.timer.stop()
        else:
            # Avisa o app principal para parar outras abas
            self.main_app.set_active_tab(self)
            
            if self.current_time == 0:
                self.main_app.voz_channel.play(self.sound_voz)
                self.main_app.fundo_channel.play(self.sound_fundo)
                self.update_volumes()
            else:
                pygame.mixer.unpause()
            
            self.is_playing = True
            self.btn_play.setText("⏸ Pause")
            self.timer.start(100)

    def stop_audio(self):
        if self.is_playing or self.current_time > 0:
            pygame.mixer.stop()
            self.is_playing = False
            self.btn_play.setText("▶ Play")
            self.timer.stop()
            self.current_time = 0.0
            self.slider_timeline.setValue(0)
            self.lbl_time.setText(f"00:00 / {self.format_time(self.audio_length)}")

    def update_timeline(self):
        self.current_time += 0.1
        
        if not self.main_app.voz_channel.get_busy() and self.is_playing:
            self.stop_audio()
            return

        if self.audio_length > 0:
            progress = int((self.current_time / self.audio_length) * 1000)
            self.slider_timeline.setValue(progress)
            self.lbl_time.setText(f"{self.format_time(self.current_time)} / {self.format_time(self.audio_length)}")

    def update_volumes(self):
        # Só altera o volume global se esta for a aba ativa tocando
        if self.main_app.active_tab == self:
            vol_voz = self.slider_voz.value() / 100.0
            vol_fundo = self.slider_fundo.value() / 100.0
            self.main_app.voz_channel.set_volume(vol_voz)
            self.main_app.fundo_channel.set_volume(vol_fundo)

    def export_mix(self):
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Mixagem", f"mix_{self.base_name}.mp3", "MP3 Files (*.mp3)"
        )
        
        if save_path:
            if not save_path.lower().endswith('.mp3'):
                save_path += '.mp3'

            try:
                self.main_app.lbl_status.setText(f"Salvando {self.base_name}...")
                QApplication.processEvents()
                
                wav_voz, sample_rate = torchaudio.load(self.voz_path)
                wav_fundo, _ = torchaudio.load(self.fundo_path)

                vol_voz = self.slider_voz.value() / 100.0
                vol_fundo = self.slider_fundo.value() / 100.0

                mixed = (wav_voz * vol_voz) + (wav_fundo * vol_fundo)
                mixed = torch.clamp(mixed, -1.0, 1.0)

                torchaudio.save(save_path, mixed, sample_rate)
                
                self.main_app.lbl_status.setText(f"Salvo: {os.path.basename(save_path)}")
                QMessageBox.information(self, "Sucesso", "Mixagem salva com sucesso em MP3!")
                
            except Exception as e:
                self.main_app.lbl_status.setText("Erro ao salvar arquivo.")
                QMessageBox.critical(self, "Erro", f"Ocorreu um erro ao salvar:\n{str(e)}")

class AudioSplitterApp(QMainWindow):
    progress_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str, str, str)
    error_signal = pyqtSignal(str)
    batch_done_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Separador e Mixer em Lote")
        self.setGeometry(100, 100, 550, 650)

        pygame.mixer.init()
        self.voz_channel = pygame.mixer.Channel(0)
        self.fundo_channel = pygame.mixer.Channel(1)
        self.active_tab = None

        self.progress_signal.connect(self.update_progress_bar)
        self.status_signal.connect(self.update_status)
        self.finished_signal.connect(self.add_new_tab)
        self.error_signal.connect(self.on_process_error)
        self.batch_done_signal.connect(self.on_batch_done)

        self.apply_modern_style()
        self.initUI()

    def apply_modern_style(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2e; }
            QLabel { color: #cdd6f4; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; font-size: 14px; }
            QLabel#TitleLabel { font-size: 22px; font-weight: bold; color: #89b4fa; margin-bottom: 5px; }
            QLabel#StatusLabel { color: #a6adc8; font-style: italic; margin: 5px 0; }
            QPushButton { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; border-radius: 8px; padding: 10px 16px; font-weight: bold; font-size: 14px; }
            QPushButton:hover:!disabled { background-color: #45475a; border: 1px solid #89b4fa; }
            QPushButton:pressed:!disabled { background-color: #585b70; }
            QPushButton:disabled { background-color: #181825; color: #45475a; border: 1px solid #1e1e2e; }
            QPushButton#ActionBtn { background-color: #89b4fa; color: #11111b; border: none; margin-top: 10px; }
            QPushButton#ActionBtn:hover:!disabled { background-color: #b4befe; }
            QPushButton#ActionBtn:disabled { background-color: #313244; color: #585b70; }
            QSlider::groove:horizontal { border: 1px solid #313244; height: 6px; background: #45475a; border-radius: 3px; }
            QSlider::handle:horizontal { background: #89b4fa; border: 2px solid #1e1e2e; width: 18px; height: 18px; margin: -6px 0; border-radius: 9px; }
            QSlider::handle:horizontal:hover:!disabled { background: #b4befe; transform: scale(1.1); }
            QSlider::handle:horizontal:disabled { background: #45475a; border: 2px solid #313244; }
            QSlider#Timeline::handle:horizontal { background: #a6e3a1; }
            QFrame#Card { background-color: #181825; border-radius: 12px; padding: 15px; }
            QProgressBar { border: 1px solid #45475a; border-radius: 6px; text-align: center; background-color: #1e1e2e; color: #cdd6f4; font-weight: bold; height: 20px; }
            QProgressBar::chunk { background-color: #a6e3a1; border-radius: 5px; }
            
            /* Estilos das Abas */
            QTabWidget::pane { border: 1px solid #45475a; background: #1e1e2e; border-radius: 8px; margin-top: 10px; }
            QTabBar::tab { background: #313244; color: #a6adc8; padding: 8px 15px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
            QTabBar::tab:selected { background: #89b4fa; color: #11111b; font-weight: bold; }
            QTabBar::tab:hover:!selected { background: #45475a; }
        """)

    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(25, 25, 25, 25)
        main_layout.setSpacing(15)

        title = QLabel("Mixer com IA (Lote)")
        title.setObjectName("TitleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        self.btn_load = QPushButton("Carregar Arquivos (MP3 ou MP4)")
        self.btn_load.clicked.connect(self.load_files)
        main_layout.addWidget(self.btn_load)

        self.lbl_status = QLabel("Nenhum arquivo carregado.")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

    def load_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Abrir Mídias", "", "Media Files (*.mp3 *.mp4 *.wav)")
        if file_paths:
            self.btn_load.setEnabled(False)
            self.progress_bar.setValue(0)
            self.progress_bar.show()
            self.tabs.clear()
            
            # Inicia o processamento da lista em uma thread separada
            threading.Thread(target=self.process_batch, args=(file_paths,), daemon=True).start()

    def process_batch(self, file_paths):
        total = len(file_paths)
        for i, file_path in enumerate(file_paths):
            try:
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                self.status_signal.emit(f"Processando ({i+1}/{total}): {base_name}")
                self.progress_signal.emit(0)
                
                if file_path.lower().endswith('.mp4'):
                    os.makedirs("separated", exist_ok=True)
                    extracted_path = os.path.join("separated", f"{base_name}_extracted.mp3")
                    
                    subprocess.run([
                        "ffmpeg", "-y", "-i", file_path, 
                        "-q:a", "0", "-map", "a", extracted_path
                    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    
                    file_path = extracted_path
                    base_name = f"{base_name}_extracted" 

                process = subprocess.Popen(
                    ["demucs", "--two-stems=vocals", file_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                buffer = ""
                while True:
                    char = process.stdout.read(1)
                    if not char and process.poll() is not None:
                        break
                    
                    if char in ['\r', '\n']:
                        match = re.search(r'(\d+)%', buffer)
                        if match:
                            self.progress_signal.emit(int(match.group(1)))
                        buffer = ""
                    else:
                        buffer += char

                if process.returncode != 0:
                    raise Exception(f"Demucs falhou com código {process.returncode}")

                output_dir = os.path.join("separated", "htdemucs", base_name)
                v_path = os.path.join(output_dir, "vocals.wav")
                f_path = os.path.join(output_dir, "no_vocals.wav")

                # Emite sinal para criar a aba
                clean_name = base_name.replace('_extracted', '')
                self.finished_signal.emit(clean_name, v_path, f_path)

            except Exception as e:
                self.error_signal.emit(f"Erro em {base_name}: {str(e)}")

        self.batch_done_signal.emit()

    def update_progress_bar(self, value):
        self.progress_bar.setValue(value)

    def update_status(self, msg):
        self.lbl_status.setText(msg)

    def add_new_tab(self, base_name, v_path, f_path):
        tab = AudioTab(self, base_name, v_path, f_path)
        self.tabs.addTab(tab, base_name)

    def on_process_error(self, error_msg):
        print("Erro detalhado:", error_msg)
        QMessageBox.warning(self, "Aviso no Lote", error_msg)

    def on_batch_done(self):
        self.lbl_status.setText("Processamento em lote concluído!")
        self.progress_bar.hide()
        self.btn_load.setEnabled(True)

    def set_active_tab(self, tab):
        """Garante que apenas uma aba toque por vez."""
        if self.active_tab and self.active_tab != tab:
            self.active_tab.stop_audio()
        self.active_tab = tab

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = AudioSplitterApp()
    ex.show()
    sys.exit(app.exec())