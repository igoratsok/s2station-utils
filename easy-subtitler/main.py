import subprocess
import whisper
import sys
import os
import time # Para pequenos delays se necessário
import traceback # Para logs de erro detalhados

# Importar componentes Qt necessários
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QVBoxLayout, QPushButton, QLabel, QFileDialog, QWidget,
    QComboBox, QSpinBox, QSizePolicy, QProgressBar # Adicionar QProgressBar
)

# --- Classe Worker para Executar Tarefas em Segundo Plano ---
class TranscriptionWorker(QThread):
    # Sinais para comunicação com a thread principal (UI)
    status_update = pyqtSignal(str)       # Atualiza a mensagem de status
    progress_update = pyqtSignal(int)     # Atualiza a barra de progresso (0-100)
    finished = pyqtSignal(bool, str)      # Indica conclusão (sucesso/falha, mensagem final)
    enable_ui = pyqtSignal(bool)          # Habilita/desabilita a UI

    def __init__(self, selected_file, srt_save_path, video_save_path, subtitle_type, max_words, process_type, model_size="turbo"):
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
            self.progress_update.emit(0) # Progresso inicial
            model = whisper.load_model(self.model_size)
            if not self._is_running: return # Verifica se foi cancelado

            # --- Etapa 2: Transcrever Áudio ---
            # Esta é a parte longa e sem progresso detalhado do Whisper
            self.status_update.emit("Transcrevendo áudio... (Esta etapa pode demorar)")
            QApplication.processEvents() # Garante que a mensagem apareça
            # Pedir timestamps para melhor geração SRT
            result = model.transcribe(self.selected_file, word_timestamps=True)
            if not self._is_running: return

            # --- Etapa 3: Gerar Arquivo SRT ---
            self.status_update.emit(f"Gerando arquivo SRT: {self.srt_save_path}")
            total_segments = len(result.get('segments', []))
            if total_segments == 0:
                 self.status_update.emit("Aviso: Nenhuma legenda detectada.")
                 # Considera sucesso, mas avisa
                 self.finished.emit(True, f"Concluído. Nenhuma legenda detectada. SRT vazio salvo em {self.srt_save_path}")
                 return

            with open(self.srt_save_path, "w", encoding='utf-8') as f:
                counter = 1
                for i, segment in enumerate(result['segments']):
                    if not self._is_running: return # Permite cancelar durante a escrita

                    words_in_segment = segment.get('words', [])
                    if not words_in_segment: continue # Pula segmentos sem palavras

                    if self.subtitle_type == "Palavra por palavra":
                        for word_info in words_in_segment:
                            start = word_info['start']
                            end = word_info['end']
                            word = word_info['word']
                            if start >= end: end = start + 0.100 # Duração mínima
                            f.write(f"{counter}\n")
                            f.write(f"{self.format_timestamp(start)} --> {self.format_timestamp(end)}\n")
                            f.write(f"{word.strip()}\n\n")
                            counter += 1
                    else: # Por frases
                        current_phrase_words = []
                        phrase_start_time = words_in_segment[0]['start']
                        for idx, word_info in enumerate(words_in_segment):
                             current_phrase_words.append(word_info['word'])
                             word_end_time = word_info['end']

                             if len(current_phrase_words) == self.max_words or idx == len(words_in_segment) - 1:
                                 phrase_end_time = word_end_time
                                 if phrase_end_time <= phrase_start_time:
                                      phrase_end_time = phrase_start_time + 0.500
                                 f.write(f"{counter}\n")
                                 f.write(f"{self.format_timestamp(phrase_start_time)} --> {self.format_timestamp(phrase_end_time)}\n")
                                 f.write(f"{' '.join(current_phrase_words).strip()}\n\n")
                                 counter += 1

                                 if idx < len(words_in_segment) - 1:
                                      current_phrase_words = []
                                      phrase_start_time = words_in_segment[idx+1]['start']

                    # Atualizar progresso baseado nos segmentos processados
                    progress = int(((i + 1) / total_segments) * 100)
                    self.progress_update.emit(progress)
                    # time.sleep(0.005) # Pequeno delay para visualização (opcional)

            if not self._is_running: return

            # --- Etapa 4: Gerar Vídeo (Opcional) ---
            if self.process_type == "Gerar SRT e vídeo legendado":
                self.status_update.emit(f"Embutindo legendas no vídeo: {self.video_save_path}")
                self.progress_update.emit(0) # Resetar progresso para FFmpeg (difícil de medir)
                QApplication.processEvents()

                ffmpeg_subtitle_path = self.srt_save_path.replace("\\", "/")
                if sys.platform == "win32":
                    ffmpeg_subtitle_path = ffmpeg_subtitle_path.replace(":", "\\:")

                comando_ffmpeg = [
                    "ffmpeg", "-y", "-i", self.selected_file,
                    "-vf", f"subtitles='{ffmpeg_subtitle_path}'",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k",
                    self.video_save_path
                ]

                print(f"Executando FFmpeg: {' '.join(comando_ffmpeg)}")
                process = subprocess.Popen(comando_ffmpeg, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')

                # Tentar ler stderr para progresso (muito dependente da versão do FFmpeg)
                # Esta parte é experimental e pode não funcionar bem
                while self._is_running:
                     line = process.stderr.readline()
                     if not line:
                         break
                     print(f"FFmpeg stderr: {line.strip()}") # Log para debug
                     # Tentar extrair progresso se possível (ex: frame= ou time=)
                     # Exemplo simples (pode precisar de regex mais robusto)
                     # if "time=" in line:
                     #     # Extrair tempo e calcular % (requer duração total)
                     #     pass
                     QApplication.processEvents() # Mantém UI minimamente responsiva

                process.wait() # Espera o processo terminar
                if not self._is_running:
                     process.terminate() # Tenta parar o FFmpeg se o usuário cancelar
                     self.status_update.emit("Processo FFmpeg cancelado.")
                     self.finished.emit(False, "Cancelado durante a codificação do vídeo.")
                     return

                if process.returncode != 0:
                     stderr_output = process.stderr.read()
                     raise subprocess.CalledProcessError(process.returncode, comando_ffmpeg, stderr=stderr_output)

                self.status_update.emit("Vídeo legendado gerado com sucesso!")
                self.progress_update.emit(100) # Indicar conclusão do FFmpeg

            # --- Conclusão ---
            if self._is_running:
                 final_message = f"Processo concluído! SRT salvo em: {self.srt_save_path}"
                 if self.process_type == "Gerar SRT e vídeo legendado":
                      final_message += f"\nVídeo salvo em: {self.video_save_path}"
                 self.progress_update.emit(100)
                 self.finished.emit(True, final_message)

        except subprocess.CalledProcessError as e:
            error_details = f"Erro no FFmpeg (código {e.returncode}): {e.stderr}"
            print(f"Erro FFmpeg:\nComando: {' '.join(e.cmd)}\nErro: {e.stderr}")
            self.finished.emit(False, error_details[:500]) # Limita tamanho
        except FileNotFoundError as e:
             # Exemplo: FFmpeg não encontrado
             error_details = f"Erro: Arquivo ou programa não encontrado. {e}"
             print(error_details)
             self.finished.emit(False, error_details)
        except Exception as e:
            error_details = f"Erro inesperado: {traceback.format_exc()}"
            print(error_details)
            self.finished.emit(False, f"Erro inesperado: {str(e)}")

    def stop(self):
        self._is_running = False
        self.status_update.emit("Cancelando...")

    def format_timestamp(self, seconds_float):
        # Função movida para dentro da classe ou pode ser mantida fora
        assert seconds_float >= 0, "Timestamp não pode ser negativo"
        total_seconds = int(seconds_float)
        milliseconds = int((seconds_float - total_seconds) * 1000)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


# --- Classe Principal da Aplicação ---
class SubtitleApp(QWidget):
    def __init__(self):
        super().__init__()
        self.selected_file = None
        self.srt_save_path = None
        self.video_save_path = None
        self.worker = None # Referência para a thread de trabalho
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # ... (Widgets de seleção de arquivo, SRT, vídeo, opções - como antes) ...
        # --- Seleção de Arquivo de Entrada ---
        self.file_label = QLabel("1. Selecione um arquivo de vídeo:")
        layout.addWidget(self.file_label)
        self.file_button = QPushButton("Escolher Arquivo de Vídeo")
        self.file_button.clicked.connect(self.open_file_chooser)
        layout.addWidget(self.file_button)
        self.selected_file_display = QLabel("Nenhum arquivo selecionado.")
        self.selected_file_display.setWordWrap(True)
        layout.addWidget(self.selected_file_display)

        # --- Definição do Caminho de Saída SRT ---
        self.srt_path_label = QLabel("2. Defina onde salvar o arquivo de legenda (.srt):")
        layout.addWidget(self.srt_path_label)
        self.srt_save_button = QPushButton("Salvar Legenda Como...")
        self.srt_save_button.clicked.connect(self.select_srt_save_path)
        layout.addWidget(self.srt_save_button)
        self.srt_save_path_display = QLabel("Arquivo SRT não definido.")
        self.srt_save_path_display.setWordWrap(True)
        layout.addWidget(self.srt_save_path_display)

        # --- Opção de Tipo de Legenda ---
        self.subtitle_type_label = QLabel("3. Escolha o tipo de legenda:")
        layout.addWidget(self.subtitle_type_label)
        self.subtitle_type_combo = QComboBox()
        self.subtitle_type_combo.addItem("Palavra por palavra")
        self.subtitle_type_combo.addItem("Por frases")
        self.subtitle_type_combo.currentIndexChanged.connect(self.toggle_word_limit_option)
        layout.addWidget(self.subtitle_type_combo)
        self.word_limit_label = QLabel("Máximo de palavras por frase:")
        self.word_limit_label.setVisible(False)
        layout.addWidget(self.word_limit_label)
        self.word_limit_spin = QSpinBox()
        self.word_limit_spin.setRange(1, 50)
        self.word_limit_spin.setValue(10)
        self.word_limit_spin.setVisible(False)
        layout.addWidget(self.word_limit_spin)

        # --- Opção de Tipo de Processamento ---
        self.process_type_label = QLabel("4. Escolha o tipo de processamento:")
        layout.addWidget(self.process_type_label)
        self.process_type_combo = QComboBox()
        self.process_type_combo.addItem("Gerar apenas SRT")
        self.process_type_combo.addItem("Gerar SRT e vídeo legendado")
        self.process_type_combo.currentIndexChanged.connect(self.toggle_video_save_options)
        layout.addWidget(self.process_type_combo)

        # --- Definição do Caminho de Saída do Vídeo ---
        self.video_path_label = QLabel("5. Defina onde salvar o vídeo legendado:")
        self.video_path_label.setVisible(False)
        layout.addWidget(self.video_path_label)
        self.video_save_button = QPushButton("Salvar Vídeo Legendado Como...")
        self.video_save_button.clicked.connect(self.select_video_save_path)
        self.video_save_button.setVisible(False)
        layout.addWidget(self.video_save_button)
        self.video_save_path_display = QLabel("Arquivo de vídeo não definido.")
        self.video_save_path_display.setWordWrap(True)
        self.video_save_path_display.setVisible(False)
        layout.addWidget(self.video_save_path_display)

        # --- Barra de Progresso ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True) # Mostra a porcentagem
        layout.addWidget(self.progress_bar)

        # --- Botão de Processar / Cancelar ---
        self.process_button = QPushButton("Gerar")
        self.process_button.clicked.connect(self.start_or_cancel_processing) # Modificado
        self.process_button.setEnabled(False)
        self.process_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.process_button)

        # --- Rótulo de Status ---
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        layout.addStretch(1)
        self.setLayout(layout)
        self.setWindowTitle("Gerador de Legendas com Progresso")
        self.resize(450, 650) # Ajustar tamanho se necessário


    # --- Métodos para Seleção de Arquivos e Opções (semelhantes aos anteriores) ---
    def toggle_word_limit_option(self):
        is_phrase = self.subtitle_type_combo.currentText() == "Por frases"
        self.word_limit_label.setVisible(is_phrase)
        self.word_limit_spin.setVisible(is_phrase)

    def toggle_video_save_options(self):
        is_video_output = self.process_type_combo.currentText() == "Gerar SRT e vídeo legendado"
        self.video_path_label.setVisible(is_video_output)
        self.video_save_button.setVisible(is_video_output)
        self.video_save_path_display.setVisible(is_video_output)
        self.check_enable_process_button()

    def open_file_chooser(self):
        if self.worker and self.worker.isRunning(): return # Não permite mudar se estiver processando
        file_path, _ = QFileDialog.getOpenFileName(self, "Selecione o vídeo", "", "Vídeos (*.mp4 *.mov *.avi *.mkv *.flv)")
        if file_path:
            self.selected_file = file_path
            self.selected_file_display.setText(f"Arquivo: {file_path}")
            self.srt_save_path = None
            self.video_save_path = None
            self.srt_save_path_display.setText("Arquivo SRT não definido.")
            self.video_save_path_display.setText("Arquivo de vídeo não definido.")
            self.status_label.setText("")
            self.progress_bar.setValue(0)
            self.check_enable_process_button()

    def select_srt_save_path(self):
        if self.worker and self.worker.isRunning(): return
        suggested_name = "legenda.srt"
        default_dir = os.path.dirname(self.selected_file) if self.selected_file else ""
        if self.selected_file:
             base_name = os.path.splitext(os.path.basename(self.selected_file))[0]
             suggested_name = os.path.join(default_dir, f"{base_name}.srt")

        srt_path, _ = QFileDialog.getSaveFileName(self, "Salvar Arquivo SRT", suggested_name, "Arquivos de Legenda (*.srt)")
        if srt_path:
            if not srt_path.lower().endswith(".srt"): srt_path += ".srt"
            self.srt_save_path = srt_path
            self.srt_save_path_display.setText(f"Salvar SRT em: {srt_path}")
            self.check_enable_process_button()

    def select_video_save_path(self):
        if self.worker and self.worker.isRunning(): return
        suggested_name = "video_legendado.mp4"
        default_dir = os.path.dirname(self.selected_file) if self.selected_file else ""
        if self.selected_file:
            base_name = os.path.splitext(os.path.basename(self.selected_file))[0]
            suggested_name = os.path.join(default_dir, f"{base_name}-legendado.mp4")

        video_path, _ = QFileDialog.getSaveFileName(self, "Salvar Vídeo Legendado", suggested_name, "Arquivos de Vídeo (*.mp4 *.avi *.mkv)")
        if video_path:
             if '.' not in os.path.basename(video_path): video_path += ".mp4"
             self.video_save_path = video_path
             self.video_save_path_display.setText(f"Salvar vídeo em: {video_path}")
             self.check_enable_process_button()

    def check_enable_process_button(self):
        # Só habilita se não estiver rodando E as condições forem atendidas
        if self.worker and self.worker.isRunning():
             self.process_button.setEnabled(True) # Habilitado para Cancelar
             return

        can_process = False
        if self.selected_file and self.srt_save_path:
            if self.process_type_combo.currentText() == "Gerar SRT e vídeo legendado":
                if self.video_save_path: can_process = True
            else:
                can_process = True
        self.process_button.setEnabled(can_process)
        if not can_process:
             self.process_button.setText("Gerar")


    # --- Métodos para Gerenciamento do Processamento ---
    def start_or_cancel_processing(self):
        if self.worker and self.worker.isRunning():
            # --- Cancelar Processo ---
            print("Tentando cancelar o processo...")
            self.worker.stop()
            self.process_button.setText("Cancelando...")
            self.process_button.setEnabled(False) # Desabilita temporariamente
        else:
            # --- Iniciar Processo ---
            # Validações extras
            if not self.selected_file or not self.srt_save_path:
                self.status_label.setText("Erro: Verifique as seleções de arquivo e SRT.")
                return
            if self.process_type_combo.currentText() == "Gerar SRT e vídeo legendado" and not self.video_save_path:
                 self.status_label.setText("Erro: Defina onde salvar o vídeo.")
                 return

            print("Iniciando processo...")
            self.set_ui_processing_state(True) # Desabilita UI, muda botão para Cancelar

            # Criar e iniciar a thread worker
            self.worker = TranscriptionWorker(
                selected_file=self.selected_file,
                srt_save_path=self.srt_save_path,
                video_save_path=self.video_save_path,
                subtitle_type=self.subtitle_type_combo.currentText(),
                max_words=self.word_limit_spin.value(),
                process_type=self.process_type_combo.currentText(),
                # model_size="base" # Pode adicionar opção para escolher modelo
            )

            # Conectar sinais da worker aos slots da UI
            self.worker.status_update.connect(self.update_status_label)
            self.worker.progress_update.connect(self.update_progress_bar)
            self.worker.finished.connect(self.on_processing_finished)
            # self.worker.enable_ui.connect(self.set_ui_enabled) # Alternativa

            self.worker.start()

    def set_ui_processing_state(self, processing):
        """ Configura a UI para estado de processamento ou normal """
        self.file_button.setEnabled(not processing)
        self.srt_save_button.setEnabled(not processing)
        self.subtitle_type_combo.setEnabled(not processing)
        self.process_type_combo.setEnabled(not processing)
        self.word_limit_spin.setEnabled(not processing)
        is_video_output = self.process_type_combo.currentText() == "Gerar SRT e vídeo legendado"
        self.video_save_button.setEnabled(not processing and is_video_output)

        if processing:
            self.process_button.setText("Cancelar")
            self.process_button.setEnabled(True) # Habilitado para cancelar
            self.status_label.setText("Iniciando...")
            self.progress_bar.setValue(0)
        else:
            self.process_button.setText("Gerar")
            self.worker = None # Limpa referência da worker
            self.check_enable_process_button() # Reavalia se pode gerar


    # --- Slots para Receber Sinais da Worker Thread ---
    def update_status_label(self, message):
        self.status_label.setText(message)

    def update_progress_bar(self, value):
        self.progress_bar.setValue(value)

    def on_processing_finished(self, success, message):
        print(f"Processo finalizado. Sucesso: {success}, Mensagem: {message}")
        self.status_label.setText(message)
        self.progress_bar.setValue(100 if success else 0) # Vai pra 100% ou zera no erro/cancelamento
        self.set_ui_processing_state(False) # Reabilita a UI

    def closeEvent(self, event):
         # Garante que a thread pare se a janela for fechada
         if self.worker and self.worker.isRunning():
              print("Fechando janela, solicitando parada da thread...")
              self.worker.stop()
              # Espera um pouco para a thread tentar parar
              self.worker.wait(1000) # Espera até 1 segundo
         event.accept()


# --- Ponto de Entrada Principal ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SubtitleApp()
    window.show()
    sys.exit(app.exec_())