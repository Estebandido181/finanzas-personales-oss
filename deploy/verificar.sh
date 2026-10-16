#!/usr/bin/env bash
# Verifica el despliegue de Finanzas personales en la VM (ítem 07).
#
# Uso (en la VM, como root):
#     sudo bash /opt/finanzas/deploy/verificar.sh tu-subdominio.duckdns.org
#
# Imprime ✔ o ✘ por cada comprobación y termina con código 1 si alguna falla
# (2 si falta el dominio o no se ejecuta como root). Nunca imprime secretos:
# de los archivos .env solo mira permisos y, de finanzas.env, las líneas
# COOKIE_SECURE y GMAIL_TOKEN (que no son secretas), sin mostrarlas.

set -uo pipefail  # sin -e: una comprobación fallida no detiene las demás

# Rutas del despliegue (las de deploy/GUIA.md). Se pueden cambiar con
# variables de entorno solo para pruebas.
ETC_DIR="${ETC_DIR:-/etc/finanzas}"
DATOS_DIR="${DATOS_DIR:-/var/lib/finanzas}"
RESPALDOS_DIR="${RESPALDOS_DIR:-/var/backups/finanzas}"
APP_DIR="${APP_DIR:-/opt/finanzas}"
PUERTO_APP=8000
PUERTOS_PUBLICOS_PERMITIDOS=" 22 80 443 "

DOMINIO="${1:-}"
if [[ -z "$DOMINIO" ]]; then
    echo "Uso: sudo bash deploy/verificar.sh tu-subdominio.duckdns.org" >&2
    exit 2
fi
if [[ ! "$DOMINIO" =~ ^[A-Za-z0-9.-]+$ ]]; then
    echo "El dominio solo puede tener letras, números, puntos y guiones." >&2
    exit 2
fi
if [[ "${EUID}" -ne 0 ]]; then
    echo "Ejecútalo con sudo: necesita leer permisos de /etc/finanzas y los puertos de todos los procesos." >&2
    exit 2
fi

fallos=0
bien() { printf '✔ %s\n' "$1"; }
mal() {
    printf '✘ %s\n' "$1"
    [[ -n "${2:-}" ]] && printf '    → %s\n' "$2"
    fallos=$((fallos + 1))
}

# Imprime "usuario:grupo modo" de un archivo (o nada si no existe).
permisos() { stat -c '%U:%G %a' -- "$1" 2>/dev/null; }

comprobar_permisos() {  # descripción, ruta, esperado ("usuario:grupo modo")
    local actual
    actual="$(permisos "$2")"
    if [[ -z "$actual" ]]; then
        mal "$1: no existe" "revisa la guía, paso de secretos o de preparar la VM"
    elif [[ "$actual" == "$3" ]]; then
        bien "$1: $3"
    else
        mal "$1: es $actual, debería ser $3" "corrige con chown y chmod (ver deploy/GUIA.md)"
    fi
}

# Valor de la última línea VARIABLE=... de un archivo .env (como systemd,
# gana la última). Solo para variables no secretas.
valor_env() {
    grep -E "^[[:space:]]*$1=" -- "$2" 2>/dev/null | tail -n 1 | sed -E "s/^[[:space:]]*$1=//; s/[[:space:]]+$//; s/^\"(.*)\"$/\1/"
}

echo "== Servicios y temporizadores"
for unidad in finanzas.service caddy.service; do
    if systemctl is-active --quiet "$unidad" && systemctl is-enabled --quiet "$unidad"; then
        bien "$unidad activo y habilitado"
    else
        mal "$unidad no está activo o no está habilitado" "sudo systemctl enable --now $unidad; journalctl -u ${unidad%.service} -n 50"
    fi
done
for unidad in finanzas-sync.timer finanzas-respaldo.timer duckdns.timer; do
    if systemctl is-active --quiet "$unidad" && systemctl is-enabled --quiet "$unidad"; then
        bien "$unidad activo y habilitado"
    else
        mal "$unidad no está activo o no está habilitado" "sudo systemctl enable --now $unidad"
    fi
done

echo "== Última sincronización"
fin_sync="$(systemctl show -p ExecMainExitTimestampMonotonic --value finanzas-sync.service 2>/dev/null)"
estado_sync="$(systemctl show -p ExecMainStatus --value finanzas-sync.service 2>/dev/null)"
if [[ -z "$fin_sync" || "$fin_sync" == "0" ]]; then
    mal "finanzas-sync todavía no se ha ejecutado desde el último arranque" "sudo systemctl start finanzas-sync.service"
elif [[ "$estado_sync" == "0" ]]; then
    bien "la última ejecución de finanzas-sync terminó con código 0"
else
    mal "la última ejecución de finanzas-sync terminó con código ${estado_sync:-desconocido}" \
        "journalctl -u finanzas-sync -n 50 (1: falló algún correo o Gmail; 2: falta configuración o autorización)"
fi

echo "== Respaldo"
hoy="$(date +%F)"
ayer="$(date -d yesterday +%F)"
respaldo=""
for dia in "$hoy" "$ayer"; do
    if [[ -s "$RESPALDOS_DIR/finanzas-$dia.db" ]]; then
        respaldo="$RESPALDOS_DIR/finanzas-$dia.db"
        break
    fi
done
if [[ -n "$respaldo" ]]; then
    bien "existe el respaldo $(basename "$respaldo")"
    comprobar_permisos "permisos del respaldo" "$respaldo" "finanzas:finanzas 600"
else
    mal "no hay respaldo de hoy ni de ayer en $RESPALDOS_DIR" "sudo systemctl start finanzas-respaldo.service; journalctl -u finanzas-respaldo -n 20"
fi

echo "== HTTPS (en /app/, la app; ítem 20)"
cabeceras="$(curl --silent --show-error --max-time 20 -o /dev/null -D - "https://$DOMINIO/app/" 2>/dev/null | tr -d '\r')"
codigo="$(printf '%s\n' "$cabeceras" | awk 'toupper($1) ~ /^HTTP\// { c = $2 } END { print c }')"
if [[ "$codigo" == "200" ]]; then
    bien "https://$DOMINIO/app/ responde 200"
else
    mal "https://$DOMINIO/app/ no responde 200 (respondió: ${codigo:-nada})" \
        "503: falta compilar el frontend (13.2); si no, revisa DuckDNS, los puertos 80/443, journalctl -u caddy -n 50 y journalctl -u finanzas -n 50"
fi
tiene_cabecera() { printf '%s\n' "$cabeceras" | grep -Eiq "$1"; }
if tiene_cabecera '^strict-transport-security:[[:space:]]*max-age=[1-9]'; then
    bien "lleva HSTS (Strict-Transport-Security)"
else
    mal "falta HSTS (Strict-Transport-Security)" "revisa /etc/caddy/Caddyfile"
fi
csp="$(printf '%s\n' "$cabeceras" | grep -Ei '^content-security-policy:' | head -n 1)"
if [[ -z "$csp" ]]; then
    mal "falta Content-Security-Policy" "¿la respuesta viene de la app? revisa reverse_proxy en el Caddyfile"
elif [[ "$csp" == *"script-src 'self';"* && "$csp" == *"style-src 'self';"* && "$csp" != *unsafe-* ]]; then
    bien "/app lleva la CSP estricta (script-src y style-src solo 'self')"
else
    mal "/app no lleva la CSP estricta" "¿la respuesta viene de la app? revisa reverse_proxy en el Caddyfile"
fi
if tiene_cabecera '^cache-control:.*no-store'; then
    bien "lleva Cache-Control: no-store"
else
    mal "falta Cache-Control: no-store"
fi

redireccion="$(curl --silent --max-time 20 -o /dev/null -w '%{http_code} %{redirect_url}' "http://$DOMINIO/" 2>/dev/null)"
codigo_http="${redireccion%% *}"
destino_http="${redireccion#* }"
if [[ "$codigo_http" =~ ^30[1278]$ && "$destino_http" == https://* ]]; then
    bien "http://$DOMINIO redirige a https ($codigo_http)"
else
    mal "http://$DOMINIO no redirige a https (respondió: ${codigo_http:-nada})" "¿está abierto el puerto 80?"
fi

echo "== La app (/app, ítems 12, 18 y 20)"
if [[ -s "$APP_DIR/frontend/dist/index.html" ]]; then
    bien "el frontend está compilado (frontend/dist)"
else
    mal "el frontend no está compilado: falta $APP_DIR/frontend/dist/index.html" \
        "compílalo con los pasos de deploy/GUIA.md, 13.2 (npm ci y npm run build)"
fi

# / (la dirección de la v1) lleva a /app/ con una redirección temporal (nunca 301).
raiz="$(curl --silent --max-time 20 -o /dev/null -w '%{http_code} %{redirect_url}' "https://$DOMINIO/" 2>/dev/null)"
codigo_raiz="${raiz%% *}"
destino_raiz="${raiz#* }"
if [[ "$codigo_raiz" =~ ^30[237]$ && "$destino_raiz" == "https://$DOMINIO/app/" ]]; then
    bien "https://$DOMINIO/ lleva a /app/ ($codigo_raiz)"
else
    mal "https://$DOMINIO/ no redirige a /app/ (respondió: ${codigo_raiz:-nada})" \
        "¿está desplegada la versión del ítem 20? journalctl -u finanzas -n 50"
fi

# La API sin sesión: 401 en JSON (nunca datos ni una redirección).
api_sesion="$(curl --silent --max-time 20 -o /dev/null -w '%{http_code} %{content_type}' "https://$DOMINIO/api/sesion" 2>/dev/null)"
codigo_api="${api_sesion%% *}"
tipo_api="${api_sesion#* }"
if [[ "$codigo_api" == "401" && "$tipo_api" == application/json* ]]; then
    bien "GET /api/sesion sin sesión responde 401 en JSON"
else
    mal "GET /api/sesion sin sesión no responde 401 en JSON (respondió: ${codigo_api:-nada})" \
        "si responde 200, la API no está exigiendo sesión: revisa la versión desplegada y journalctl -u finanzas -n 50"
fi

# Lo que necesita la app instalada en el celular (PWA, ítem 18).
for archivo in manifest.webmanifest sw.js; do
    codigo_archivo="$(curl --silent --max-time 20 -o /dev/null -w '%{http_code}' "https://$DOMINIO/app/$archivo" 2>/dev/null)"
    if [[ "$codigo_archivo" == "200" ]]; then
        bien "/app/$archivo responde 200"
    else
        mal "/app/$archivo no responde 200 (respondió: ${codigo_archivo:-nada})" \
            "la app instalada lo necesita: compila el frontend (deploy/GUIA.md, 13.2)"
    fi
done

echo "== Red"
escuchas_app="$(ss -ltnH "sport = :$PUERTO_APP" 2>/dev/null | awk '{ print $4 }')"
if [[ -z "$escuchas_app" ]]; then
    mal "nada escucha en el puerto $PUERTO_APP" "journalctl -u finanzas -n 50"
elif printf '%s\n' "$escuchas_app" | grep -Evq "^127\.0\.0\.1:$PUERTO_APP$"; then
    mal "la app escucha fuera de 127.0.0.1" "el ExecStart de finanzas.service debe llevar --host 127.0.0.1"
else
    bien "la app solo escucha en 127.0.0.1:$PUERTO_APP"
fi

es_local() {  # dirección de escucha de ss, sin el puerto
    case "$1" in
        127.* | "[::1]" | ::1 | "[::ffff:127."*) return 0 ;;
        *) return 1 ;;
    esac
}
puertos_extra=""
while read -r direccion; do
    [[ -z "$direccion" ]] && continue
    puerto="${direccion##*:}"
    host="${direccion%:*}"
    host="${host%%%*}"  # quita la interfaz, p. ej. 127.0.0.53%lo
    if es_local "$host"; then
        continue
    fi
    if [[ "$PUERTOS_PUBLICOS_PERMITIDOS" != *" $puerto "* && " $puertos_extra " != *" $puerto "* ]]; then
        puertos_extra="$puertos_extra $puerto"
    fi
done < <(ss -ltnH 2>/dev/null | awk '{ print $4 }')
if [[ -z "$puertos_extra" ]]; then
    bien "no hay puertos TCP públicos distintos de 22, 80 y 443"
else
    pista_puertos="sudo ss -ltnp para ver qué programa es"
    if [[ " $puertos_extra " == *" 111 "* ]]; then
        # Las imágenes Ubuntu de Oracle traen rpcbind en el 111; la app no lo usa.
        pista_puertos="el 111 es rpcbind, que la app no usa: sudo systemctl disable --now rpcbind.socket rpcbind.service (deploy/GUIA.md, paso 5.3); para los demás, $pista_puertos"
    fi
    mal "hay puertos TCP escuchando hacia fuera:$puertos_extra" "$pista_puertos"
fi

reglas="$(iptables -S INPUT 2>/dev/null)"
posicion() {  # número de la primera regla de INPUT que cumple el patrón
    printf '%s\n' "$reglas" | grep -n -E -- "$1" | head -n 1 | cut -d: -f1
}
rechazo="$(posicion '-j REJECT')"
for puerto in 80 443; do
    acepta="$(posicion "--dport $puerto( |$).*-j ACCEPT")"
    if [[ -n "$acepta" && ( -z "$rechazo" || "$acepta" -lt "$rechazo" ) ]]; then
        bien "iptables acepta el puerto $puerto antes del REJECT"
    else
        mal "iptables no acepta el puerto $puerto antes del REJECT" "ver deploy/GUIA.md, paso 4 (iptables y netfilter-persistent save)"
    fi
done

echo "== Secretos y permisos"
# systemd lee los .env como root: la app no necesita acceder a /etc/finanzas.
comprobar_permisos "carpeta $ETC_DIR" "$ETC_DIR" "root:root 700"
comprobar_permisos "finanzas.env" "$ETC_DIR/finanzas.env" "root:root 600"
comprobar_permisos "duckdns.env" "$ETC_DIR/duckdns.env" "root:root 600"
comprobar_permisos "carpeta de datos $DATOS_DIR" "$DATOS_DIR" "finanzas:finanzas 700"
comprobar_permisos "carpeta de respaldos $RESPALDOS_DIR" "$RESPALDOS_DIR" "finanzas:finanzas 700"

db_path="$(valor_env DB_PATH "$ETC_DIR/finanzas.env")"
if [[ -n "$db_path" ]]; then
    comprobar_permisos "base de datos" "$db_path" "finanzas:finanzas 600"
    # Ítem 22: la app no arranca si la base no está en la última migración.
    # Como el usuario finanzas y solo lectura (--comprobar no escribe nada).
    if (cd "$APP_DIR" && runuser -u finanzas -- "$APP_DIR/.venv/bin/python" -m finanzas.migrar \
            --base "$db_path" --comprobar) >/dev/null 2>&1; then
        bien "la base de datos está en la última migración"
    else
        mal "la base de datos no está en la última migración (o no se pudo comprobar)" \
            "sudo systemctl start finanzas-migrar.service; journalctl -u finanzas-migrar -n 20 (ver 13.2)"
    fi
else
    mal "finanzas.env no define DB_PATH" "DB_PATH=$DATOS_DIR/finanzas.db"
fi

token="$(valor_env GMAIL_TOKEN "$ETC_DIR/finanzas.env")"
if [[ -n "$token" ]]; then
    comprobar_permisos "carpeta del token de Gmail" "$(dirname "$token")" "finanzas:finanzas 700"
    comprobar_permisos "token de Gmail" "$token" "finanzas:finanzas 600"
else
    mal "finanzas.env no define GMAIL_TOKEN" "GMAIL_TOKEN=$DATOS_DIR/gmail/token.json"
fi

if [[ "$(valor_env COOKIE_SECURE "$ETC_DIR/finanzas.env")" == "true" ]]; then
    bien "COOKIE_SECURE=true"
else
    mal "COOKIE_SECURE no es true en finanzas.env" "en el servidor debe ser COOKIE_SECURE=true"
fi

echo
if [[ "$fallos" -eq 0 ]]; then
    echo "Todo en orden."
    exit 0
fi
echo "Fallaron $fallos comprobaciones."
exit 1
