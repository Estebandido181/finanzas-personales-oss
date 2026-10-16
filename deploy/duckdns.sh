#!/usr/bin/env bash
# Actualiza la IP pública del subdominio de DuckDNS (ítem 07).
#
# Lo ejecuta duckdns.service cada 30 minutos. Lee DUCKDNS_DOMINIO y
# DUCKDNS_TOKEN de /etc/finanzas/duckdns.env, que systemd le entrega en
# $CREDENTIALS_DIRECTORY/duckdns.env (LoadCredential). Para probarlo a mano
# como root:  sudo bash /opt/finanzas/deploy/duckdns.sh /etc/finanzas/duckdns.env
#
# Seguridad:
# - El archivo se lee línea a línea; nunca se ejecuta con "source".
# - El token no va en la línea de comandos de curl (se vería en "ps"): la URL
#   se le pasa por stdin como archivo de configuración (-K -).
# - Nunca se imprime el token ni la URL. Solo "OK" o un error genérico.
# - "ip=" vacío: DuckDNS usa la IP desde la que llega la petición, que en
#   Oracle es la IP pública de la VM.
set -euo pipefail

archivo="${1:-${CREDENTIALS_DIRECTORY:-}/duckdns.env}"
if [[ ! -r "$archivo" ]]; then
    echo "duckdns: no puedo leer el archivo de configuración de DuckDNS." >&2
    exit 2
fi

dominio=""
token=""
while IFS= read -r linea || [[ -n "$linea" ]]; do
    linea="${linea%$'\r'}"
    case "$linea" in
        DUCKDNS_DOMINIO=*) dominio="${linea#DUCKDNS_DOMINIO=}" ;;
        DUCKDNS_TOKEN=*) token="${linea#DUCKDNS_TOKEN=}" ;;
    esac
done < "$archivo"

# Se acepta "tu-subdominio" o "tu-subdominio.duckdns.org".
dominio="${dominio%.duckdns.org}"
if [[ ! "$dominio" =~ ^[a-z0-9-]{1,63}$ ]]; then
    echo "duckdns: DUCKDNS_DOMINIO falta o no es válido (solo el subdominio, en minúsculas)." >&2
    exit 2
fi
# Los tokens de DuckDNS tienen forma de UUID. Validarlo impide además que un
# carácter raro (comillas, espacios) altere la configuración que recibe curl.
if [[ ! "$token" =~ ^[0-9a-fA-F-]{36}$ ]]; then
    echo "duckdns: DUCKDNS_TOKEN falta o no tiene el formato esperado." >&2
    exit 2
fi

# printf es un comando interno de bash: el token no aparece en ningún argv.
respuesta="$(
    printf 'url = "https://www.duckdns.org/update?domains=%s&token=%s&ip="\n' "$dominio" "$token" |
        curl --silent --show-error --fail --max-time 30 --proto =https -K -
)" || {
    echo "duckdns: la petición a DuckDNS falló." >&2
    exit 1
}
unset token

if [[ "$respuesta" == "OK" ]]; then
    echo "duckdns: IP actualizada (OK)."
else
    # DuckDNS responde "KO" si el subdominio o el token no coinciden.
    echo "duckdns: DuckDNS rechazó la actualización (revisa el subdominio y el token)." >&2
    exit 1
fi
