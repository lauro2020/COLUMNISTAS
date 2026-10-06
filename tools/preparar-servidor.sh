#!/bin/sh
# Prepara el .env de un servidor nuevo con claves seguras y te deja listo para
# arrancar. Se corre UNA vez, en el servidor, desde la carpeta del proyecto:
#
#   sh tools/preparar-servidor.sh
#
# No sobrescribe un .env existente.

set -eu
cd "$(dirname "$0")/.."

if [ -f .env ]; then
    echo "Ya existe un .env aquí. No lo toco."
    echo "Si quieres empezar de cero, bórralo a mano y vuelve a correr esto."
    exit 1
fi

command -v openssl >/dev/null 2>&1 || { echo "Falta openssl: apt install -y openssl"; exit 1; }

echo
echo "Dominio con el que vas a entrar (ej. columnistas.duckdns.org)."
echo "Debe apuntar ya a la IP de este servidor."
printf "Dominio: "
read -r DOMINIO
[ -n "$DOMINIO" ] || { echo "Hace falta un dominio."; exit 1; }

echo
echo "Contraseña de la app. Solo letras, números, guion y guion bajo."
echo "Mínimo 8 caracteres: la app va a estar en internet."
printf "Contraseña: "
read -r CLAVE
case "$CLAVE" in
    *[!A-Za-z0-9_-]*|"") echo "Usa solo letras, números, - y _ (sin espacios ni símbolos)."; exit 1 ;;
esac
[ "${#CLAVE}" -ge 8 ] || { echo "Muy corta: mínimo 8 caracteres."; exit 1; }

echo
echo "Clave de OpenAI para el audio (empieza con sk-). Enter para dejarla"
echo "vacía; sin ella no se genera audio hasta que la pongas en el .env."
printf "OPENAI_API_KEY: "
read -r OPENAI
case "$OPENAI" in
    *[!A-Za-z0-9_-]*) echo "La clave trae caracteres raros; pégala a mano en el .env."; OPENAI="" ;;
esac

cp .env.example .env

poner() {  # poner VARIABLE valor  -> reemplaza la línea VARIABLE=... del .env
    sed -i "s|^$1=.*|$1=$2|" .env
}

SECRETO=$(openssl rand -hex 32)
DB_CLAVE=$(openssl rand -hex 16)

poner APP_SECRET_KEY "$SECRETO"
poner APP_PASSWORD "$CLAVE"
poner POSTGRES_PASSWORD "$DB_CLAVE"
poner DATABASE_URL "postgresql+psycopg://columnistas:${DB_CLAVE}@db:5432/columnistas"
[ -n "$OPENAI" ] && poner OPENAI_API_KEY "$OPENAI"
[ -z "$OPENAI" ] && poner OPENAI_API_KEY ""

{
    echo
    echo "# --- Servidor (lo añade tools/preparar-servidor.sh) ---"
    echo "DOMAIN=$DOMINIO"
    echo "COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml"
} >> .env

chmod 600 .env

echo
echo "Listo. .env creado (solo tú puedes leerlo)."
echo
echo "Siguiente paso:"
echo "  docker compose up -d --build"
echo
echo "Cuando termine (la primera vez tarda varios minutos):"
echo "  https://$DOMINIO"
echo
