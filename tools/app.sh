#!/bin/sh
# Ejecuta cualquier comando de la app, desde donde estés.
#
#   sh ~/columnistas/tools/app.sh status
#   sh ~/columnistas/tools/app.sh why "riva palacio"
#   sh ~/columnistas/tools/app.sh collect
#   sh ~/columnistas/tools/app.sh            (lista los comandos)
#
# Existe porque «docker compose» busca su archivo de configuración en la
# carpeta donde estás, no donde vive el proyecto. Escribir el comando desde
# otro sitio falla con «no configuration file provided: not found», que no
# dice en ningún momento que el problema sea la carpeta. Este script se va
# solo a la que toca.

set -u

cd "$(dirname "$0")/.." || exit 1

if ! docker info >/dev/null 2>&1; then
    echo
    echo "  ✗ Docker Desktop no está corriendo."
    echo "    Ábrelo y espera a que la ballena de la barra de menús deje de"
    echo "    moverse. Con Docker cerrado no corre nada: ni la web, ni la"
    echo "    recolección de las 6 de la mañana."
    echo
    echo "    Para que arranque solo al encender la computadora:"
    echo "    Docker Desktop › Settings › General › «Start Docker Desktop"
    echo "    when you sign in to your computer»."
    echo
    exit 1
fi

if [ "$#" -eq 0 ]; then
    docker compose exec api python -m app.cli version
    echo "  Úsalos así:   sh $0 status"
    echo
    exit 0
fi

exec docker compose exec api python -m app.cli "$@"
