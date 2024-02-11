#!/bin/bash

function ajustar_data {
  file=$1
  hours=$2

  # Se o arquivo tiver a data de criação maior que a data de modificação, define a data de criação como a data de modificação
  if [[ $(GetFileInfo -d "$file") > $(GetFileInfo -m "$file") ]]; then
    modification_date=$(stat -f%Sm -t "%m/%d/%Y %H:%M:%S" "$file")
    SetFile -d "$modification_date" "$file"
  fi
  

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

# Abrir um prompt para escolher quantas horas vai ajustar
hours=$(osascript -e 'display dialog "Quantas horas deseja ajustar?" default answer "-3"')

# Abrir um prompt para escolher o nome do arquivo
filepattern=$(osascript -e 'display dialog "Qual o nome do arquivo?" default answer "pocket-*"')

# Obtém o valor após textreturned:
hours=$(echo $hours | sed 's/.*text returned://')

# Obtém o valor após textreturned:
filepattern=$(echo $filepattern | sed 's/.*text returned://')

echo "Horas: $hours"

echo "Padrão: $filepattern"

# Itera sobre os arquivos na pasta que começam com "filepattern-"
for file in "$folder"/$filepattern; do
  ajustar_data "$file" $hours
  # Imprime que a data foi ajustada
  echo "$file ajustada."
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