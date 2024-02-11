#!/bin/bash

function ajustar_data {
  file=$1
  hours=$2
  # Obtém a data de criação do arquivo
  creation_date=$(GetFileInfo -d "$file")
  formatted_date=$(date -j -f "%m/%d/%Y %H:%M:%S" "$creation_date" "+%Y%m%d%H%M")
  touch -mt $formatted_date "$file"

  # Adiciona a quantidade de horas especificada à data de criação do arquivo
  touch -mt $(date -v${hours}H -r "$file" "+%Y%m%d%H%M") "$file"

  modification_date=$(stat -f%Sm -t "%m/%d/%Y %H:%M:%S" "$file")
  SetFile -d "$modification_date" "$file"
}

# Define a variável com o caminho para a pasta contendo os arquivos
folder=$(osascript -e 'tell application "Finder" to POSIX path of (choose folder)')

# Itera sobre os arquivos na pasta que começam com "pocket-"
for file in "$folder"/camera-*; do
  ajustar_data "$file" -2
done

# NY
# x-pocket3, +14 
# camera, -2

# Seul
# pocket3, +12
# camera, +23
# x-camera, -13
# celular, +12

# Filipinas
# pocket3, +11
# action, +11
# camera, +22
# celular -12

# Macau
# pocket3, +12
# camera, +23
# celular +12