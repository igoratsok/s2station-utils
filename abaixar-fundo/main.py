import sys
import os
import subprocess
import threading
import torch
import torchaudio
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QPushButton, QSlider, QLabel, QFileDialog, QMessageBox, QHBoxLayout, QFrame)
from PyQt6.QtCore import Qt
import pygame

class AudioSplitterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Separador e Mixer de Áudio/Vídeo")
        self.setGeometry(100, 100, 500, 400)

        pygame.mixer.init()
        self.voz_channel = pygame.mixer.Channel(0)
        self.fundo_channel = pygame.mixer.Channel(1)
        self.sound_voz = None
        self.sound_fundo = None
        
        self.voz_path = ""
        self.fundo_path = ""

        self.apply_modern_style()
        self.initUI()

    def apply_modern_style(self):
        # Estilo QSS (Dark Mode moderno inspirado em softwares de edição)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e2e;
            }
            QLabel {
                color: #cdd6f4;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                font-size: 14px;
            }
            QLabel#TitleLabel {
                font-size: 22px;
                font-weight: bold;
                color: #89b4fa;
                margin-bottom: 10px;
            }
            QLabel#StatusLabel {
                color: #a6adc8;
                font-style: italic;
                margin: 10px 0;
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
            QPushButton:hover {
                background-color: #45475a;
                border: 1px solid #89b4fa;
            }
            QPushButton:pressed {
                background-color: #585b70;
            }
            QPushButton:disabled {
                background-color: #181825;
                color: #585b70;
                border: 1px solid #313244;
            }
            QPushButton#ActionBtn {
                background-color: #89b4fa;
                color: #11111b;
                border: none;
            }
            QPushButton#ActionBtn:hover {
                background-color: #b4befe;
            }
            QPushButton#ActionBtn:disabled {
                background-color: #313244;
                color: #585b70;
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
            QSlider::handle:horizontal:hover {
                background: #b4befe;
                transform: scale(1.1);
            }
            QFrame#Card {
                background-color: #181825;
                border-radius: 12px;
                padding: 15px;
            }
        """)

    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal com margens maiores para respirar
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(25, 25, 25, 25)
        main_layout.setSpacing(15)

        # Título
        title = QLabel("Mixer com IA")
        title.setObjectName("TitleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        # Botão de Carregar
        self.btn_load = QPushButton("Carregar Arquivo (MP3 ou MP4)")
        self.btn_load.clicked.connect(self.load_file)
        main_layout.addWidget(self.btn_load)

        # Status
        self.lbl_status = QLabel("Nenhum arquivo carregado.")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.lbl_status)

        # Card para os controles de mídia
        controls_card = QFrame()
        controls_card.setObjectName("Card")
        controls_layout = QHBoxLayout(controls_card)
        
        self.btn_play = QPushButton("▶ Tocar / Pausar")
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_play.setEnabled(False)
        controls_layout.addWidget(self.btn_play)

        self.btn_export = QPushButton("↓ Salvar Mixagem MP3")
        self.btn_export.setObjectName("ActionBtn") # Aplica estilo de destaque
        self.btn_export.clicked.connect(self.export_mix)
        self.btn_export.setEnabled(False)
        controls_layout.addWidget(self.btn_export)
        
        main_layout.addWidget(controls_card)

        # Card para os sliders de volume
        sliders_card = QFrame()
        sliders_card.setObjectName("Card")
        sliders_layout = QVBoxLayout(sliders_card)
        sliders_layout.setSpacing(10)

        # Slider de Voz
        sliders_layout.addWidget(QLabel("🎤 Volume da Voz:"))
        self.slider_voz = QSlider(Qt.Orientation.Horizontal)
        self.slider_voz.setRange(0, 100)
        self.slider_voz.setValue(100)
        self.slider_voz.valueChanged.connect(self.update_volumes)
        sliders_layout.addWidget(self.slider_voz)

        # Slider de Fundo (Instrumentos)
        sliders_layout.addWidget(QLabel("🎸 Volume do Fundo Musical:"))
        self.slider_fundo = QSlider(Qt.Orientation.Horizontal)
        self.slider_fundo.setRange(0, 100)
        self.slider_fundo.setValue(100)
        self.slider_fundo.valueChanged.connect(self.update_volumes)
        sliders_layout.addWidget(self.slider_fundo)

        main_layout.addWidget(sliders_card)
        main_layout.addStretch() # Empurra tudo para cima e alinha melhor

    def load_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Abrir Mídia", "", "Media Files (*.mp3 *.mp4 *.wav)")
        if file_path:
            self.lbl_status.setText("Preparando arquivo...")
            self.btn_load.setEnabled(False)
            self.btn_export.setEnabled(False)
            
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

            self.lbl_status.setText("Processando IA (isso pode levar alguns minutos)...")
            
            subprocess.run(["demucs", "--two-stems=vocals", file_path], check=True)
            
            output_dir = os.path.join("separated", "htdemucs", base_name)
            self.voz_path = os.path.join(output_dir, "vocals.wav")
            self.fundo_path = os.path.join(output_dir, "no_vocals.wav")

            self.sound_voz = pygame.mixer.Sound(self.voz_path)
            self.sound_fundo = pygame.mixer.Sound(self.fundo_path)

            self.lbl_status.setText(f"Pronto: {base_name.replace('_extracted', '')}")
            self.btn_play.setEnabled(True)
            self.btn_export.setEnabled(True)
            self.btn_load.setEnabled(True)

        except Exception as e:
            self.lbl_status.setText("Erro ao processar o arquivo.")
            print(e)
            self.btn_load.setEnabled(True)

    def toggle_play(self):
        if self.voz_channel.get_busy() or self.fundo_channel.get_busy():
            pygame.mixer.pause()
        else:
            if self.sound_voz and self.sound_fundo:
                self.voz_channel.play(self.sound_voz)
                self.fundo_channel.play(self.sound_fundo)
                self.update_volumes()
            else:
                pygame.mixer.unpause()

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