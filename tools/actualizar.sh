#!/bin/sh
# Actualiza la app a la última versión y comprueba que quedó aplicada.
#
#   sh tools/actualizar.sh
#
# Existe porque «git pull» solo no basta: el código del backend va DENTRO de
# la imagen de Docker, así que hace falta reconstruirla. Sin el «--build», los
# contenedores siguen corriendo la versión anterior aunque los archivos del
# disco ya estén nuevos, y no lo dice nada: los comandos nuevos simplemente
# "no existen".

set -u

cd "$(dirname "$0")/.." || exit 1

echo
echo "── 1. Traer los cambios ──────────────────────────"

ANTES=$(git rev-parse --short HEAD 2>/dev/null)
if ! git pull; then
    echo
    echo "  ✗ No se pudieron traer los cambios."
    echo "    Si dice que tienes cambios locales sin guardar, mándame lo que"
    echo "    salió: hay que decidir qué se conserva antes de seguir."
    exit 1
fi
DESPUES=$(git rev-parse --short HEAD 2>/dev/null)

if [ "$ANTES" = "$DESPUES" ]; then
    echo "  Ya estabas en la última versión ($DESPUES)."
else
    echo "  ✓ De $ANTES a $DESPUES."
fi

echo
echo "── 2. Reconstruir y levantar ─────────────────────"
echo "  La primera vez tarda varios minutos. Es normal."
echo

if ! docker compose up -d --build; then
    echo
    echo "  ✗ La reconstrucción falló. Los contenedores siguen corriendo la"
    echo "    versión ANTERIOR: la app no se ha roto, pero tampoco se ha"
    echo "    actualizado. Mándame las últimas líneas de aquí arriba."
    exit 1
fi

echo
echo "── 3. Comprobar que quedó aplicada ───────────────"

# Se espera a que la API vuelva a responder antes de preguntarle nada.
INTENTO=0
while [ "$INTENTO" -lt 30 ]; do
    if docker compose exec -T api python -c "pass" >/dev/null 2>&1; then
        break
    fi
    INTENTO=$((INTENTO + 1))
    sleep 2
done

if ! docker compose exec -T api python -m app.cli version 2>&1; then
    echo
    echo "  ? No se pudo preguntar a la aplicación. Comprueba que los"
    echo "    contenedores estén arriba:   docker compose ps"
    exit 1
fi

echo "  Si la fecha de construcción es de ahora mismo, ya estás al día."
echo
