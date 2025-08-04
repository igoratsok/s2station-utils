import json
import tkinter as tk
from tkinter import filedialog, messagebox

def filter_trello_and_save(json_file_path, search_terms, output_json_path):
    """
    Lê um arquivo JSON do Trello, filtra as listas e cartões com base
    nas palavras-chave e salva o resultado em um novo arquivo JSON.
    """
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return "Erro: Arquivo de entrada não encontrado."
    except json.JSONDecodeError:
        return "Erro: Não foi possível decodificar o JSON. Verifique o formato do arquivo."
    except Exception as e:
        return f"Ocorreu um erro ao ler o arquivo: {e}"

    filtered_lists = []
    filtered_list_ids = set()
    
    # Prepara os termos de busca (remove espaços em branco e converte para minúsculas)
    search_terms_clean = [term.strip().lower() for term in search_terms]

    # Encontra listas que contêm qualquer um dos termos de pesquisa em seu nome
    for lst in data.get('lists', []):
        list_name_lower = lst.get('name', '').lower()
        for term in search_terms_clean:
            if term in list_name_lower:
                filtered_lists.append(lst)
                filtered_list_ids.add(lst['id'])
                break

    if not filtered_lists:
        return f"Nenhuma lista encontrada contendo os termos: {', '.join(search_terms)}"

    # Filtra os cartões que pertencem às listas selecionadas
    filtered_cards = [
        card for card in data.get('cards', [])
        if card.get('idList') in filtered_list_ids
    ]

    result_json = {
        'name': f"Filtrado - {data.get('name', 'Quadro Trello')}",
        'desc': f"Visualização filtrada para listas contendo: {', '.join(search_terms)}",
        'lists': filtered_lists,
        'cards': filtered_cards,
    }

    try:
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(result_json, f, ensure_ascii=False, indent=4)
        return f"Arquivo filtrado criado com sucesso em:\n{output_json_path}"
    except Exception as e:
        return f"Ocorreu um erro ao salvar o arquivo de saída: {e}"

# --- Funções da Interface Gráfica ---

def select_input_file():
    """Abre uma caixa de diálogo para selecionar o arquivo de entrada."""
    file_path = filedialog.askopenfilename(
        title="Selecione o arquivo JSON do Trello",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
    )
    if file_path:
        entry_input.delete(0, tk.END)
        entry_input.insert(0, file_path)

def select_output_file():
    """Abre uma caixa de diálogo para definir o arquivo de saída."""
    file_path = filedialog.asksaveasfilename(
        title="Salvar arquivo JSON filtrado como...",
        defaultextension=".json",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
    )
    if file_path:
        entry_output.delete(0, tk.END)
        entry_output.insert(0, file_path)

def run_filter():
    """Executa o processo de filtragem com os dados da interface."""
    input_path = entry_input.get()
    output_path = entry_output.get()
    keywords = entry_keywords.get()

    if not input_path or not output_path or not keywords:
        messagebox.showwarning("Campos Vazios", "Por favor, preencha todos os campos antes de executar.")
        return

    keyword_list = [kw.strip() for kw in keywords.split(',')]
    
    result_message = filter_trello_and_save(input_path, keyword_list, output_path)
    
    if "sucesso" in result_message:
        messagebox.showinfo("Processo Concluído", result_message)
    else:
        messagebox.showerror("Erro", result_message)


# --- Configuração da Janela Principal ---

root = tk.Tk()
root.title("Filtro de JSON do Trello")
root.geometry("500x250") # Largura x Altura
root.resizable(False, False)

frame = tk.Frame(root, padx=10, pady=10)
frame.pack(expand=True, fill=tk.BOTH)

# --- Widgets da Interface ---

# 1. Arquivo de Entrada
lbl_input = tk.Label(frame, text="Arquivo JSON de Entrada:")
lbl_input.grid(row=0, column=0, sticky="w", pady=(0, 5))

entry_input = tk.Entry(frame, width=50)
entry_input.grid(row=1, column=0, sticky="ew")

btn_input = tk.Button(frame, text="Procurar...", command=select_input_file)
btn_input.grid(row=1, column=1, padx=(5, 0))

# 2. Palavras-chave
lbl_keywords = tk.Label(frame, text="Palavras-chave (separadas por vírgula):")
lbl_keywords.grid(row=2, column=0, sticky="w", pady=(10, 5))

entry_keywords = tk.Entry(frame, width=50)
entry_keywords.grid(row=3, column=0, columnspan=2, sticky="ew")

# 3. Arquivo de Saída
lbl_output = tk.Label(frame, text="Arquivo de Saída:")
lbl_output.grid(row=4, column=0, sticky="w", pady=(10, 5))

entry_output = tk.Entry(frame, width=50)
entry_output.grid(row=5, column=0, sticky="ew")

btn_output = tk.Button(frame, text="Salvar como...", command=select_output_file)
btn_output.grid(row=5, column=1, padx=(5, 0))

# 4. Botão de Execução
btn_run = tk.Button(frame, text="Executar Filtro", bg="#4CAF50", fg="white", font=('Helvetica', 10, 'bold'), command=run_filter)
btn_run.grid(row=6, column=0, columnspan=2, pady=(20, 0), ipady=5, sticky="ew")


# Configura o grid para expandir corretamente
frame.columnconfigure(0, weight=1)

# Inicia a aplicação
root.mainloop()