#!/bin/sh
# Diagnóstico: ¿por qué el teléfono no abre la app?
#
#   sh tools/direccion-en-red.sh
#
# Se ejecuta en tu computadora, NO dentro de Docker: es la máquina la que sabe
# qué dirección tiene en la red de tu casa y qué puertos tiene abiertos.
#
# Revisa, en orden, las cinco cosas que tienen que estar bien para que el
# teléfono llegue, y al final imprime la dirección que hay que abrir.

set -u

cd "$(dirname "$0")/.." || exit 1

OK="  ✓"
MAL="  ✗"
DUDA="  ?"
PROBLEMAS=0

falla() {
    PROBLEMAS=$((PROBLEMAS + 1))
}

titulo() {
    echo
    echo "── $1 ──────────────────────────────"
}

# =============================================================================
# 1. Puerto configurado
# =============================================================================
PUERTO=8080
if [ -f .env ]; then
    DEL_ENV=$(grep -E '^[[:space:]]*WEB_PORT=' .env 2>/dev/null \
        | tail -1 | cut -d= -f2 | cut -d'#' -f1 | tr -d '[:space:]')
    [ -n "${DEL_ENV:-}" ] && PUERTO="$DEL_ENV"
fi

titulo "1. Puerto"
echo "$OK La app debería estar en el puerto $PUERTO."

# =============================================================================
# 2. ¿Están los contenedores arriba?
# =============================================================================
titulo "2. Contenedores"

if ! command -v docker >/dev/null 2>&1; then
    echo "$MAL Docker no está instalado o no está en el PATH."
    falla
elif ! docker info >/dev/null 2>&1; then
    echo "$MAL Docker no está corriendo."
    echo "    Abre Docker Desktop y espera a que la ballena deje de moverse."
    falla
else
    ESTADO=$(docker compose ps --format '{{.Service}} {{.State}}' 2>/dev/null)
    if [ -z "$ESTADO" ]; then
        echo "$MAL No hay ningún contenedor levantado."
        echo "    Arráncalos con:   docker compose up -d"
        falla
    else
        WEB=$(echo "$ESTADO" | awk '$1=="web"{print $2}')
        API=$(echo "$ESTADO" | awk '$1=="api"{print $2}')
        case "$WEB" in
            running) echo "$OK El contenedor «web» (la página) está corriendo." ;;
            "")      echo "$MAL El contenedor «web» no existe. Ejecuta: docker compose up -d"; falla ;;
            *)       echo "$MAL El contenedor «web» está «$WEB», no «running»."
                     echo "    Mira por qué:   docker compose logs --tail 30 web"
                     falla ;;
        esac
        case "$API" in
            running) echo "$OK El contenedor «api» (los datos) está corriendo." ;;
            "")      echo "$MAL El contenedor «api» no existe. Ejecuta: docker compose up -d"; falla ;;
            *)       echo "$MAL El contenedor «api» está «$API», no «running»."
                     echo "    Mira por qué:   docker compose logs --tail 30 api"
                     falla ;;
        esac

        # ¿En qué dirección publicó Docker el puerto?
        PUBLICADO=$(docker compose port web 80 2>/dev/null)
        case "$PUBLICADO" in
            0.0.0.0:*|"[::]:"*|:::*)
                echo "$OK El puerto está abierto a toda la red ($PUBLICADO)." ;;
            127.0.0.1:*|localhost:*)
                echo "$MAL El puerto solo está abierto para esta computadora"
                echo "    ($PUBLICADO). Por eso el teléfono no llega."
                echo "    En docker-compose.yml, el puerto de «web» debe ser"
                echo "    \"\${WEB_PORT:-8080}:80\", sin 127.0.0.1 delante."
                falla ;;
            "")
                echo "$DUDA No se pudo leer el puerto publicado del contenedor «web»." ;;
            *)
                echo "$OK Puerto publicado en $PUBLICADO." ;;
        esac
    fi
fi

# =============================================================================
# 3. ¿Hay algo escuchando en ese puerto?
# =============================================================================
titulo "3. Escucha en el puerto $PUERTO"

ESCUCHA=""
if command -v lsof >/dev/null 2>&1; then
    ESCUCHA=$(lsof -nP -iTCP:"$PUERTO" -sTCP:LISTEN 2>/dev/null | tail -n +2)
elif command -v ss >/dev/null 2>&1; then
    ESCUCHA=$(ss -ltnp 2>/dev/null | grep ":$PUERTO ")
fi

if [ -n "$ESCUCHA" ]; then
    echo "$OK Sí, hay un programa escuchando en el $PUERTO."
    QUIEN=$(echo "$ESCUCHA" | awk '{print $1}' | sort -u | tr '\n' ' ')
    case "$QUIEN" in
        *ocker*|*com.doc*|*vpnkit*|*nginx*) ;;
        *) echo "$DUDA Lo ocupa: $QUIEN"
           echo "    Si no es Docker, ese programa le está robando el puerto a"
           echo "    la app. Cámbiale el puerto a la app poniendo otro valor en"
           echo "    WEB_PORT dentro de .env (por ejemplo 8090) y luego:"
           echo "    docker compose up -d" ;;
    esac
else
    echo "$MAL Nadie escucha en el puerto $PUERTO."
    echo "    Casi siempre es porque los contenedores no están arriba, o"
    echo "    porque otro programa ya tenía ese puerto y Docker no pudo"
    echo "    quedárselo. Ejecuta:   docker compose up -d"
    falla
fi

# =============================================================================
# 4. Cortafuegos de macOS
# =============================================================================
FW=/usr/libexec/ApplicationFirewall/socketfilterfw
if [ -x "$FW" ]; then
    titulo "4. Cortafuegos de macOS"

    GLOBAL=$("$FW" --getglobalstate 2>/dev/null)
    BLOQUEO=$("$FW" --getblockall 2>/dev/null)
    SIGILO=$("$FW" --getstealthmode 2>/dev/null)

    case "$GLOBAL" in
        *"enabled"*|*"activado"*|*"habilitado"*)
            echo "$DUDA El cortafuegos está ENCENDIDO."
            case "$BLOQUEO" in
                *"on"*|*"activado"*)
                    echo "$MAL Y además está en «bloquear todas las conexiones"
                    echo "    entrantes». Con eso el teléfono NO puede llegar."
                    echo "    Ajustes del Sistema › Red › Firewall › Opciones ›"
                    echo "    desactiva «Bloquear todas las conexiones entrantes»."
                    falla ;;
                *)
                    echo "    Comprueba que Docker tenga permiso:"
                    echo "    Ajustes del Sistema › Red › Firewall › Opciones ›"
                    echo "    «Docker Desktop» debe decir «Permitir conexiones"
                    echo "    entrantes». Si no aparece en la lista, añádelo con +"
                    echo "    desde Aplicaciones." ;;
            esac
            case "$SIGILO" in
                *"enabled"*|*"on"*|*"activado"*)
                    echo "$DUDA El «modo encubierto» está activo. No bloquea la"
                    echo "    app, pero hace que la Mac no responda a ping, así"
                    echo "    que no te fíes de esa prueba." ;;
            esac ;;
        *)
            echo "$OK El cortafuegos está apagado: no está estorbando." ;;
    esac
fi

# =============================================================================
# 5. Direcciones de esta computadora en la red
# =============================================================================
titulo "5. Dirección para el teléfono"

# Se juntan todas las direcciones IPv4 de todas las interfaces y luego se
# descartan las que no sirven: la de loopback, las de Docker y las de las
# redes virtuales (VPN, máquinas virtuales), que el teléfono no puede alcanzar.
CANDIDATAS=""
if command -v ifconfig >/dev/null 2>&1; then
    CANDIDATAS=$(ifconfig 2>/dev/null | awk '/inet /{print $2}')
fi
if [ -z "$CANDIDATAS" ] && command -v ip >/dev/null 2>&1; then
    CANDIDATAS=$(ip -4 -o addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
fi
if [ -z "$CANDIDATAS" ] && command -v hostname >/dev/null 2>&1; then
    CANDIDATAS=$(hostname -I 2>/dev/null)
fi

# La que macOS usa de verdad para salir a internet va primero: es la del WiFi.
PREFERIDA=""
if command -v route >/dev/null 2>&1; then
    IFAZ=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
    if [ -n "${IFAZ:-}" ] && command -v ipconfig >/dev/null 2>&1; then
        PREFERIDA=$(ipconfig getifaddr "$IFAZ" 2>/dev/null)
    fi
fi
if [ -z "$PREFERIDA" ] && command -v ip >/dev/null 2>&1; then
    PREFERIDA=$(ip -4 route get 1.1.1.1 2>/dev/null \
        | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')
fi

BUENAS=""
OTRAS=""
for IP in $PREFERIDA $CANDIDATAS; do
    case "$IP" in
        127.*|169.254.*) continue ;;          # loopback y "sin red"
        172.1[6-9].*|172.2[0-9].*|172.3[01].*) continue ;;  # rangos de Docker
    esac
    case "$IP" in
        192.168.*|10.*)
            case " $BUENAS " in *" $IP "*) continue ;; esac
            BUENAS="$BUENAS $IP" ;;
        *)
            # Redes de casa poco habituales: se guardan por si no hay ninguna
            # de las normales, para no dejar al usuario sin dirección.
            case " $OTRAS " in *" $IP "*) continue ;; esac
            OTRAS="$OTRAS $IP" ;;
    esac
done
[ -z "$BUENAS" ] && BUENAS="$OTRAS"

if [ -z "$BUENAS" ]; then
    echo "$MAL Esta computadora no tiene dirección en ninguna red local."
    echo "    Conéctala al WiFi de tu casa y vuelve a ejecutar esto."
    falla
else
    for IP in $BUENAS; do
        CODIGO=000
        if command -v curl >/dev/null 2>&1; then
            CODIGO=$(curl -s -o /dev/null -w '%{http_code}' -m 5 \
                "http://$IP:$PUERTO/" 2>/dev/null)
        fi
        case "$CODIGO" in
            200|30*) MARCA="$OK responde" ;;
            000)     MARCA="$MAL no responde" ;;
            *)       MARCA="$DUDA responde con el código $CODIGO" ;;
        esac
        echo
        echo "      http://$IP:$PUERTO"
        echo "$MARCA"
    done
    PRIMERA=$(echo "$BUENAS" | awk '{print $1}')
fi

# =============================================================================
# Resumen
# =============================================================================
echo
echo "══════════════════════════════════════════════════════"
if [ "$PROBLEMAS" -gt 0 ]; then
    echo "  Hay $PROBLEMAS cosa(s) que arreglar aquí arriba (las marcadas ✗)."
    echo "  Arréglalas y vuelve a ejecutar este comando."
else
    echo "  Por parte de la computadora, todo está bien."
    if [ -n "${PRIMERA:-}" ]; then
        echo
        echo "  En el teléfono, escribe la dirección COMPLETA, con http://"
        echo "  delante, en la barra del navegador:"
        echo
        echo "      http://$PRIMERA:$PUERTO"
    fi
fi
echo "══════════════════════════════════════════════════════"

cat <<'FIN'

  Si aquí sale todo ✓ y aun así el teléfono no abre, es cosa del teléfono
  o del router. Comprueba, en este orden:

  1. Escribe la dirección con «http://» delante. Sin eso, el navegador
     del teléfono la toma como una búsqueda, o intenta «https://» y falla.

  2. Apaga los datos móviles un momento, para obligar al teléfono a usar
     el WiFi.

  3. Apaga cualquier VPN en el teléfono. Una VPN encendida saca el tráfico
     de tu casa y ya no encuentra la computadora.

  4. Que sea el MISMO WiFi. Muchos routers dan dos redes con nombres
     parecidos (una acaba en «5G» o «_5GHz»): a veces no se ven entre
     ellas. La red «de invitados» casi nunca deja ver a las demás; si estás
     en ella, cámbiate a la principal.

  5. Prueba primero en el navegador de la propia computadora con esa misma
     dirección http://... Si ahí sí abre y en el teléfono no, el problema
     está entre el router y el teléfono, no en la app.

  Ojo: la comprobación de arriba se hace desde la propia computadora, y ese
  camino no pasa por el cortafuegos. Que diga «responde» no garantiza que el
  teléfono llegue; por eso hay que revisar también los puntos 1 a 5.

  Por una dirección así (sin HTTPS) puedes leer y escuchar, pero el teléfono
  no dejará instalar la app ni descargar para uso sin conexión. Para eso, ver
  «Instalar en el teléfono» en el README (la opción de Tailscale).

  La dirección puede cambiar al reiniciar el router: si un día deja de abrir,
  vuelve a ejecutar este comando.
FIN
