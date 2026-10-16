#!/usr/bin/env bash
# Despliega en la VM un commit exacto de `main`: los pasos de deploy/GUIA.md,
# 13.2 ("Actualizar la app"), en un solo comando.
#
# Uso (en la VM, como root):
#     sudo bash /opt/finanzas/deploy/desplegar.sh <sha-de-40-caracteres> [--permitir-migraciones]
#
# Qué hace, en orden:
#   1. Toma un candado: nunca corren dos despliegues a la vez.
#   2. Trae `origin` y exige que el commit exista y esté en `origin/main`.
#   3. Compara la revisión REAL de la base con las migraciones del commit:
#      - si la base va por delante del commit (un commit viejo), no hace nada;
#      - si el commit va a migrar la base y no se pasó --permitir-migraciones,
#        no hace nada (código 3). Algunas migraciones no se pueden deshacer.
#   4. Respaldo, parada, checkout, dependencias, frontend, unidades, Caddyfile
#      y migración, como en 13.2.
#   5. Arranca todo y comprueba la app de ESTA VM (HTTPS por 127.0.0.1).
#   6. Corre deploy/verificar.sh como diagnóstico completo.
#
# Si algo falla, o se corta la sesión, y la base NO cambió, vuelve solo al
# commit anterior. Si la base ya cambió, no vuelve atrás: el código anterior
# no la entiende y la vuelta atrás es restaurar el respaldo (guía, "Volver
# atrás", caso 2), una decisión del dueño.
#
# Códigos de salida:
#   0  desplegado y la app responde
#   1  falló, volvió al commit anterior y la app responde
#   2  uso incorrecto
#   3  el commit migra la base: falta --permitir-migraciones (no se tocó nada)
#   4  falló con la base ya migrada: no vuelve atrás solo (decide el dueño)
#   5  vuelta atrás incompleta o la app no responde: revisar a mano YA
#   6  no se hizo nada (candado ocupado, fetch o respaldo fallidos, base
#      ilegible, commit más viejo que la base)
#
# Nunca imprime secretos: no lee /etc/finanzas (eso lo hace systemd).

set -Eeuo pipefail

# Se ejecuta desde una copia temporal: el checkout reemplaza este archivo.
if [[ "${DESPLEGAR_COPIA_RUTA:-}" != "$0" ]]; then
    copia="$(mktemp "${TMPDIR:-/tmp}/desplegar.XXXXXX")"
    cp -- "$0" "$copia"
    DESPLEGAR_COPIA_RUTA="$copia" exec bash "$copia" "$@"
fi
# Solo se borra la copia temporal, nunca el script de /opt/finanzas.
if [[ "$0" == "${TMPDIR:-/tmp}"/desplegar.* ]]; then
    trap 'rm -f -- "$0"' EXIT
fi

# Rutas del despliegue (las de deploy/GUIA.md). Se pueden cambiar con
# variables de entorno solo para pruebas.
APP_DIR="${APP_DIR:-/opt/finanzas}"
DB="${DB:-/var/lib/finanzas/finanzas.db}"
NODE_BIN="${NODE_BIN:-/opt/node/bin}"
ESTADO_DIR="${ESTADO_DIR:-/var/lib/finanzas-despliegue}"
CANDADO="${CANDADO:-/run/finanzas-despliegue.lock}"
CADDY_OVERRIDE="${CADDY_OVERRIDE:-/etc/systemd/system/caddy.service.d/override.conf}"
CADDYFILE_SISTEMA="${CADDYFILE_SISTEMA:-/etc/caddy/Caddyfile}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
ESPERA_SALUD="${ESPERA_SALUD:-60}"  # segundos para que la app responda

uso() {
    echo "Uso: sudo bash deploy/desplegar.sh <sha-de-40-caracteres> [--permitir-migraciones]" >&2
    exit 2
}

SHA="${1:-}"
PERMITIR_MIGRACIONES=0
[[ $# -ge 1 ]] || uso
shift
for opcion in "$@"; do
    case "$opcion" in
        --permitir-migraciones) PERMITIR_MIGRACIONES=1 ;;
        *) uso ;;
    esac
done
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "El commit debe ser un SHA completo de 40 caracteres en minúsculas." >&2; exit 2; }
# DESPLEGAR_PRUEBA=1 solo lo usan las pruebas (backend/tests/operacion/), que
# simulan la VM con comandos falsos y no corren como root.
if [[ "${EUID}" -ne 0 && "${DESPLEGAR_PRUEBA:-0}" != "1" ]]; then
    echo "Ejecútalo con sudo: detiene servicios y escribe en /opt/finanzas." >&2
    exit 2
fi

paso() { printf '\n==> %s\n' "$*"; }
nota() { printf '    %s\n' "$*"; }
npm_() { env PATH="$NODE_BIN:/usr/bin:/bin" npm "$@"; }
git_() { git -C "$APP_DIR" "$@"; }
nada() { echo "$*" >&2; echo "No se tocó nada." >&2; exit 6; }

# --- 1. Candado -------------------------------------------------------------------
exec 9>"$CANDADO"
flock -n 9 || nada "Ya hay otro despliegue en curso."
install -d -m 0700 "$ESTADO_DIR"

# El dominio vive en el override de Caddy (guía, 9.2), no en el repositorio.
DOMINIO="$(sed -n 's/^Environment=DOMINIO=//p' "$CADDY_OVERRIDE" 2>/dev/null | tail -n 1)"
[[ "$DOMINIO" =~ ^[A-Za-z0-9.-]+$ ]] || { echo "No encuentro el dominio en $CADDY_OVERRIDE (guía, paso 9.2)." >&2; exit 2; }

# --- 2. El commit -----------------------------------------------------------------
paso "Traer el código y comprobar el commit"
git_ fetch --quiet origin || nada "No se pudo traer origin."
git_ cat-file -e "${SHA}^{commit}" 2>/dev/null || { echo "El commit $SHA no existe en origin." >&2; exit 2; }
git_ merge-base --is-ancestor "$SHA" origin/main || { echo "El commit $SHA no está en origin/main; solo se despliega main." >&2; exit 2; }
ANTERIOR="$(git_ rev-parse HEAD)"
nota "anterior: $ANTERIOR"
nota "nuevo:    $SHA"

# --- 3. Revisión de la base frente a las migraciones del commit ----------------------
revision_base() {
    # Solo lectura. Vacío si no hay base. Devuelve 2 si la base es de la v1
    # (sin tabla de Alembic) y 1 si no se puede leer (bloqueada, sin sqlite3).
    [[ -f "$DB" ]] || return 0
    local salida
    if salida="$(sqlite3 -cmd '.timeout 5000' "file:$DB?mode=ro" "SELECT version_num FROM alembic_version" 2>&1)"; then
        printf '%s\n' "$salida"
        return 0
    fi
    grep -qi "no such table" <<<"$salida" && return 2
    return 1
}
ultima_revision() {
    # La revisión más alta de un commit, esté en la raíz (antes) o en backend/.
    local archivos
    archivos="$(git_ ls-tree -r --name-only "$1")" || return 1
    { grep -oE '(^|/)finanzas/migraciones/versions/[0-9]{4}_' <<<"$archivos" | grep -oE '[0-9]{4}' || true; } \
        | sort | tail -n 1
}
estado_base=0
REV_BASE="$(revision_base)" || estado_base=$?
if [[ "$estado_base" -ne 0 ]]; then
    if [[ "$estado_base" -eq 2 ]]; then
        nada "La base es de la v1 (sin tabla de Alembic): esa primera actualización se hace a mano (guía, 13.2, \"Primera actualización con migraciones\")."
    fi
    nada "No se pudo leer la revisión de la base ($DB): ¿está bloqueada o falta sqlite3?"
fi
REV_COMMIT="$(ultima_revision "$SHA")" || nada "No se pudo leer el árbol del commit $SHA."
nota "base: ${REV_BASE:-sin base}   commit: ${REV_COMMIT:-sin migraciones}"
if [[ -n "$REV_BASE" && ( -z "$REV_COMMIT" || "$REV_BASE" > "$REV_COMMIT" ) ]]; then
    nada "La base ($REV_BASE) va por delante del commit (${REV_COMMIT:-sin migraciones}): ese código no la entiende. Para volver a una versión anterior, sigue \"Volver atrás\", caso 2."
fi
MIGRA=0
[[ "$REV_BASE" != "$REV_COMMIT" ]] && MIGRA=1
if [[ "$MIGRA" -eq 1 && "$PERMITIR_MIGRACIONES" -ne 1 ]]; then
    echo "Este despliegue migra la base (${REV_BASE:-sin base} -> $REV_COMMIT): revisa en la guía la sección de esas migraciones y repite con --permitir-migraciones." >&2
    echo "No se tocó nada." >&2
    exit 3
fi

historial() { printf '%s %s -> %s %s\n' "$(date -Is)" "$ANTERIOR" "$SHA" "$1" >> "$ESTADO_DIR/historial.log"; }
ultimo_historial() { tail -n 1 "$ESTADO_DIR/historial.log" 2>/dev/null || true; }

# La sincronización solo se arranca si ya estaba habilitada: en una VM nueva
# de pruebas sigue apagada (preparar-servidor.sh sin --produccion).
SINCRONIZACION=finanzas-sync.timer
systemctl is-enabled --quiet finanzas-sync.timer 2>/dev/null || SINCRONIZACION=""
arrancar() { systemctl start finanzas.service $SINCRONIZACION finanzas-respaldo.timer; }
parar() { systemctl stop finanzas-sync.timer finanzas-respaldo.timer finanzas-sync.service finanzas.service; }

app_sana() {
    # La app de ESTA VM (no la que diga el DNS): /app/ con 200 y /api/sesion con 401.
    local limite=$((SECONDS + ESPERA_SALUD)) app="" api=""
    while (( SECONDS < limite )); do
        if systemctl is-active --quiet finanzas.service; then
            app="$(curl --silent --output /dev/null --max-time 10 --resolve "$DOMINIO:443:127.0.0.1" \
                --write-out '%{http_code}' "https://$DOMINIO/app/" || true)"
            api="$(curl --silent --output /dev/null --max-time 10 --resolve "$DOMINIO:443:127.0.0.1" \
                --write-out '%{http_code}' "https://$DOMINIO/api/sesion" || true)"
            [[ "$app" == "200" && "$api" == "401" ]] && return 0
        fi
        sleep "${PAUSA_SALUD:-3}"
    done
    nota "La app no respondió como se esperaba (/app/: ${app:-nada}, /api/sesion: ${api:-nada})."
    return 1
}

# Instala dependencias, frontend, unidades y Caddyfile del commit en APP_DIR.
# Intenta cada paso aunque falle otro y devuelve 1 si alguno falló.
instalar_commit() {
    local fallos=0
    if [[ -f "$APP_DIR/backend/requirements.txt" ]]; then
        "$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/backend/requirements.txt" -e "$APP_DIR" || fallos=1
    else
        # Código anterior a backend/ (guía, "Volver atrás").
        "$APP_DIR/.venv/bin/pip" uninstall --quiet -y finanzas-personales || true
        "$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt" || fallos=1
    fi
    if (cd "$APP_DIR/frontend" && npm_ ci --ignore-scripts --no-audit --no-fund && npm_ run build); then
        git_ rev-parse HEAD > "$APP_DIR/frontend/.dist-commit"  # fuera de dist/: no se publica
    else
        fallos=1
    fi
    cp "$APP_DIR"/deploy/systemd/*.service "$APP_DIR"/deploy/systemd/*.timer "$SYSTEMD_DIR/" || fallos=1
    systemctl daemon-reload || fallos=1
    if ! cmp -s "$APP_DIR/deploy/caddy/Caddyfile" "$CADDYFILE_SISTEMA"; then
        nota "El Caddyfile cambió: se copia y se recarga Caddy."
        { install -m 0644 "$APP_DIR/deploy/caddy/Caddyfile" "$CADDYFILE_SISTEMA" && systemctl reload caddy; } || fallos=1
    fi
    return "$fallos"
}

if [[ "$ANTERIOR" == "$SHA" && "$MIGRA" -eq 0 ]]; then
    # Repetir un despliegue: solo es "nada que hacer" si el anterior terminó
    # bien y la app responde. Si no (corte, reinicio, código 4 o 5), se
    # reinstala el commit (pudo quedar a medias) y se comprueba.
    if [[ "$(ultimo_historial)" == *" -> $SHA OK" ]] && app_sana; then
        nota "La VM ya está en ese commit y la app responde; no hay nada que desplegar."
        exit 0
    fi
    paso "La VM ya está en ese commit, pero el último despliegue no terminó bien: reinstalar y comprobar"
    parar
    if instalar_commit && arrancar && app_sana; then
        historial "OK"
        printf '\n✔ La app responde en %s.\n' "$SHA"
        exit 0
    fi
    arrancar || true
    echo "✘ La app no responde en $SHA. Revisa: journalctl -u finanzas -n 50 --no-pager" >&2
    exit 5
fi

migracion_en_curso() {
    # Una unidad oneshot en marcha está "activating" (is-active no sirve).
    local estado
    estado="$(systemctl show -p ActiveState --value finanzas-migrar.service 2>/dev/null || true)"
    [[ "$estado" == "activating" || "$estado" == "deactivating" ]]
}

REV_AHORA=""
base_migrada() {
    # 0 si la base cambió, 1 si no. Si no se puede saber, sale con 5.
    while migracion_en_curso; do sleep 1; done
    if ! REV_AHORA="$(revision_base)"; then
        historial "FALLO-REVISION-ILEGIBLE"
        arrancar
        echo "✘ El despliegue falló y no se puede leer la revisión de la base para decidir la vuelta atrás. Revisa YA (guía, \"Volver atrás\")." >&2
        exit 5
    fi
    [[ "$REV_AHORA" != "$REV_BASE" ]]
}

con_base_migrada() {
    historial "FALLO-CON-MIGRACIONES"
    arrancar
    cat >&2 <<EOF

✘ El despliegue falló con la base YA migrada (${REV_BASE:-sin base} -> $REV_AHORA).
  No se vuelve atrás solo: el código anterior no entiende la base nueva. La
  app queda en el commit nuevo (se intentó arrancar).
  Revisa:   journalctl -u finanzas -n 50 --no-pager
  Volver atrás exige restaurar el respaldo previo a la migración
  (deploy/GUIA.md, 13.2, "Volver atrás", caso 2). Commit anterior: $ANTERIOR
EOF
    exit 4
}

volver_atras() {
    # Un segundo corte no debe interrumpir la vuelta atrás.
    trap - ERR
    trap "" HUP INT TERM
    set +e
    local fallos=0
    # Un corte mata al cliente systemctl, pero la migración sigue dentro de
    # systemd: base_migrada espera a que termine antes de mirar la base.
    base_migrada && con_base_migrada
    paso "Volviendo al commit anterior ($ANTERIOR); la base no cambió"
    parar
    git_ checkout --quiet --force --detach "$ANTERIOR" || { nota "Falló el checkout del commit anterior."; fallos=1; }
    instalar_commit || { nota "Falló algún paso al reinstalar el commit anterior."; fallos=1; }
    if base_migrada; then
        # La base cambió mientras se reinstalaba: el código nuevo es el que la entiende.
        git_ checkout --quiet --force --detach "$SHA"
        instalar_commit
        con_base_migrada
    fi
    arrancar || { nota "Falló el arranque."; fallos=1; }
    if [[ "$fallos" -eq 0 && "$(git_ rev-parse HEAD)" == "$ANTERIOR" ]] && app_sana; then
        historial "FALLO-VUELTO-ATRAS"
        echo "✘ El despliegue falló; la VM volvió al commit anterior y la app responde." >&2
        exit 1
    fi
    historial "FALLO-VUELTA-ATRAS-INCOMPLETA"
    echo "✘ El despliegue falló y la vuelta atrás quedó incompleta. Revisa YA: git -C $APP_DIR log -1; journalctl -u finanzas -n 50 --no-pager" >&2
    exit 5
}

# --- 4. Desplegar -----------------------------------------------------------------
paso "Respaldo manual antes de cambiar nada"
systemctl start finanzas-respaldo.service || nada "El respaldo falló."

# Desde aquí, cualquier fallo o corte (también de la sesión SSH) vuelve atrás.
trap 'nota "Falló la línea $LINENO."; volver_atras' ERR
trap 'nota "Despliegue interrumpido."; volver_atras' HUP INT TERM

paso "Parar la app y los temporizadores"
parar

paso "Pasar al commit nuevo, instalar y compilar"
git_ checkout --quiet --detach "$SHA"
instalar_commit

paso "Migrar la base (respaldo previo automático si hay cambios)"
if ! systemctl start finanzas-migrar.service; then
    journalctl -u finanzas-migrar -n 20 --no-pager || true
    nota "La migración falló (es una sola transacción: la base no debería cambiar)."
    false
fi
journalctl -u finanzas-migrar -n 5 --no-pager || true

# --- 5. Arrancar y comprobar ------------------------------------------------------
paso "Arrancar y comprobar que la app responde"
arrancar
app_sana
trap - ERR HUP INT TERM

historial "OK"
paso "Diagnóstico completo (deploy/verificar.sh)"
if ! bash "$APP_DIR/deploy/verificar.sh" "$DOMINIO"; then
    nota "verificar.sh marcó algo: la app responde, pero revisa los ✘ de arriba."
fi
printf '\n✔ Desplegado %s.\n' "$SHA"
