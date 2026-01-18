import subprocess
import whisper
import sys
import os
import time
import traceback

# Importar componentes Qt necessários
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QIcon, QPalette, QColor
from PyQt5.QtWidgets import (
    QApplication, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog, 
    QWidget, QComboBox, QSpinBox, QSizePolicy, QProgressBar, QGroupBox, 
    QFrame, QMessageBox
)

# --- Estilos (Dark Mode Moderno) ---
STYLESHEET = """
    QWidget {
        background-color: #1e1e1e;
        color: #e0e0e0;
        font-family: 'Segoe UI', 'Roboto', sans-serif;
        font-size: 14px;
    }
    QGroupBox {
        border: 1px solid #3d3d3d;
        border-radius: 6px;
        margin-top: 12px;
        padding-top: 10px;
        font-weight: bold;
        color: #4fa3d1;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 5px;
        left: 10px;
    }
    QPushButton {
        background-color: #333333;
        border: 1px solid #444444;
        border-radius: 4px;
        padding: 8px 15px;
        color: #ffffff;
    }
    QPushButton:hover {
        background-color: #444444;
        border-color: #555555;
    }
    QPushButton:pressed {
        background-color: #222222;
    }
    QPushButton:disabled {
        background-color: #2a2a2a;
        color: #666666;
        border-color: #333333;
    }
    QPushButton#primary {
        background-color: #0078d4;
        border: 1px solid #005a9e;
        font-weight: bold;
        font-size: 15px;
    }
    QPushButton#primary:hover {
        background-color: #106ebe;
    }
    QPushButton#primary:pressed {
        background-color: #005a9e;
    }
    QPushButton#danger {
        background-color: #c42b1c;
        border: 1px solid #a80000;
    }
    QPushButton#danger:hover {
        background-color: #b00020;
    }
    QComboBox, QSpinBox {
        background-color: #2d2d2d;
        border: 1px solid #444444;
        border-radius: 4px;
        padding: 5px;
        color: #ffffff;
    }
    QComboBox::drop-down {
        border: 0px;
    }
    QProgressBar {
        border: 1px solid #444444;
        border-radius: 4px;
        text-align: center;
        background-color: #2d2d2d;
    }
    QProgressBar::chunk {
        background-color: #0078d4;
        border-radius: 3px;
    }
    QLabel#path_label {
        color: #aaaaaa;
        font-style: italic;
        font-size: 12px;
    }
"""

# --- Classe Worker (Lógica em Segundo Plano) ---
class TranscriptionWorker(QThread):
    status_update = pyqtSignal(str)
    progress_update = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def __init__(self, selected_file, srt_save_path, video_save_path, subtitle_type, max_words, process_type, model_size):
        super().__init__()
        self.selected_file = selected_file
        self.srt_save_path = srt_save_path
        self.video_save_path = video_save_path
        self.subtitle_type = subtitle_type
        self.max_words = max_words
        self.process_type = process_type
        self.model_size = model_size
        self._is_running = True

    def run(self):
        try:
            # --- Etapa 1: Carregar Modelo ---
            self.status_update.emit(f"Carregando modelo Whisper '{self.model_size}'...")
            self.progress_update.emit(5)
            
            try:
                model = whisper.load_model(self.model_size)
            except Exception as e:
                self.finished.emit(False, f"Erro ao carregar modelo '{self.model_size}'.\nVerifique se o 'openai-whisper' está atualizado.\nErro: {str(e)}")
                return

            if not self._is_running: return

            # --- Etapa 2: Transcrever Áudio ---
            self.status_update.emit("Transcrevendo áudio... (Isso pode demorar dependendo da GPU/CPU)")
            QApplication.processEvents()
            
            # Nota: O Whisper padrão não fornece callback de progresso nativo facilmente nesta chamada
            # Se fosse o 'faster-whisper', seria mais fácil obter o progresso real da transcrição.
            result = model.transcribe(self.selected_file, word_timestamps=True)
            
            if not self._is_running: return

            # --- Etapa 3: Gerar Arquivo SRT ---
            self.status_update.emit(f"Processando segmentos...")
            total_segments = len(result.get('segments', []))
            
            if total_segments == 0:
                 self.finished.emit(True, f"Concluído. Nenhuma fala detectada. SRT vazio salvo.")
                 return

            with open(self.srt_save_path, "w", encoding='utf-8') as f:
                counter = 1
                for i, segment in enumerate(result['segments']):
                    if not self._is_running: return

                    words_in_segment = segment.get('words', [])
                    if not words_in_segment: continue

                    if self.subtitle_type == "Palavra por palavra":
                        for word_info in words_in_segment:
                            start = word_info['start']
                            end = word_info['end']
                            word = word_info['word']
                            if start >= end: end = start + 0.100
                            f.write(f"{counter}\n")
                            f.write(f"{self.format_timestamp(start)} --> {self.format_timestamp(end)}\n")
                            f.write(f"{word.strip()}\n\n")
                            counter += 1
                    else: # Por frases (agrupado)
                        current_phrase_words = []
                        phrase_start_time = words_in_segment[0]['start']
                        
                        for idx, word_info in enumerate(words_in_segment):
                             # FIX: Remove espaços extras de cada palavra antes de adicionar à lista
                             current_phrase_words.append(word_info['word'].strip())
                             word_end_time = word_info['end']

                             # Lógica de quebra de frase
                             if len(current_phrase_words) >= self.max_words or idx == len(words_in_segment) - 1:
                                 phrase_end_time = word_end_time
                                 if phrase_end_time <= phrase_start_time:
                                      phrase_end_time = phrase_start_time + 0.500
                                 
                                 f.write(f"{counter}\n")
                                 f.write(f"{self.format_timestamp(phrase_start_time)} --> {self.format_timestamp(phrase_end_time)}\n")
                                 # FIX: Junta as palavras com um único espaço limpo
                                 f.write(f"{' '.join(current_phrase_words)}\n\n")
                                 counter += 1

                                 if idx < len(words_in_segment) - 1:
                                      current_phrase_words = []
                                      phrase_start_time = words_in_segment[idx+1]['start']

                    # Atualizar progresso (Simulado para 50-90% durante a escrita, já que a transcrição acabou)
                    progress = 50 + int(((i + 1) / total_segments) * 40)
                    self.progress_update.emit(progress)

            if not self._is_running: return

            # --- Etapa 4: Gerar Vídeo (Opcional) ---
            if self.process_type == "Gerar SRT e Vídeo Legendado":
                self.status_update.emit(f"Renderizando vídeo com FFmpeg...")
                self.progress_update.emit(90)
                QApplication.processEvents()

                ffmpeg_subtitle_path = self.srt_save_path.replace("\\", "/")
                # Escape para Windows no filtro subtitles do ffmpeg
                if sys.platform == "win32":
                    ffmpeg_subtitle_path = ffmpeg_subtitle_path.replace(":", "\\:")

                comando_ffmpeg = [
                    "ffmpeg", "-y", "-i", self.selected_file,
                    "-vf", f"subtitles='{ffmpeg_subtitle_path}'",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "192k",
                    self.video_save_path
                ]

                # Execução do FFmpeg
                process = subprocess.Popen(
                    comando_ffmpeg, 
                    stderr=subprocess.PIPE, 
                    stdout=subprocess.PIPE, 
                    text=True, 
                    encoding='utf-8', 
                    errors='replace'
                )

                while self._is_running:
                     if process.poll() is not None: break
                     time.sleep(0.1)
                     QApplication.processEvents()

                if not self._is_running:
                     process.terminate()
                     self.finished.emit(False, "Cancelado durante a renderização.")
                     return

                if process.returncode != 0:
                     stderr_output = process.stderr.read()
                     raise subprocess.CalledProcessError(process.returncode, comando_ffmpeg, stderr=stderr_output)

            # --- Conclusão ---
            self.progress_update.emit(100)
            msg = f"Sucesso!\nSRT: {os.path.basename(self.srt_save_path)}"
            if self.process_type == "Gerar SRT e Vídeo Legendado":
                msg += f"\nVídeo: {os.path.basename(self.video_save_path)}"
            
            self.finished.emit(True, msg)

        except Exception as e:
            print(traceback.format_exc())
            self.finished.emit(False, f"Erro: {str(e)}")

    def stop(self):
        self._is_running = False

    def format_timestamp(self, seconds_float):
        seconds_float = max(0, seconds_float)
        total_seconds = int(seconds_float)
        milliseconds = int((seconds_float - total_seconds) * 1000)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


# --- Interface Gráfica Principal ---
class SubtitleApp(QWidget):
    def __init__(self):
        super().__init__()
        self.selected_file = None
        self.srt_save_path = None
        self.video_save_path = None
        self.worker = None
        
        self.initUI()
        # Aplicar tema
        self.setStyleSheet(STYLESHEET)

    def initUI(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # --- Título ---
        title_label = QLabel("AI Auto Subtitle Generator")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff; margin-bottom: 5px;")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # --- Grupo 1: Entrada ---
        input_group = QGroupBox("Arquivo de Entrada")
        input_layout = QVBoxLayout()
        
        btn_layout = QHBoxLayout()
        self.file_button = QPushButton("Selecionar Vídeo")
        self.file_button.setCursor(Qt.PointingHandCursor)
        self.file_button.clicked.connect(self.open_file_chooser)
        btn_layout.addWidget(self.file_button)
        
        self.selected_file_display = QLabel("Nenhum arquivo selecionado")
        self.selected_file_display.setObjectName("path_label")
        self.selected_file_display.setWordWrap(True)
        
        input_layout.addLayout(btn_layout)
        input_layout.addWidget(self.selected_file_display)
        input_group.setLayout(input_layout)
        main_layout.addWidget(input_group)

        # --- Grupo 2: Configuração do Modelo (NOVO) ---
        model_group = QGroupBox("Configurações do Modelo AI")
        model_layout = QHBoxLayout()
        
        lbl_model = QLabel("Modelo Whisper:")
        self.model_combo = QComboBox()
        # Adicionando as opções solicitadas
        self.model_combo.addItems(["base", "small", "medium", "large-v3", "turbo"])
        self.model_combo.setCurrentText("small") # Default equilibrado
        self.model_combo.setToolTip("Modelos maiores são mais precisos, mas exigem mais memória e tempo.")

        model_layout.addWidget(lbl_model)
        model_layout.addWidget(self.model_combo)
        model_group.setLayout(model_layout)
        main_layout.addWidget(model_group)

        # --- Grupo 3: Estilo da Legenda ---
        sub_group = QGroupBox("Estilo da Legenda")
        sub_layout = QVBoxLayout()
        
        h_layout_sub = QHBoxLayout()
        self.subtitle_type_combo = QComboBox()
        self.subtitle_type_combo.addItems(["Palavra por palavra", "Frases Completas"])
        self.subtitle_type_combo.setCurrentText("Frases Completas")
        self.subtitle_type_combo.currentIndexChanged.connect(self.toggle_word_limit_option)
        
        h_layout_sub.addWidget(QLabel("Formato:"))
        h_layout_sub.addWidget(self.subtitle_type_combo)
        sub_layout.addLayout(h_layout_sub)

        # Configuração extra para frases
        self.phrase_container = QWidget()
        phrase_layout = QHBoxLayout(self.phrase_container)
        phrase_layout.setContentsMargins(0, 5, 0, 0)
        self.word_limit_spin = QSpinBox()
        self.word_limit_spin.setRange(1, 50)
        self.word_limit_spin.setValue(10)
        phrase_layout.addWidget(QLabel("Máx. palavras por linha:"))
        phrase_layout.addWidget(self.word_limit_spin)
        sub_layout.addWidget(self.phrase_container)
        
        sub_group.setLayout(sub_layout)
        main_layout.addWidget(sub_group)

        # --- Grupo 4: Saída ---
        out_group = QGroupBox("Configuração de Saída")
        out_layout = QVBoxLayout()

        # Tipo de Processamento
        h_proc = QHBoxLayout()
        self.process_type_combo = QComboBox()
        self.process_type_combo.addItems(["Apenas Gerar SRT", "Gerar SRT e Vídeo Legendado"])
        self.process_type_combo.currentIndexChanged.connect(self.toggle_video_save_options)
        h_proc.addWidget(QLabel("Ação:"))
        h_proc.addWidget(self.process_type_combo)
        out_layout.addLayout(h_proc)

        # Botões de Salvar
        self.srt_save_button = QPushButton("Definir local do SRT...")
        self.srt_save_button.clicked.connect(self.select_srt_save_path)
        out_layout.addWidget(self.srt_save_button)
        self.srt_path_display = QLabel("")
        self.srt_path_display.setObjectName("path_label")
        out_layout.addWidget(self.srt_path_display)

        self.video_save_button = QPushButton("Definir local do Vídeo...")
        self.video_save_button.clicked.connect(self.select_video_save_path)
        self.video_save_button.setVisible(False)
        out_layout.addWidget(self.video_save_button)
        self.video_path_display = QLabel("")
        self.video_path_display.setObjectName("path_label")
        self.video_path_display.setVisible(False)
        
        out_group.setLayout(out_layout)
        main_layout.addWidget(out_group)

        # --- Área de Ação e Status ---
        main_layout.addStretch() # Empurra tudo pra cima
        
        self.status_label = QLabel("Aguardando início...")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)
        main_layout.addWidget(self.progress_bar)

        self.process_button = QPushButton("INICIAR TRANSCRIÇÃO")
        self.process_button.setObjectName("primary")
        self.process_button.setMinimumHeight(45)
        self.process_button.setCursor(Qt.PointingHandCursor)
        self.process_button.clicked.connect(self.start_or_cancel_processing)
        self.process_button.setEnabled(False)
        main_layout.addWidget(self.process_button)

        self.setLayout(main_layout)
        self.setWindowTitle("Whisper Subtitle Pro")
        self.resize(500, 750)

    # --- Lógica de UI ---

    def toggle_word_limit_option(self):
        is_phrase = self.subtitle_type_combo.currentText() == "Frases Completas"
        self.phrase_container.setVisible(is_phrase)

    def toggle_video_save_options(self):
        is_video = self.process_type_combo.currentText() == "Gerar SRT e Vídeo Legendado"
        self.video_save_button.setVisible(is_video)
        self.video_path_display.setVisible(is_video)
        self.check_enable_process_button()

    def check_enable_process_button(self):
        if self.worker and self.worker.isRunning():
            self.process_button.setEnabled(True)
            return

        ready = False
        if self.selected_file and self.srt_save_path:
            if self.process_type_combo.currentText() == "Gerar SRT e Vídeo Legendado":
                if self.video_save_path: ready = True
            else:
                ready = True
        
        self.process_button.setEnabled(ready)
        if not ready:
            self.process_button.setText("INICIAR TRANSCRIÇÃO")
            self.process_button.setObjectName("primary")
            self.style().unpolish(self.process_button)
            self.style().polish(self.process_button)

    # --- Seletores de Arquivo ---

    def open_file_chooser(self):
        if self.worker and self.worker.isRunning(): return
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar Vídeo", "", "Vídeos (*.mp4 *.mov *.avi *.mkv *.flv *.mp3 *.wav)")
        if path:
            self.selected_file = path
            self.selected_file_display.setText(os.path.basename(path))
            
            # Resetar saídas
            self.srt_save_path = None
            self.video_save_path = None
            self.srt_path_display.setText("")
            self.video_path_display.setText("")
            
            # Sugerir nomes automaticamente seria uma melhoria UX
            folder = os.path.dirname(path)
            name = os.path.splitext(os.path.basename(path))[0]
            self.srt_save_path = os.path.join(folder, f"{name}.srt")
            self.srt_path_display.setText(f"SRT: {os.path.basename(self.srt_save_path)}")
            
            self.check_enable_process_button()

    def select_srt_save_path(self):
        if self.worker and self.worker.isRunning(): return
        default_name = "legenda.srt"
        if self.selected_file:
            default_name = os.path.splitext(os.path.basename(self.selected_file))[0] + ".srt"
            
        path, _ = QFileDialog.getSaveFileName(self, "Salvar SRT", default_name, "Legenda (*.srt)")
        if path:
            self.srt_save_path = path
            self.srt_path_display.setText(f"SRT: {os.path.basename(path)}")
            self.check_enable_process_button()

    def select_video_save_path(self):
        if self.worker and self.worker.isRunning(): return
        default_name = "video_legendado.mp4"
        if self.selected_file:
             default_name = os.path.splitext(os.path.basename(self.selected_file))[0] + "_subbed.mp4"
             
        path, _ = QFileDialog.getSaveFileName(self, "Salvar Vídeo", default_name, "Vídeo (*.mp4)")
        if path:
            self.video_save_path = path
            self.video_path_display.setText(f"Vídeo: {os.path.basename(path)}")
            self.check_enable_process_button()

    # --- Controle do Processo ---

    def start_or_cancel_processing(self):
        if self.worker and self.worker.isRunning():
            # Cancelar
            self.worker.stop()
            self.process_button.setText("Cancelando...")
            self.process_button.setEnabled(False)
        else:
            # Iniciar
            self.ui_state_processing(True)
            
            # Capturar modelo selecionado
            selected_model = self.model_combo.currentText()
            
            self.worker = TranscriptionWorker(
                selected_file=self.selected_file,
                srt_save_path=self.srt_save_path,
                video_save_path=self.video_save_path,
                subtitle_type=self.subtitle_type_combo.currentText(),
                max_words=self.word_limit_spin.value(),
                process_type=self.process_type_combo.currentText(),
                model_size=selected_model # Passando o modelo escolhido
            )
            
            self.worker.status_update.connect(self.status_label.setText)
            self.worker.progress_update.connect(self.progress_bar.setValue)
            self.worker.finished.connect(self.on_finished)
            self.worker.start()

    def ui_state_processing(self, is_processing):
        # Desabilitar entradas
        self.file_button.setEnabled(not is_processing)
        self.model_combo.setEnabled(not is_processing)
        self.subtitle_type_combo.setEnabled(not is_processing)
        self.srt_save_button.setEnabled(not is_processing)
        self.video_save_button.setEnabled(not is_processing)
        
        if is_processing:
            self.process_button.setText("CANCELAR")
            self.process_button.setObjectName("danger") # Muda cor para vermelho
            self.progress_bar.setValue(0)
        else:
            self.process_button.setText("INICIAR TRANSCRIÇÃO")
            self.process_button.setObjectName("primary") # Volta para azul
        
        # Forçar atualização de estilo do botão
        self.style().unpolish(self.process_button)
        self.style().polish(self.process_button)

    def on_finished(self, success, message):
        self.ui_state_processing(False)
        self.status_label.setText("Pronto" if success else "Erro")
        
        if success:
            QMessageBox.information(self, "Concluído", message)
            self.progress_bar.setValue(100)
        else:
            if "Cancelado" in message:
                self.progress_bar.setValue(0)
                self.status_label.setText("Cancelado pelo usuário")
            else:
                QMessageBox.critical(self, "Erro", message)
                self.progress_bar.setValue(0)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(1000)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Configurar estilo Fusion para garantir que QSS funcione bem em todas plataformas
    app.setStyle("Fusion") 
    window = SubtitleApp()
    window.show()
    sys.exit(app.exec_())