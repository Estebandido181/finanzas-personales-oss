#!/usr/bin/env bash
# Prepara una VM Ubuntu 24.04 de Oracle Cloud para Finanzas personales: los
# pasos 4.2 a 10 de deploy/GUIA.md en un solo comando que se puede repetir.
#
# Uso (en la VM, como root; lo llama cloud-init al crear la VM con Terraform):
#     sudo bash preparar-servidor.sh [--dominio sub.duckdns.org] [--produccion]
#
# Es idempotente: cada paso mira si ya está hecho y, si lo está, no lo repite.
# Se puede correr las veces que haga falta; por ejemplo, después de registrar
# la llave de despliegue en GitHub o de poner los secretos.
#
# Con --commit <sha> clona ese commit exacto (el que corre la VM anterior), así
# la base que se traiga encaja con el código sin migrar nada.
#
# Lo que NO hace (y dice al final si falta):
#   - Registrar la llave de despliegue en GitHub: imprime la llave pública y
#     se detiene hasta que la registres (el repositorio es privado).
#   - Poner los secretos (/etc/finanzas/*.env) ni el token de Gmail: vienen de
#     la VM anterior o del Vault. Sin ellos no arranca la app.
#   - Migrar la base ni arrancar la app sobre una base vieja: si la base no
#     está al día, eso lo decide el dueño con desplegar.sh --permitir-migraciones.
#     Sin base no arranca nada (no crea una vacía).
#   - Activar DuckDNS ni la sincronización con Gmail, salvo con --produccion
#     (en el cambio de VM): dos VM actualizando el mismo subdominio se lo
#     pelearían, y dos sincronizaciones dejarían dos bases distintas. Sin la
#     bandera solo arranca la app y el respaldo, para probarla.
#
# Nunca imprime secretos.

set -Eeuo pipefail

# Repositorio privado por SSH (usuario genérico de GitHub, como en la guía, 6).
GITHUB_SSH="git@github.com"
REPO="${REPO:-$GITHUB_SSH:Estebandido181/finanzas-personales-oss.git}"
RAMA="${RAMA:-main}"
APP_DIR=/opt/finanzas
NODE_VERSION=24.21.0
# Huella SHA-256 pública de GitHub para ed25519 (la misma de deploy/GUIA.md,
# paso 6, publicada en docs.github.com).
GITHUB_HUELLA="SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU"
LLAVE_DEPLOY=/root/.ssh/finanzas_deploy

USO="Uso: sudo bash preparar-servidor.sh [--dominio sub.duckdns.org] [--commit <sha>] [--produccion]"
DOMINIO=""
COMMIT=""
PRODUCCION=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dominio|--commit)
            [[ $# -ge 2 && -n "$2" ]] || { echo "$1 necesita un valor. $USO" >&2; exit 2; }
            [[ "$1" == "--dominio" ]] && DOMINIO="$2" || COMMIT="$2"
            shift 2 ;;
        --produccion) PRODUCCION=1; shift ;;
        *) echo "$USO" >&2; exit 2 ;;
    esac
done
if [[ -n "$COMMIT" && ! "$COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
    echo "--commit debe ser un SHA completo de 40 caracteres (el mismo que corre la VM anterior)." >&2
    exit 2
fi
if [[ -n "$DOMINIO" && ! "$DOMINIO" =~ ^[a-z0-9-]+\.duckdns\.org$ ]]; then
    echo "--dominio debe ser un subdominio de duckdns.org en minúsculas." >&2
    exit 2
fi
if [[ "${EUID}" -ne 0 ]]; then echo "Ejecútalo con sudo." >&2; exit 2; fi

paso() { printf '\n==> %s\n' "$*"; }
nota() { printf '    %s\n' "$*"; }
PENDIENTES=()

# --- Comprobaciones -------------------------------------------------------------
. /etc/os-release
[[ "${ID:-}" == "ubuntu" && "${VERSION_ID:-}" == "24.04" ]] || { echo "Esta preparación es para Ubuntu 24.04 (D13)." >&2; exit 2; }
case "$(uname -m)" in
    aarch64) NODE_ARCH=arm64 ;;
    x86_64) NODE_ARCH=x64 ;;
    *) echo "Arquitectura no soportada: $(uname -m)" >&2; exit 2 ;;
esac
export DEBIAN_FRONTEND=noninteractive

# --- 5.1 Sistema, zona horaria y actualizaciones automáticas ---------------------
paso "Paquetes del sistema y zona horaria"
timedatectl set-timezone America/Bogota
echo "iptables-persistent iptables-persistent/autosave_v4 boolean true" | debconf-set-selections
echo "iptables-persistent iptables-persistent/autosave_v6 boolean true" | debconf-set-selections
apt-get update -q
apt-get install -y -q unattended-upgrades git python3-venv sqlite3 curl gnupg \
    iptables-persistent debian-keyring debian-archive-keyring apt-transport-https
printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' \
    > /etc/apt/apt.conf.d/20auto-upgrades

# Con poca memoria (E2.1.Micro), 1 GB de intercambio para compilar (guía, 5.2).
if (( $(awk '/MemTotal/ {print $2}' /proc/meminfo) < 2000000 )) && [[ ! -f /swapfile ]]; then
    paso "Archivo de intercambio de 1 GB"
    if fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile; then
        grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    else
        rm -f /swapfile
        PENDIENTES+=("Intercambio: no se pudo crear /swapfile (guía, 5.2).")
    fi
fi

# --- 4.2 iptables: 80 y 443 antes del REJECT de Oracle ---------------------------
paso "Cortafuegos de la VM (80 y 443)"
for puerto in 80 443; do
    if ! iptables -C INPUT -p tcp -m state --state NEW -m tcp --dport "$puerto" -j ACCEPT 2>/dev/null; then
        n="$(iptables -L INPUT --line-numbers -n | awk '$2 == "REJECT" { print $1; exit }')"
        if [[ -n "$n" ]]; then
            iptables -I INPUT "$n" -p tcp -m state --state NEW -m tcp --dport "$puerto" -j ACCEPT
        else
            iptables -A INPUT -p tcp -m state --state NEW -m tcp --dport "$puerto" -j ACCEPT
        fi
        nota "abierto el $puerto"
    fi
done
netfilter-persistent save >/dev/null
rechazo="$(iptables -L INPUT --line-numbers -n | awk '$2 == "REJECT" { print $1; exit }')"
for puerto in 80 443; do
    linea="$(iptables -L INPUT --line-numbers -n | awk -v p="dpt:$puerto" '$2 == "ACCEPT" && $0 ~ p" *$" { print $1; exit }')"
    if [[ -n "$rechazo" && -n "$linea" && "$linea" -gt "$rechazo" ]]; then
        PENDIENTES+=("iptables: la regla del $puerto quedó después del REJECT y no se aplica (guía, 4.2, cómo corregirlo).")
    fi
done

# --- 5.3 rpcbind fuera ---------------------------------------------------------------
if systemctl list-unit-files rpcbind.service >/dev/null 2>&1; then
    systemctl disable --now rpcbind.socket rpcbind.service 2>/dev/null || true
    systemctl mask rpcbind.socket rpcbind.service >/dev/null 2>&1 || true
fi

# --- 5.2 Usuario y carpetas ----------------------------------------------------------
paso "Usuario finanzas y carpetas"
if ! id finanzas >/dev/null 2>&1; then
    useradd --system --user-group --home-dir /var/lib/finanzas --no-create-home --shell /usr/sbin/nologin finanzas
    passwd -l finanzas >/dev/null
fi
install -d -o finanzas -g finanzas -m 0700 /var/lib/finanzas /var/lib/finanzas/gmail /var/backups/finanzas
install -d -o root -g root -m 0700 /etc/finanzas

# --- 6.1 Node fijo y verificado ------------------------------------------------------
if [[ "$(/opt/node/bin/node --version 2>/dev/null || true)" != "v$NODE_VERSION" ]]; then
    paso "Node $NODE_VERSION ($NODE_ARCH)"
    archivo="node-v$NODE_VERSION-linux-$NODE_ARCH.tar.xz"
    tmp="$(mktemp -d)"
    curl -fsSL --proto =https -o "$tmp/$archivo" "https://nodejs.org/dist/v$NODE_VERSION/$archivo"
    # Huellas publicadas en nodejs.org (las mismas de la guía, 6.1); solo se
    # comprueba la del archivo descargado.
    huellas="$(cat <<'HUELLAS'
6ad1325edbdb5649c379b75a237147a666c95d4f9ae8d340fef2d1575d289ad2  node-v24.21.0-linux-arm64.tar.xz
fd8e59d5a511510f6a298afb548f18c7d2b1be404d8b4a27d94fbe49f56cb2d6  node-v24.21.0-linux-x64.tar.xz
HUELLAS
)"
    grep -F "  $archivo" <<<"$huellas" | (cd "$tmp" && sha256sum --quiet -c -) \
        || { echo "La huella de Node no coincide: no se instala." >&2; exit 1; }
    rm -rf /opt/node && mkdir -p /opt/node
    tar -xJf "$tmp/$archivo" -C /opt/node --strip-components=1 --no-same-owner
    rm -rf "$tmp"
fi

# --- 9.1 Caddy desde su repositorio oficial ------------------------------------------
if ! command -v caddy >/dev/null 2>&1; then
    paso "Caddy"
    curl -1sLf --proto =https 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf --proto =https 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        > /etc/apt/sources.list.d/caddy-stable.list
    chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -q
    apt-get install -y -q caddy
fi

# --- 6. Código: llave de despliegue (solo lectura) y clon ----------------------------
paso "Acceso de solo lectura al repositorio"
install -d -m 0700 /root/.ssh
[[ -f "$LLAVE_DEPLOY" ]] || ssh-keygen -q -t ed25519 -f "$LLAVE_DEPLOY" -N "" -C "finanzas-vm-deploy"
touch /root/.ssh/known_hosts && chmod 600 /root/.ssh/known_hosts
# Huellas ED25519 que ya tenga known_hosts para github.com (puede haber varias).
huellas_github="$(ssh-keygen -lF github.com -f /root/.ssh/known_hosts 2>/dev/null | awk '/ED25519/ {print $3}' | sort -u)"
if [[ -z "$huellas_github" ]]; then
    clave="$(ssh-keyscan -t ed25519 github.com 2>/dev/null || true)"
    [[ -n "$clave" ]] || { echo "No se pudo consultar la llave de github.com (¿red o DNS?). Vuelve a intentar." >&2; exit 1; }
    huella="$(printf '%s\n' "$clave" | ssh-keygen -lf - | awk '{print $2}')"
    [[ "$huella" == "$GITHUB_HUELLA" ]] || { echo "La huella de github.com no coincide con la publicada: no sigo." >&2; exit 1; }
    printf '%s\n' "$clave" >> /root/.ssh/known_hosts
elif [[ "$huellas_github" != "$GITHUB_HUELLA" ]]; then
    echo "known_hosts tiene para github.com llaves ED25519 distintas de la publicada ($GITHUB_HUELLA): no sigo. Revisa /root/.ssh/known_hosts (ssh-keygen -lF github.com -f /root/.ssh/known_hosts)." >&2
    exit 1
fi
export GIT_SSH_COMMAND="ssh -i $LLAVE_DEPLOY -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes"
if ! error_git="$(git ls-remote --heads "$REPO" "$RAMA" 2>&1 >/dev/null)"; then
    if grep -qi "host key verification failed" <<<"$error_git"; then
        echo "GitHub presentó una llave que no coincide con known_hosts: no sigo. Revisa /root/.ssh/known_hosts." >&2
        exit 1
    fi
    if ! grep -qiE "permission denied|repository not found|could not read from remote" <<<"$error_git"; then
        echo "No se pudo hablar con GitHub (¿red o DNS?). Vuelve a intentar." >&2
        exit 1
    fi
    echo
    echo "Falta registrar la llave de despliegue en GitHub (solo lectura):"
    echo "  repositorio -> Settings -> Deploy keys -> Add deploy key, SIN 'Allow write access'."
    echo "  Llave pública:"
    cat "$LLAVE_DEPLOY.pub"
    echo "Después vuelve a correr este script."
    exit 10
fi
if [[ ! -d "$APP_DIR/.git" ]]; then
    paso "Clonar $RAMA en $APP_DIR"
    git clone --quiet --branch "$RAMA" "$REPO" "$APP_DIR"
    if [[ -n "$COMMIT" ]]; then
        git -C "$APP_DIR" merge-base --is-ancestor "$COMMIT" "origin/$RAMA" \
            || { echo "El commit $COMMIT no está en $RAMA." >&2; exit 2; }
        git -C "$APP_DIR" checkout --quiet --detach "$COMMIT"
    fi
elif [[ -n "$COMMIT" && "$(git -C "$APP_DIR" rev-parse HEAD)" != "$COMMIT" ]]; then
    PENDIENTES+=("Commit: $APP_DIR ya existe en otro commit; --commit solo aplica al clonar. Para cambiarlo usa desplegar.sh.")
fi
git -C "$APP_DIR" config core.sshCommand "$GIT_SSH_COMMAND"

paso "Entorno de Python y frontend"
[[ -x "$APP_DIR/.venv/bin/python" ]] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/backend/requirements.txt" -e "$APP_DIR"
# Se compila si falta o si es de otro commit. La marca va fuera de dist/ (que
# la app publica) y es la misma que escribe desplegar.sh.
cabeza="$(git -C "$APP_DIR" rev-parse HEAD)"
if [[ ! -f "$APP_DIR/frontend/dist/index.html" || "$(cat "$APP_DIR/frontend/.dist-commit" 2>/dev/null || true)" != "$cabeza" ]]; then
    (cd "$APP_DIR/frontend" && env PATH=/opt/node/bin:/usr/bin:/bin npm ci --ignore-scripts --no-audit --no-fund \
        && env PATH=/opt/node/bin:/usr/bin:/bin npm run build)
    printf '%s\n' "$cabeza" > "$APP_DIR/frontend/.dist-commit"
fi

# --- 9.2 Caddyfile y dominio ---------------------------------------------------------
if [[ -n "$DOMINIO" ]]; then
    paso "Caddy para $DOMINIO"
    install -m 0644 "$APP_DIR/deploy/caddy/Caddyfile" /etc/caddy/Caddyfile
    install -d -m 0755 /etc/systemd/system/caddy.service.d
    printf '[Service]\nEnvironment=DOMINIO=%s\n' "$DOMINIO" > /etc/systemd/system/caddy.service.d/override.conf
    systemctl daemon-reload
    systemctl restart caddy
else
    PENDIENTES+=("Dominio: vuelve a correr con --dominio sub.duckdns.org para configurar Caddy (HTTPS).")
fi

# --- 10. Servicios -------------------------------------------------------------------
paso "Unidades de systemd"
cp "$APP_DIR"/deploy/systemd/*.service "$APP_DIR"/deploy/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload

permisos() { stat -c '%U:%G %a' "$1" 2>/dev/null || true; }
DB=/var/lib/finanzas/finanzas.db
TOKEN=/var/lib/finanzas/gmail/token.json
if [[ "$(permisos /etc/finanzas/finanzas.env)" != "root:root 600" ]]; then
    PENDIENTES+=("Secretos: falta /etc/finanzas/finanzas.env (root:root 600). Tráelo de la VM anterior o del Vault y vuelve a correr.")
elif [[ "$(permisos "$DB")" != "finanzas:finanzas 600" ]]; then
    PENDIENTES+=("Base: falta $DB (finanzas:finanzas 600). Cópiala de la VM anterior (o, si de verdad empiezas de cero, crea una vacía con la unidad finanzas-migrar) y vuelve a correr.")
elif ! comprobacion="$(cd "$APP_DIR" && runuser -u finanzas -- "$APP_DIR/.venv/bin/python" -m finanzas.migrar --base "$DB" --comprobar 2>&1)"; then
    PENDIENTES+=("Base: la comprobación dice «$(tail -n 1 <<<"$comprobacion")». Si faltan migraciones, decide y despliega con: sudo bash $APP_DIR/deploy/desplegar.sh <sha> --permitir-migraciones")
else
    paso "Servicios de la app (la base ya está al día)"
    systemctl enable --now finanzas.service finanzas-respaldo.timer
    if [[ "$PRODUCCION" -eq 1 ]]; then
        systemctl enable --now finanzas-sync.timer
    elif ! systemctl is-active --quiet finanzas-sync.timer; then
        nota "La sincronización con Gmail sigue apagada (se activa con --produccion en el cambio de VM)."
    fi
fi
[[ "$(permisos "$TOKEN")" == "finanzas:finanzas 600" ]] \
    || PENDIENTES+=("Token de Gmail: cópialo a $TOKEN (finanzas:finanzas 600) o autoriza de nuevo (guía, 8).")
if [[ "$PRODUCCION" -eq 1 ]]; then
    if [[ "$(permisos /etc/finanzas/duckdns.env)" == "root:root 600" ]]; then
        systemctl enable --now duckdns.timer
    else
        PENDIENTES+=("DuckDNS: falta /etc/finanzas/duckdns.env (root:root 600).")
    fi
elif ! systemctl is-active --quiet duckdns.timer; then
    nota "DuckDNS sigue apagado (se activa con --produccion en el cambio de VM)."
fi

# --- Resumen ---------------------------------------------------------------------------
echo
if [[ ${#PENDIENTES[@]} -eq 0 ]]; then
    echo "✔ Servidor preparado. Comprueba con: sudo bash $APP_DIR/deploy/verificar.sh $DOMINIO"
else
    echo "Servidor preparado, con pendientes:"
    printf '  - %s\n' "${PENDIENTES[@]}"
fi
