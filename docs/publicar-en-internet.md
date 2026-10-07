# Publicar la app en internet (para usarla desde el teléfono y la tablet)

Resultado: entras a `https://tu-dominio` desde cualquier dispositivo, con una
contraseña, y la instalas como app. La recolección de las 6:00 corre sola, con
tu computadora apagada.

La app necesita una máquina virtual (VPS) con Docker encendida 24/7: tiene base
de datos, cola de trabajos, recolector y generador de audio. No cabe en hostings
de páginas estáticas (Vercel, Netlify, GitHub Pages).

## Qué contratar

| Concepto | Recomendación | Costo aproximado |
|---|---|---|
| Servidor | Hetzner Cloud, plan CX23 (2 vCPU, 4 GB RAM), ubicación Alemania o Finlandia | 5–6 EUR/mes (verifica el precio al contratar: ha cambiado varias veces en 2026) |
| Dominio | Subdominio gratuito de DuckDNS (`algo.duckdns.org`) o dominio propio | 0 / ~10–15 USD al año |
| Audio (voz) | OpenAI `gpt-4o-mini-tts` (ya configurado en la app) | Por uso; revisa tu consumo actual |

Por qué Hetzner: es el más barato con memoria suficiente para correr los seis
contenedores. 2 GB de RAM se quedan cortos al generar audio y compilar la web.

Riesgo a vigilar: algunos medios bloquean IPs de centros de datos. Hetzner está
en Europa, y Reforma y Milenio ya ponen trabas con navegadores no comunes.
**Después de instalar, corre una recolección y revisa el diagnóstico** (paso 6).
Si un medio responde 403 desde el servidor y desde tu casa no, el remedio es
cambiar de proveedor a uno con IP en Estados Unidos o México, no tocar la app.

## Paso a paso

### 1. Crear el servidor
1. Crea cuenta en Hetzner Cloud y un proyecto nuevo.
2. Crear servidor: Ubuntu 24.04, CX23, Alemania o Finlandia. Activa IPv4 pública.
3. Autenticación: llave SSH (recomendado) o contraseña por correo.
4. Anota la IP pública.

### 2. Apuntar un dominio a la IP
- DuckDNS: entra a duckdns.org, crea un subdominio (por ejemplo
  `columnistas-lauro.duckdns.org`) y pega la IP del servidor.
- Dominio propio: crea un registro `A` con la IP.

### 3. Preparar el servidor
Conéctate (`ssh root@IP`) y corre:

```bash
curl -fsSL https://get.docker.com | sh
ufw allow 22 && ufw allow 80 && ufw allow 443 && ufw --force enable
git clone -b claude/exciting-carson-wl6a0s https://github.com/lauro2020/COLUMNISTAS.git columnistas
cd columnistas
sh tools/preparar-servidor.sh
```

El asistente te pide el dominio, la contraseña y la clave de OpenAI, y genera
las claves internas al azar. Para la contraseña usa solo letras, números, `-` y
`_`, mínimo 8 caracteres. Es una contraseña "sencilla", pero la app queda
abierta a internet: la app bloquea 15 minutos tras 10 intentos fallidos, y aun
así una contraseña corta o común es el punto débil. Evita `columnistas123`.

### 4. Arrancar

```bash
docker compose up -d --build
```

La primera vez tarda varios minutos. Después abre `https://tu-dominio`. El
certificado HTTPS lo obtiene Caddy solo (el dominio debe apuntar ya al
servidor; si no, tarda en funcionar).

### 5. Pasar tus datos de la computadora (opcional)
Si quieres conservar lo ya recopilado y tus ajustes:

En tu computadora, desde la carpeta del proyecto:
```bash
docker compose exec -T db pg_dump -U columnistas columnistas > respaldo.sql
scp respaldo.sql root@IP:~/columnistas/
```

En el servidor:
```bash
cd ~/columnistas
docker compose stop api worker beat
docker compose exec -T db psql -U columnistas columnistas < respaldo.sql
docker compose start api worker beat
```
El respaldo no trae los MP3; se regeneran desde el texto (botón de audio en cada
artículo). Si la app estaba en pausa en tu computadora, la pausa viaja en el
respaldo: reanúdala con `sh tools/app.sh pause --reanudar`.

Si prefieres empezar limpio, sáltate este paso: la app crea sus columnistas
iniciales al arrancar.

### 6. Comprobar que recolecta desde el servidor

```bash
sh tools/app.sh collect
sh tools/app.sh status
```

Revisa que no haya fuentes marcadas como degradadas por bloqueos (403).

### 7. Instalar en el teléfono y la tablet
- iPhone/iPad: Safari, abrir `https://tu-dominio`, entrar con la contraseña,
  botón Compartir, "Agregar a pantalla de inicio". Debe ser Safari; Chrome en
  iPhone no instala la app.
- Android: Chrome, menú de tres puntos, "Instalar app".

## Mantenimiento

```bash
cd ~/columnistas
git pull && docker compose up -d --build          # actualizar
sh tools/cambiar-contrasena.sh                    # cambiar contraseña
docker compose exec -T db pg_dump -U columnistas columnistas > respaldo.sql   # respaldo
```

Haz el respaldo de vez en cuando: el servidor es la única copia de tu base de
datos. Hetzner ofrece respaldos automáticos del servidor completo por un
porcentaje adicional del precio.
