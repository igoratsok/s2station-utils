#!/bin/bash

# Solicita ao usuário para selecionar múltiplas pastas
folders=$(osascript -e 'tell application "Finder" to set folderList to choose folder with multiple selections allowed' \
                     -e 'set output to ""' \
                     -e 'repeat with f in folderList' \
                     -e 'set output to output & POSIX path of f & "\n"' \
                     -e 'end repeat' \
                     -e 'return output')

# Converte a lista de pastas em um array
IFS=$'\n' read -d '' -r -a folder_array <<< "$folders"

# Loop através de cada pasta selecionada
for folder in "${folder_array[@]}"; do
    # Cria os diretórios 360, Videos e Fotos se eles não existirem
    mkdir -p "$folder/360" "$folder/Videos" "$folder/Fotos" "$folder/LRF"

    # Move todos os arquivos que começam com "360-" para o diretório 360
    mv "$folder/360-"* "$folder/360/"

    # Move todos os arquivos *.LRF para o diretório LRF
    mv "$folder"/*.LRF "$folder/LRF/"

    # Move todos os arquivos de vídeo para o diretório Videos
    for file in "$folder"/*; do
        if [[ $file == *.mov || $file == *.mp4 || $file == *.MP4 ]]; then
            mv "$file" "$folder/Videos/"
        fi
    done

    # Move todos os arquivos de foto para o diretório Fotos
    for file in "$folder"/*; do
        if [[ $file == *.jpg || $file == *.jpeg || $file == *.JPG || $file == *.JPEG || $file == *.HEIC  || $file == *.heic  ]]; then
            mv "$file" "$folder/Fotos/"
        fi
    done

    # Mostra uma janela de seleção de pasta
    foldervideos="$folder/Videos"

    echo "A pasta de vídeos: $foldervideos"

    # Cria a pasta "Shorts" se ela ainda não existir
    if [ ! -d "$foldervideos/Shorts" ]; then
      mkdir "$foldervideos/Shorts"
    fi

    # Percorre todos os arquivos de vídeo (*.mp4 ou *.MP4) na pasta
    # Identifica os arquivos de vídeo que estão na vertical e move para a pasta Shorts
    find "$foldervideos" -maxdepth 1 -type f -name "*.MP4" -o -name "*.mp4" -o -name "*.mov" -o -name "*.avi" -o -name "*.wmv" -o -name "*.flv" -o -name "*.mkv" -o -name "*.webm" | while read -r file; do
      
      height=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=s=x:p=0 "$file")
      width=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=s=x:p=0 "$file")

      echo "$file: $width x $height"

      # Verifica se o height é maior que o width
      if [ "$height" -gt  "$width" ]; then
        mv "$file" "$foldervideos/Shorts"
      fi

      # Verifica se a variável height termina com "x"
      if [[ $height == *x ]]; then
        mv "$file" "$foldervideos/Shorts"
      fi
    done

    echo "Os arquivos de vídeo na vertical foram movidos para a pasta Shorts."
done
