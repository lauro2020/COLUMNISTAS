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

# --- Antes que nada: ¿está Docker en marcha? --------------------------------
# Sin esto, el fallo aparece más adelante disfrazado de error de descarga de
# imágenes, y el mensaje que sigue habla de reconstrucciones cuando lo único
# que hace falta es abrir una aplicación.
echo
echo "── 0. ¿Está Docker en marcha? ────────────────────"

if ! command -v docker >/dev/null 2>&1; then
    echo "  ✗ Docker no está instalado, o no está en el PATH."
    echo "    Descárgalo de https://www.docker.com/products/docker-desktop/"
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "  ✗ Docker Desktop no está corriendo."
    echo
    echo "    Ábrelo (Aplicaciones › Docker) y espera a que el icono de la"
    echo "    ballena, arriba en la barra de menús, deje de moverse."
    echo "    Después vuelve a ejecutar este comando."
    echo
    echo "    Mientras Docker esté cerrado NO hay nada corriendo: ni la app,"
    echo "    ni la recolección de las 6 de la mañana. Es también lo que hay"
    echo "    detrás de un «no se puede conectar con el servidor» en la web."
    exit 1
fi

echo "  ✓ Docker está en marcha."

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
    echo "  ✗ La reconstrucción falló."
    # Docker pudo pararse a mitad. Solo se puede decir «sigue corriendo lo
    # anterior» si de verdad hay algo corriendo.
    if docker compose ps --status running 2>/dev/null | grep -q .; then
        echo "    Lo que ya estaba en pie sigue funcionando con la versión"
        echo "    anterior: la app no se ha roto, pero tampoco se ha actualizado."
    else
        echo "    Y no hay ningún contenedor en pie, así que la app está parada."
    fi
    echo "    Mándame las últimas líneas de aquí arriba."
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

if docker compose exec -T api python -m app.cli version 2>&1; then
    echo "  Si la fecha de construcción es de ahora mismo, ya estás al día."
    echo
    exit 0
fi

# --- No contesta: hay que decir por qué, no solo que no contesta -------------
echo
echo "  ✗ La aplicación no contesta. Esto es lo que le pasa:"
echo
echo "── Estado de cada contenedor ─────────────────────"
docker compose ps

echo
echo "── Últimas líneas del registro de «api» ──────────"
echo "  (el motivo del fallo suele ser la ÚLTIMA línea)"
echo
docker compose logs --tail 40 --no-color api 2>&1

echo
echo "── Espacio en disco ──────────────────────────────"
# Quedarse sin disco es una causa habitual y despista mucho, porque el error
# que sale no habla de disco: la imagen con navegador headless pesa ~2 GB y
# cada reconstrucción deja atrás la anterior.
docker system df 2>/dev/null | head -5
echo
echo "  Si «Images» ocupa muchos GB y te queda poco disco, libera lo viejo:"
echo "      docker system prune -a -f"
echo "  (borra imágenes sin usar; NO toca tus artículos ni tu base de datos,"
echo "   que viven en volúmenes aparte)"

echo
echo "  Manda todo lo de arriba y te digo qué es."
echo
exit 1
