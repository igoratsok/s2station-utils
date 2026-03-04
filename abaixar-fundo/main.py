import sys
import os
import subprocess
import threading
import torch
import torchaudio
import re
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QPushButton, QSlider, QLabel, QFileDialog, QMessageBox, QHBoxLayout, QFrame, QProgressBar)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
import pygame

class AudioSplitterApp(QMainWindow):
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(str, str, str)
    error_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Separador e Mixer de Áudio/Vídeo")
        self.setGeometry(100, 100, 500, 560) # Aumentei um pouco a altura para acomodar o player

        pygame.mixer.init()
        self.voz_channel = pygame.mixer.Channel(0)
        self.fundo_channel = pygame.mixer.Channel(1)
        self.sound_voz = None
        self.sound_fundo = None
        
        self.voz_path = ""
        self.fundo_path = ""

        # Controle de Tempo para o Player
        self.is_playing = False
        self.current_time = 0.0
        self.audio_length = 0.0
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_timeline)

        self.progress_signal.connect(self.update_progress_bar)
        self.finished_signal.connect(self.on_process_finished)
        self.error_signal.connect(self.on_process_error)

        self.apply_modern_style()
        self.initUI()
        self.set_controls_enabled(False) # Inicia com tudo desativado

    def apply_modern_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e2e;
            }
            QLabel {
                color: #cdd6f4;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
                font-size: 14px;
            }
            QLabel#TitleLabel {
                font-size: 22px;
                font-weight: bold;
                color: #89b4fa;
                margin-bottom: 5px;
            }
            QLabel#StatusLabel {
                color: #a6adc8;
                font-style: italic;
                margin: 5px 0;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 8px;
                padding: 10px 16px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover:!disabled {
                background-color: #45475a;
                border: 1px solid #89b4fa;
            }
            QPushButton:pressed:!disabled {
                background-color: #585b70;
            }
            QPushButton:disabled {
                background-color: #181825;
                color: #45475a;
                border: 1px solid #1e1e2e;
            }
            QPushButton#ActionBtn {
                background-color: #89b4fa;
                color: #11111b;
                border: none;
                margin-top: 10px;
            }
            QPushButton#ActionBtn:hover:!disabled {
                background-color: #b4befe;
            }
            QPushButton#ActionBtn:disabled {
                background-color: #313244;
                color: #585b70;
            }
            QPushButton#ClearBtn {
                background-color: #f38ba8;
                color: #11111b;
                border: none;
            }
            QPushButton#ClearBtn:hover:!disabled {
                background-color: #f5c2e7;
            }
            QSlider::groove:horizontal {
                border: 1px solid #313244;
                height: 6px;
                background: #45475a;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #89b4fa;
                border: 2px solid #1e1e2e;
                width: 18px;
                height: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover:!disabled {
                background: #b4befe;
                transform: scale(1.1);
            }
            QSlider::handle:horizontal:disabled {
                background: #45475a;
                border: 2px solid #313244;
            }
            QSlider#Timeline::handle:horizontal {
                background: #a6e3a1; /* Cor diferente para diferenciar do volume */
            }
            QFrame#Card {
                background-color: #181825;
                border-radius: 12px;
                padding: 15px;
            }
            QProgressBar {
                border: 1px solid #45475a;
                border-radius: 6px;
                text-align: center;
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-weight: bold;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #a6e3a1;
                border-radius: 5px;
            }
        """)

    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(25, 25, 25, 25)
        main_layout.setSpacing(15)

        title = QLabel("Mixer com IA")
        title.setObjectName("TitleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        top_buttons_layout = QHBoxLayout()
        self.btn_load = QPushButton("Carregar Arquivo (MP3 ou MP4)")
        self.btn_load.clicked.connect(self.load_file)
        top_buttons_layout.addWidget(self.btn_load)

        self.btn_clear = QPushButton("Limpar / Nova Faixa")
        self.btn_clear.setObjectName("ClearBtn")
        self.btn_clear.clicked.connect(self.clear_workspace)
        self.btn_clear.hide()
        top_buttons_layout.addWidget(self.btn_clear)

        main_layout.addLayout(top_buttons_layout)

        self.lbl_status = QLabel("Nenhum arquivo carregado.")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

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
        self.lbl_time = QLabel("00:00 / 00:00")
        self.slider_timeline = QSlider(Qt.Orientation.Horizontal)
        self.slider_timeline.setObjectName("Timeline")
        self.slider_timeline.setRange(0, 1000)
        # Ignora cliques do mouse para não quebrar a sincronia, agindo apenas como visualizador
        self.slider_timeline.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        timeline_layout.addWidget(self.slider_timeline)
        timeline_layout.addWidget(self.lbl_time)
        
        player_layout.addLayout(controls_layout)
        player_layout.addLayout(timeline_layout)
        main_layout.addWidget(player_card)

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

        main_layout.addWidget(sliders_card)
        main_layout.addStretch()

        # 3. BOTÃO EXPORTAR NO FINAL
        self.btn_export = QPushButton("↓ Salvar Mixagem MP3")
        self.btn_export.setObjectName("ActionBtn")
        self.btn_export.clicked.connect(self.export_mix)
        main_layout.addWidget(self.btn_export)

    def set_controls_enabled(self, state):
        self.btn_play.setEnabled(state)
        self.btn_stop.setEnabled(state)
        self.slider_voz.setEnabled(state)
        self.slider_fundo.setEnabled(state)
        self.slider_timeline.setEnabled(state)
        self.btn_export.setEnabled(state)

    def format_time(self, seconds):
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"

    def clear_workspace(self):
        self.stop_audio()
        self.sound_voz = None
        self.sound_fundo = None
        self.voz_path = ""
        self.fundo_path = ""
        self.audio_length = 0.0
        
        self.slider_voz.setValue(100)
        self.slider_fundo.setValue(100)
        self.lbl_time.setText("00:00 / 00:00")
        
        self.set_controls_enabled(False)
        self.btn_load.show()
        self.btn_clear.hide()
        self.progress_bar.hide()
        self.progress_bar.setValue(0)
        
        self.lbl_status.setText("Área limpa. Pronto para novo arquivo.")

    def load_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Abrir Mídia", "", "Media Files (*.mp3 *.mp4 *.wav)")
        if file_path:
            self.lbl_status.setText("Preparando arquivo...")
            self.btn_load.hide()
            self.btn_clear.show()
            self.btn_clear.setEnabled(False) 
            
            self.set_controls_enabled(False)
            
            self.progress_bar.setValue(0)
            self.progress_bar.show()
            
            threading.Thread(target=self.process_audio, args=(file_path,), daemon=True).start()

    def process_audio(self, file_path):
        try:
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            
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

            self.finished_signal.emit(base_name.replace('_extracted', ''), v_path, f_path)

        except Exception as e:
            self.error_signal.emit(str(e))

    def update_progress_bar(self, value):
        self.progress_bar.setValue(value)
        self.lbl_status.setText(f"Processando IA... {value}%")

    def on_process_finished(self, base_name, v_path, f_path):
        self.voz_path = v_path
        self.fundo_path = f_path
        
        self.sound_voz = pygame.mixer.Sound(self.voz_path)
        self.sound_fundo = pygame.mixer.Sound(self.fundo_path)
        
        self.audio_length = self.sound_voz.get_length()
        self.lbl_time.setText(f"00:00 / {self.format_time(self.audio_length)}")

        self.lbl_status.setText(f"Pronto: {base_name}")
        self.progress_bar.setValue(100)
        self.btn_clear.setEnabled(True)
        self.set_controls_enabled(True)

    def on_process_error(self, error_msg):
        self.lbl_status.setText("Erro ao processar o arquivo.")
        self.progress_bar.hide()
        self.btn_clear.setEnabled(True)
        print("Erro detalhado:", error_msg)

    def toggle_play(self):
        if self.is_playing:
            pygame.mixer.pause()
            self.is_playing = False
            self.btn_play.setText("▶ Play")
            self.timer.stop()
        else:
            if self.current_time == 0:
                self.voz_channel.play(self.sound_voz)
                self.fundo_channel.play(self.sound_fundo)
                self.update_volumes()
            else:
                pygame.mixer.unpause()
            
            self.is_playing = True
            self.btn_play.setText("⏸ Pause")
            self.timer.start(100) # Atualiza a linha do tempo a cada 100ms

    def stop_audio(self):
        pygame.mixer.stop()
        self.is_playing = False
        self.btn_play.setText("▶ Play")
        self.timer.stop()
        self.current_time = 0.0
        self.slider_timeline.setValue(0)
        if self.audio_length > 0:
            self.lbl_time.setText(f"00:00 / {self.format_time(self.audio_length)}")

    def update_timeline(self):
        self.current_time += 0.1
        
        # Se a música acabou naturalmente
        if not self.voz_channel.get_busy() and self.is_playing:
            self.stop_audio()
            return

        # Atualiza visual do tempo e do slider
        if self.audio_length > 0:
            progress = int((self.current_time / self.audio_length) * 1000)
            self.slider_timeline.setValue(progress)
            self.lbl_time.setText(f"{self.format_time(self.current_time)} / {self.format_time(self.audio_length)}")

    def update_volumes(self):
        vol_voz = self.slider_voz.value() / 100.0
        vol_fundo = self.slider_fundo.value() / 100.0
        
        self.voz_channel.set_volume(vol_voz)
        self.fundo_channel.set_volume(vol_fundo)

    def export_mix(self):
        if not self.voz_path or not self.fundo_path:
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Salvar Mixagem", 
            "minha_mixagem.mp3", 
            "MP3 Files (*.mp3)"
        )
        
        if save_path:
            if not save_path.lower().endswith('.mp3'):
                save_path += '.mp3'

            try:
                self.lbl_status.setText("Salvando mixagem...")
                QApplication.processEvents()
                
                wav_voz, sample_rate = torchaudio.load(self.voz_path)
                wav_fundo, _ = torchaudio.load(self.fundo_path)

                vol_voz = self.slider_voz.value() / 100.0
                vol_fundo = self.slider_fundo.value() / 100.0

                mixed = (wav_voz * vol_voz) + (wav_fundo * vol_fundo)
                mixed = torch.clamp(mixed, -1.0, 1.0)

                torchaudio.save(save_path, mixed, sample_rate)
                
                self.lbl_status.setText(f"Salvo: {os.path.basename(save_path)}")
                QMessageBox.information(self, "Sucesso", "Mixagem salva com sucesso em MP3!")
                
            except Exception as e:
                self.lbl_status.setText("Erro ao salvar arquivo.")
                QMessageBox.critical(self, "Erro", f"Ocorreu um erro ao salvar:\n{str(e)}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = AudioSplitterApp()
    ex.show()
    sys.exit(app.exec())