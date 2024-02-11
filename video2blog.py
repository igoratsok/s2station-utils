import tkinter as tk
from tkinter import scrolledtext
import re
import unicodedata

def gerar_id(cabecalho):
    # Normalizar e remover acentos de caracteres especiais
    cabecalho = unicodedata.normalize('NFD', cabecalho)  # Decompor caracteres acentuados
    cabecalho = ''.join([c for c in cabecalho if unicodedata.category(c) != 'Mn'])  # Remover os acentos

    # Remover tudo que não for letra, número ou espaço
    cabecalho = re.sub(r'[^a-zA-Z0-9\s_]', '', cabecalho)  # Remove caracteres especiais não-latinos
    cabecalho = cabecalho.replace(' ', '_')  # Substitui espaços por underscores
    return cabecalho.lower()  # Converte para minúsculas

def processar_texto():
    texto_entrada = texto_entrada_box.get("1.0", tk.END).strip()

    resultado = ""
    indice = []

    # Processar regex customizadas
    regras = []
    for linha in lista_regras.get("1.0", tk.END).split("\n"):
        if linha.strip():
            try:
                regex, heading = linha.split(",")
                regras.append((regex.strip(), int(heading.strip())))
            except ValueError:
                continue

    # Adicionar uma regra padrão para linhas que terminam com "?"
    regras.append((r'.*\?$', 4))  # Essa regra transforma qualquer linha que termina com "?" em um heading 4

    # Processar texto
    for linha in texto_entrada.split("\n"):
        if not linha.strip():  # Ignorar linhas vazias
            continue

        if linha.startswith("#INDICE#"):
            resultado += linha
        # Checar as regras personalizadas
        matched = False
        for regex, heading in regras:
            if re.match(regex, linha.strip()):
                resultado += f'<!-- wp:heading {{ "level": {heading} }} -->\n<h{heading} class="wp-block-heading" id="{gerar_id(linha)}">{linha}</h{heading}>\n<!-- /wp:heading -->\n'
                indice.append(f'<!-- wp:list-item -->\n<li><a href="#{gerar_id(linha)}">{linha}</a></li>\n<!-- /wp:list-item -->')
                matched = True
                break
        # Caso não tenha encontrado nenhuma correspondência, trata como parágrafo
        if not matched:
            resultado += f'<!-- wp:paragraph -->\n<p>{linha}</p>\n<!-- /wp:paragraph -->\n'

    # Criar o índice com wp:list e a classe wp-block-list
    indice_html = "<!-- wp:list -->\n<ul class=\"wp-block-list\">\n" + ''.join(indice) + "</ul>\n<!-- /wp:list -->\n"
    
    # Adicionar título "Índice" antes da lista
    indice_html = "<!-- wp:heading {\"level\":3} -->\n<h3 class=\"wp-block-heading\">Índice</h3>\n<!-- /wp:heading -->\n" + indice_html
    
    # Substitui #INDICE# pelo índice gerado
    resultado = resultado.replace("#INDICE#", indice_html)

    # Colocar o resultado na caixa de saída
    texto_saida_box.delete("1.0", tk.END)
    texto_saida_box.insert(tk.END, resultado)

# Configuração da janela principal
janela = tk.Tk()
janela.title("Conversor de Texto para Gutenberg Wordpress")

# Caixa de entrada de texto
texto_entrada_label = tk.Label(janela, text="Texto de Entrada:")
texto_entrada_label.pack(pady=5)

texto_entrada_box = scrolledtext.ScrolledText(janela, width=60, height=15)
texto_entrada_box.pack(pady=10)

# Caixa para inserir regras de regex
regras_label = tk.Label(janela, text="Regras de Regex (regex, heading):")
regras_label.pack(pady=5)

lista_regras = scrolledtext.ScrolledText(janela, width=60, height=5)
lista_regras.pack(pady=10)
lista_regras.insert(tk.END, "Dia.*, 3\n^\\d+\\.\\s.*, 4")  # Exemplos de regex e heading (pode adicionar novos)

# Caixa de saída de texto
texto_saida_label = tk.Label(janela, text="Resultado (Gutenberg):")
texto_saida_label.pack(pady=5)

texto_saida_box = scrolledtext.ScrolledText(janela, width=60, height=15)
texto_saida_box.pack(pady=10)

# Botão para processar
processar_btn = tk.Button(janela, text="Processar Texto", command=processar_texto)
processar_btn.pack(pady=10)

# Rodar a interface
janela.mainloop()
