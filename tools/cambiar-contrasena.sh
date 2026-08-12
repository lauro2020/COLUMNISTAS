#!/bin/sh
# Cambia la contraseña con la que entras a la app, y comprueba que funciona.
#
#   sh tools/cambiar-contrasena.sh
#
# Hace las tres cosas que hay que hacer, en orden:
#   1. la escribe en el archivo .env (guardando antes una copia)
#   2. recrea los contenedores, que es lo ÚNICO que les hace releer ese archivo
#   3. entra en la app con ella, de verdad, para confirmar que sirve

set -u

cd "$(dirname "$0")/.." || exit 1

if [ ! -f .env ]; then
    echo "No encuentro el archivo .env en $(pwd)."
    echo "Créalo copiando el de ejemplo:   cp .env.example .env"
    exit 1
fi

# --- Pedirla dos veces, sin que se vea -------------------------------------
leer_oculta() {
    printf '%s' "$1" >&2
    stty -echo 2>/dev/null
    IFS= read -r RESPUESTA
    stty echo 2>/dev/null
    printf '\n' >&2
}

echo
echo "── Contraseña nueva ──────────────────────────────"
echo
echo "  Que sea de letras, números y guiones. Evita  #  \$  \"  '"
echo "  porque el archivo .env les da un significado propio y la"
echo "  contraseña llegaría cortada o cambiada."
echo

leer_oculta "  Contraseña nueva: "
NUEVA="$RESPUESTA"
leer_oculta "  Otra vez, para confirmar: "
CONFIRMA="$RESPUESTA"

if [ "$NUEVA" != "$CONFIRMA" ]; then
    echo "  ✗ No coinciden. No se ha cambiado nada; vuelve a intentarlo."
    exit 1
fi

# --- Comprobaciones que evitan los tropiezos conocidos ----------------------
case "$NUEVA" in
    "")           echo "  ✗ Está vacía. No se ha cambiado nada."; exit 1 ;;
    *"#"*)        echo "  ✗ Lleva «#». En un .env, todo lo que va después de"
                  echo "    una almohadilla se descarta, así que al contenedor le"
                  echo "    llegaría solo el trozo de antes. Elige otra."; exit 1 ;;
    *'$'*)        echo "  ✗ Lleva «\$». Docker lo entiende como el principio del"
                  echo "    nombre de una variable y lo sustituye. Elige otra."; exit 1 ;;
    *'"'*|*"'"*)  echo "  ✗ Lleva comillas. Se guardarían dentro de la propia"
                  echo "    contraseña sin que se note. Elige otra."; exit 1 ;;
    *\\*)         echo "  ✗ Lleva una barra invertida. Elige otra."; exit 1 ;;
esac

if [ "$NUEVA" != "$(printf '%s' "$NUEVA" | tr -d '[:space:]')" ]; then
    echo "  ✗ Lleva espacios. Son imposibles de ver al teclearla en el"
    echo "    teléfono. Elige otra sin espacios."
    exit 1
fi

if [ "${#NUEVA}" -lt 8 ]; then
    echo "  ✗ Muy corta: al menos 8 caracteres."
    exit 1
fi

# --- Escribirla en el .env --------------------------------------------------
echo
echo "── 1. Guardando en .env ──────────────────────────"

cp .env .env.respaldo || exit 1
echo "  Copia de seguridad: .env.respaldo"

# Se pasa por el entorno, no por la línea de órdenes, para que la contraseña
# no aparezca en la lista de procesos de la máquina.
if ! NUEVA_CONTRASENA="$NUEVA" awk '
    /^[[:space:]]*APP_PASSWORD[[:space:]]*=/ && !hecho {
        print "APP_PASSWORD=" ENVIRON["NUEVA_CONTRASENA"]; hecho=1; next
    }
    { print }
    END { if (!hecho) print "APP_PASSWORD=" ENVIRON["NUEVA_CONTRASENA"] }
' .env.respaldo > .env; then
    echo "  ✗ No se pudo escribir. Se restaura la copia."
    cp .env.respaldo .env
    exit 1
fi
echo "  ✓ Guardada."

# --- Recrear los contenedores ----------------------------------------------
echo
echo "── 2. Aplicando el cambio ────────────────────────"
echo "  («restart» no vale: los contenedores solo leen el .env al crearse)"
echo

if ! docker compose up -d; then
    echo
    echo "  ✗ No se pudieron recrear los contenedores. La contraseña YA está"
    echo "    escrita en el .env, así que en cuanto arreglen esto y ejecutes"
    echo "    «docker compose up -d» quedará aplicada."
    exit 1
fi

# --- Comprobarla de verdad --------------------------------------------------
echo
echo "── 3. Comprobando que sirve ──────────────────────"

PUERTO=$(grep -E '^[[:space:]]*WEB_PORT=' .env 2>/dev/null \
    | tail -1 | cut -d= -f2 | cut -d'#' -f1 | tr -d '[:space:]')
[ -n "${PUERTO:-}" ] || PUERTO=8080

# Se espera a que la API vuelva a estar en pie tras recrearse.
INTENTO=0
while [ "$INTENTO" -lt 30 ]; do
    CODIGO=$(curl -s -o /dev/null -w '%{http_code}' -m 5 \
        "http://localhost:$PUERTO/api/health/live" 2>/dev/null)
    [ "$CODIGO" = "200" ] && break
    INTENTO=$((INTENTO + 1))
    sleep 2
done

RESPUESTA_LOGIN=$(NUEVA_CONTRASENA="$NUEVA" sh -c '
    printf "{\"password\":\"%s\"}" "$NUEVA_CONTRASENA" \
    | curl -s -o /dev/null -w "%{http_code}" -m 10 \
        -X POST "http://localhost:'"$PUERTO"'/api/auth/login" \
        -H "Content-Type: application/json" --data-binary @-
' 2>/dev/null)

echo
if [ "$RESPUESTA_LOGIN" = "200" ]; then
    echo "  ✓ Listo: la app acepta la contraseña nueva."
    echo
    echo "  Ojo con esto: los aparatos donde YA habías entrado siguen dentro."
    echo "  La sesión no depende de la contraseña, así que no se cierra al"
    echo "  cambiarla. La nueva hace falta la próxima vez que alguien entre."
    echo "  Si quieres echar a todos, cambia también APP_SECRET_KEY en el .env"
    echo "  y vuelve a ejecutar «docker compose up -d»."
    rm -f .env.respaldo
else
    echo "  ✗ La app NO la acepta (respondió $RESPUESTA_LOGIN)."
    echo
    echo "    El .env quedó cambiado; tu contraseña anterior está en la copia"
    echo "    .env.respaldo por si quieres volver atrás."
    echo "    Mira qué dice el registro:   docker compose logs --tail 30 api"
    exit 1
fi
echo
