#!/bin/sh
# Imprime la dirección con la que abrir la app desde el teléfono, en el mismo WiFi.
#
#   sh tools/direccion-en-red.sh
#
# Se ejecuta en tu computadora, NO dentro de Docker: es la máquina la que sabe
# qué dirección tiene en la red de tu casa.

set -u

# --- Puerto: el del .env si existe, si no el de por defecto -----------------
PUERTO=8080
if [ -f .env ]; then
    DEL_ENV=$(grep -E '^[[:space:]]*WEB_PORT=' .env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]')
    [ -n "${DEL_ENV:-}" ] && PUERTO="$DEL_ENV"
fi

# --- Dirección en la red local ---------------------------------------------
IP=""
if command -v ipconfig >/dev/null 2>&1; then          # macOS
    for INTERFAZ in en0 en1 en2 en3; do
        IP=$(ipconfig getifaddr "$INTERFAZ" 2>/dev/null) && [ -n "$IP" ] && break
    done
fi
if [ -z "$IP" ] && command -v ip >/dev/null 2>&1; then  # Linux
    IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')
fi
if [ -z "$IP" ] && command -v hostname >/dev/null 2>&1; then
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fi
if [ -z "$IP" ] && command -v ifconfig >/dev/null 2>&1; then
    IP=$(ifconfig 2>/dev/null | awk '/inet /{if ($2 != "127.0.0.1") {print $2; exit}}')
fi

echo
if [ -z "$IP" ]; then
    echo "No se pudo averiguar la dirección de esta computadora en la red."
    echo "Comprueba que estás conectado al WiFi y vuelve a intentarlo."
    exit 1
fi

echo "  Abre esta dirección en el teléfono, conectado al MISMO WiFi:"
echo
echo "      http://$IP:$PUERTO"
echo

# --- ¿Está la app escuchando? -----------------------------------------------
if command -v curl >/dev/null 2>&1; then
    CODIGO=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "http://$IP:$PUERTO/" 2>/dev/null)
    case "$CODIGO" in
        200|30*)
            echo "  ✓ La app responde en esa dirección."
            ;;
        000)
            echo "  ✗ Nada responde ahí. Comprueba que los contenedores estén"
            echo "    arriba:   docker compose ps"
            ;;
        *)
            echo "  ? Respondió con el código $CODIGO. Míralo en el navegador"
            echo "    de esta misma computadora para ver qué dice."
            ;;
    esac
fi

echo
echo "  Recuerda: por una dirección así (sin HTTPS) puedes leer y escuchar,"
echo "  pero el teléfono no dejará instalar la app ni descargar para uso sin"
echo "  conexión. Para eso, ver la sección «Instalar en el teléfono» del README."
echo
echo "  Si el router reinicia, esta dirección puede cambiar: vuelve a"
echo "  ejecutar este comando."
echo
