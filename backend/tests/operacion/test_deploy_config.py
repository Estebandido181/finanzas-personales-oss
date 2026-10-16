"""Comprobaciones estáticas de los archivos de ``deploy/`` (ítem 07).

No necesitan root, red ni systemd: leen los archivos como texto. La prueba de
``duckdns.sh`` lo ejecuta con un ``curl`` falso para ver qué recibe.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[3] / "deploy"
SYSTEMD = DEPLOY / "systemd"

ENDURECIMIENTO = {
    "NoNewPrivileges": "true",
    "ProtectSystem": "strict",
    "ProtectHome": "true",
    "PrivateTmp": "true",
    "PrivateDevices": "true",
    "ProtectKernelTunables": "true",
    "ProtectKernelModules": "true",
    "ProtectKernelLogs": "true",
    "ProtectControlGroups": "true",
    "LockPersonality": "true",
    "MemoryDenyWriteExecute": "true",
    "CapabilityBoundingSet": "",
    "UMask": "0077",
}


def _directivas(ruta: Path) -> dict[str, list[str]]:
    """Directivas de una unidad de systemd: nombre → valores (sin comentarios)."""
    resultado: dict[str, list[str]] = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith(("#", ";", "[")):
            continue
        nombre, _, valor = linea.partition("=")
        resultado.setdefault(nombre.strip(), []).append(valor.strip())
    return resultado


def _unica(directivas: dict[str, list[str]], nombre: str) -> str:
    valores = directivas.get(nombre)
    assert valores is not None, f"falta {nombre}"
    assert len(valores) == 1, f"{nombre} aparece {len(valores)} veces"
    return valores[0]


def _seccion(markdown: str, titulo: str) -> str:
    """Texto de la sección cuyo encabezado contiene ``titulo`` (hasta el siguiente del mismo nivel o superior)."""
    lineas = markdown.splitlines()
    # Los "# ..." dentro de bloques de código son comentarios, no encabezados.
    encabezados: list[tuple[int, int]] = []  # (línea, nivel)
    en_codigo = False
    for i, linea in enumerate(lineas):
        if linea.startswith("```"):
            en_codigo = not en_codigo
        elif not en_codigo and re.match(r"#{1,6} ", linea):
            encabezados.append((i, len(linea) - len(linea.lstrip("#"))))
    for k, (i, nivel) in enumerate(encabezados):
        if titulo.lower() in lineas[i].lower():
            fin = next((j for j, n in encabezados[k + 1:] if n <= nivel), len(lineas))
            return "\n".join(lineas[i:fin])
    raise AssertionError(f"no hay una sección «{titulo}»")


def test_existen_todos_los_archivos():
    esperados = [
        "GUIA.md",
        "respaldo.py",
        "duckdns.sh",
        "verificar.sh",
        "caddy/Caddyfile",
        "systemd/finanzas.service",
        "systemd/finanzas-sync.service",
        "systemd/finanzas-sync.timer",
        "systemd/finanzas-respaldo.service",
        "systemd/finanzas-respaldo.timer",
        "systemd/duckdns.service",
        "systemd/duckdns.timer",
    ]
    for relativo in esperados:
        assert (DEPLOY / relativo).is_file(), relativo


# --- finanzas.service ---------------------------------------------------------


def test_servicio_web_usuario_entorno_y_arranque():
    d = _directivas(SYSTEMD / "finanzas.service")
    assert _unica(d, "User") == "finanzas"
    assert _unica(d, "EnvironmentFile") == "/etc/finanzas/finanzas.env"
    assert _unica(d, "Restart") == "on-failure"
    inicio = _unica(d, "ExecStart").split()
    assert inicio[0] == "/opt/finanzas/.venv/bin/uvicorn"
    assert "--factory" in inicio
    assert "finanzas.web.app:crear_app" in inicio
    assert inicio[inicio.index("--host") + 1] == "127.0.0.1"
    assert inicio[inicio.index("--port") + 1] == "8000"
    assert "--proxy-headers" in inicio
    assert "--forwarded-allow-ips=127.0.0.1" in inicio
    # Un solo proceso: el limitador y los tokens del ingreso viven en memoria.
    assert "--workers" not in inicio
    assert not any(parte.startswith("--workers") for parte in inicio)


@pytest.mark.parametrize("unidad", ["finanzas.service", "finanzas-sync.service"])
def test_servicios_de_la_app_endurecidos(unidad):
    d = _directivas(SYSTEMD / unidad)
    for nombre, valor in ENDURECIMIENTO.items():
        assert _unica(d, nombre) == valor, nombre
    assert _unica(d, "ReadWritePaths") == "/var/lib/finanzas"
    familias = set(_unica(d, "RestrictAddressFamilies").split())
    assert familias == {"AF_INET", "AF_INET6", "AF_UNIX"}


# --- Sincronización -----------------------------------------------------------


def test_servicio_de_sincronizacion():
    d = _directivas(SYSTEMD / "finanzas-sync.service")
    assert _unica(d, "Type") == "oneshot"
    assert _unica(d, "User") == "finanzas"
    assert _unica(d, "EnvironmentFile") == "/etc/finanzas/finanzas.env"
    assert _unica(d, "ExecStart") == "/opt/finanzas/.venv/bin/python -m finanzas.sincronizacion"


def test_temporizador_de_sincronizacion_cada_6_horas_y_persistente():
    d = _directivas(SYSTEMD / "finanzas-sync.timer")
    assert _unica(d, "OnCalendar") == "*-*-* 00/6:00:00"
    assert _unica(d, "Persistent") == "true"
    assert _unica(d, "RandomizedDelaySec") == "5min"
    assert _unica(d, "Unit") == "finanzas-sync.service"
    assert "timers.target" in _unica(d, "WantedBy")


def test_el_temporizador_explica_como_cambiar_el_intervalo():
    assert "systemctl edit finanzas-sync.timer" in (SYSTEMD / "finanzas-sync.timer").read_text()


# --- Respaldo -----------------------------------------------------------------


def test_respaldo_diario_con_el_script_del_repositorio():
    d = _directivas(SYSTEMD / "finanzas-respaldo.service")
    assert _unica(d, "Type") == "oneshot"
    assert _unica(d, "User") == "finanzas"
    inicio = _unica(d, "ExecStart").split()
    assert inicio[:2] == ["/usr/bin/python3", "/opt/finanzas/deploy/respaldo.py"]
    assert inicio[inicio.index("--origen") + 1] == "/var/lib/finanzas/finanzas.db"
    assert inicio[inicio.index("--destino") + 1] == "/var/backups/finanzas"
    assert "/var/backups/finanzas" in _unica(d, "ReadWritePaths").split()
    # No necesita secretos.
    assert "EnvironmentFile" not in d
    for nombre, valor in ENDURECIMIENTO.items():
        assert _unica(d, nombre) == valor, nombre

    t = _directivas(SYSTEMD / "finanzas-respaldo.timer")
    calendario = _unica(t, "OnCalendar")
    assert re.fullmatch(r"\*-\*-\* \d{2}:\d{2}:\d{2}", calendario)  # una vez al día
    assert _unica(t, "Persistent") == "true"
    assert _unica(t, "Unit") == "finanzas-respaldo.service"


# --- Migraciones (ítem 22) ------------------------------------------------------


def test_servicio_de_migraciones():
    d = _directivas(SYSTEMD / "finanzas-migrar.service")
    assert _unica(d, "Type") == "oneshot"
    assert _unica(d, "User") == "finanzas"
    assert _unica(d, "WorkingDirectory") == "/opt/finanzas"
    inicio = _unica(d, "ExecStart").split()
    assert inicio[:3] == ["/opt/finanzas/.venv/bin/python", "-m", "finanzas.migrar"]
    assert inicio[inicio.index("--base") + 1] == "/var/lib/finanzas/finanzas.db"
    assert inicio[inicio.index("--respaldos") + 1] == "/var/backups/finanzas"
    assert set(_unica(d, "ReadWritePaths").split()) == {"/var/lib/finanzas", "/var/backups/finanzas"}
    # No necesita secretos ni red, y no arranca solo (se lanza al actualizar).
    assert "EnvironmentFile" not in d
    assert _unica(d, "PrivateNetwork") == "true"
    assert "WantedBy" not in d
    # No se puede migrar con la app o la sincronización escribiendo.
    assert set(_unica(d, "Conflicts").split()) == {"finanzas.service", "finanzas-sync.service"}
    for nombre, valor in ENDURECIMIENTO.items():
        assert _unica(d, nombre) == valor, nombre


def test_guia_explica_migrar_y_volver_atras():
    guia = (DEPLOY / "GUIA.md").read_text(encoding="utf-8")
    actualizar = _seccion(guia, "13.2 Actualizar la app")
    bloques = _bloques_de_codigo(actualizar)
    # Empieza con el respaldo manual y migra antes de arrancar la app.
    primero = [l for l in bloques[0].splitlines() if l.strip() and not l.startswith("#")]
    assert primero[0].startswith("sudo systemctl start finanzas-respaldo.service")
    orden = bloques[0]
    assert orden.index("finanzas-migrar.service") < orden.index("sudo systemctl start finanzas.service")
    assert orden.index("stop") < orden.index("finanzas-migrar.service")
    for texto in ("0001", "Volver atrás", "finanzas-antes-de-migrar-", "--comprobar", "--bajar-a", "rm "):
        assert texto in actualizar, texto
    # Volver atrás: el caso de solo marcar 0001 no restaura; el que restaura no
    # lanza finanzas-migrar (no existe en el código anterior al ítem 22).
    volver = _seccion(guia, "Volver atrás")
    assert "No restaures nada" in volver
    caso_1, caso_2 = _bloques_de_codigo(volver)[:2]
    assert "install -o finanzas" not in caso_1 and "install -o finanzas" in caso_2
    for bloque in (caso_1, caso_2):
        assert "finanzas-migrar" not in bloque
        assert "sudo systemctl start finanzas.service finanzas-sync.timer finanzas-respaldo.timer" in bloque
    # Si la estructura no coincide, se arranca de nuevo lo que se paró.
    primera = _seccion(guia, "Primera actualización con migraciones")
    assert any(
        "sudo systemctl start finanzas.service finanzas-sync.timer finanzas-respaldo.timer" in b
        for b in _bloques_de_codigo(primera)
    )
    primera_vez = _seccion(guia, "10. Servicios")
    assert primera_vez.index("finanzas-migrar.service") < primera_vez.index("enable --now finanzas.service")



def test_la_guia_lista_los_respaldos_con_sudo():
    """/var/backups/finanzas es 0700 de finanzas: sin sudo, ls da "Permission
    denied"; y un * fuera de ``sudo sh -c`` lo expande el shell del usuario,
    que no ve los nombres. Pasó en la primera actualización real."""
    guia = (DEPLOY / "GUIA.md").read_text(encoding="utf-8")
    for bloque in _bloques_de_codigo(guia):
        for linea in bloque.splitlines():
            orden = linea.split("#", 1)[0].strip()
            if "/var/backups/finanzas" not in orden or not orden.startswith("ls"):
                continue
            raise AssertionError(f"ls sin sudo: {linea}")
        for linea in bloque.splitlines():
            orden = linea.split("#", 1)[0].strip()
            if orden.startswith("sudo ls") and "/var/backups/finanzas" in orden:
                assert "*" not in orden, f"el * debe ir dentro de sudo sh -c: {linea}"


# --- DuckDNS ------------------------------------------------------------------


def test_duckdns_servicio_sin_privilegios_y_cada_30_minutos():
    d = _directivas(SYSTEMD / "duckdns.service")
    assert _unica(d, "DynamicUser") == "true"
    assert _unica(d, "LoadCredential") == "duckdns.env:/etc/finanzas/duckdns.env"
    assert _unica(d, "ExecStart") == "/bin/bash /opt/finanzas/deploy/duckdns.sh"
    # No carga el archivo como entorno (quedaría visible en /proc/<pid>/environ).
    assert "EnvironmentFile" not in d
    t = _directivas(SYSTEMD / "duckdns.timer")
    assert _unica(t, "OnUnitActiveSec") == "30min"


def test_duckdns_sh_no_mete_el_token_en_argv():
    texto = (DEPLOY / "duckdns.sh").read_text(encoding="utf-8")
    assert texto.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in texto
    codigo = [l for l in texto.splitlines() if not l.lstrip().startswith("#")]
    for linea in codigo:
        if "curl" in linea:
            assert "token=$" not in linea
            assert "duckdns.org/update" not in linea
    lineas_curl = [l for l in codigo if re.search(r"\bcurl\b", l) and "echo" not in l]
    assert lineas_curl, "no hay llamada a curl"
    for linea in lineas_curl:
        assert "-K -" in linea
        assert "--silent" in linea and "--show-error" in linea and "--fail" in linea
    assert "source" not in "\n".join(codigo)  # el .env se lee, no se ejecuta


TOKEN_FALSO = "01234567-89ab-cdef-0123-456789abcdef"


def _curl_falso(carpeta: Path, respuesta: str, codigo: int = 0) -> Path:
    bin_dir = carpeta / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(
        "#!/bin/bash\n"
        f'printf "%s\\n" "$@" > "{carpeta}/argv.txt"\n'
        f'cat > "{carpeta}/stdin.txt"\n'
        f"printf '{respuesta}'\n"
        f"exit {codigo}\n"
    )
    curl.chmod(curl.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _ejecutar_duckdns(tmp_path: Path, env_texto: str, respuesta="OK", codigo=0):
    if shutil.which("bash") is None:
        pytest.skip("no hay bash")
    credenciales = tmp_path / "cred"
    credenciales.mkdir()
    (credenciales / "duckdns.env").write_text(env_texto)
    bin_dir = _curl_falso(tmp_path, respuesta, codigo)
    entorno = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "CREDENTIALS_DIRECTORY": str(credenciales),
    }
    return subprocess.run(
        ["bash", str(DEPLOY / "duckdns.sh")],
        env=entorno, capture_output=True, text=True, timeout=30,
    )


def test_duckdns_sh_pasa_el_token_por_stdin_y_no_lo_imprime(tmp_path):
    r = _ejecutar_duckdns(
        tmp_path, f"DUCKDNS_DOMINIO=tu-subdominio.duckdns.org\nDUCKDNS_TOKEN={TOKEN_FALSO}\n"
    )
    assert r.returncode == 0, r.stderr
    argv = (tmp_path / "argv.txt").read_text()
    stdin = (tmp_path / "stdin.txt").read_text()
    assert TOKEN_FALSO not in argv
    assert "-K" in argv.split()
    assert stdin == (
        'url = "https://www.duckdns.org/update?domains=tu-subdominio'
        f'&token={TOKEN_FALSO}&ip="\n'
    )
    assert TOKEN_FALSO not in r.stdout + r.stderr


def test_duckdns_sh_falla_si_duckdns_responde_ko(tmp_path):
    r = _ejecutar_duckdns(
        tmp_path, f"DUCKDNS_DOMINIO=tu-subdominio\nDUCKDNS_TOKEN={TOKEN_FALSO}\n", respuesta="KO"
    )
    assert r.returncode != 0
    assert TOKEN_FALSO not in r.stdout + r.stderr


def test_duckdns_sh_falla_si_curl_falla(tmp_path):
    r = _ejecutar_duckdns(
        tmp_path, f"DUCKDNS_DOMINIO=tu-subdominio\nDUCKDNS_TOKEN={TOKEN_FALSO}\n", codigo=22
    )
    assert r.returncode != 0
    assert TOKEN_FALSO not in r.stdout + r.stderr


@pytest.mark.parametrize(
    "contenido",
    [
        f"DUCKDNS_TOKEN={TOKEN_FALSO}\n",  # falta el dominio
        "DUCKDNS_DOMINIO=tu-subdominio\n",  # falta el token
        f'DUCKDNS_DOMINIO=tu-subdominio\nDUCKDNS_TOKEN={TOKEN_FALSO}" -o /tmp/x "\n',
        f"DUCKDNS_DOMINIO=otro&domains=x\nDUCKDNS_TOKEN={TOKEN_FALSO}\n",
    ],
)
def test_duckdns_sh_rechaza_configuracion_invalida_sin_llamar_a_curl(tmp_path, contenido):
    r = _ejecutar_duckdns(tmp_path, contenido)
    assert r.returncode == 2
    assert not (tmp_path / "argv.txt").exists()
    assert TOKEN_FALSO not in r.stdout + r.stderr


# --- Caddy --------------------------------------------------------------------


def test_caddyfile():
    texto = (DEPLOY / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    codigo = "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith("#"))
    assert "{$DOMINIO} {" in codigo
    assert re.search(r"^\s*reverse_proxy 127\.0\.0\.1:8000\s*$", codigo, re.M)
    assert "localhost" not in codigo
    assert re.search(r'header Strict-Transport-Security "max-age=\d+', codigo)
    # Compresión solo para los archivos con hash del frontend (riesgo BREACH en
    # páginas con tokens). Nunca /app entero (el índice) ni /api. Desde el
    # ítem 20 ya no hay /static (se retiraron las plantillas de la v1).
    assert re.search(r"^\s*@estaticos path /app/assets/\*\s*$", codigo, re.M)
    assert "/static" not in codigo
    assert re.search(r"^\s*encode @estaticos zstd gzip\s*$", codigo, re.M)
    assert not re.search(r"^\s*encode (?!@estaticos)", codigo, re.M)
    # Nunca reescribir Host (rompería la verificación de Origin) ni confiar en
    # un X-Forwarded-For del visitante.
    assert "header_up Host" not in texto
    assert not re.search(r"header_up\s+Host", texto, re.I)
    assert "trusted_proxies" not in codigo


def test_caddyfile_explica_x_forwarded_for_y_donde_va_el_dominio():
    texto = (DEPLOY / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    assert "X-Forwarded-For" in texto
    assert "/etc/systemd/system/caddy.service.d/override.conf" in texto
    assert "Environment=DOMINIO=" in texto


# --- Secretos -----------------------------------------------------------------

PATRONES_SECRETO = [
    re.compile(r"scrypt:\d+:\d+:\d+:[0-9a-f]{8,}", re.I),  # hash de contraseña real
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),  # token DuckDNS
    # Token largo (p. ej. token_urlsafe): 40 o más caracteres con letras y números.
    re.compile(r"(?<![\w/.-])(?=[\w-]*\d)(?=[\w-]*[A-Za-z])[\w-]{40,}(?![\w/.-])"),
    re.compile(r"ya29\.[\w-]+|1//[\w-]{20,}"),  # tokens de Google
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


# Única excepción: la huella SHA-256 pública del instalador de Node (paso 6.1,
# ítem 12), siempre en la forma que lee `sha256sum -c`: 64 hexadecimales, dos
# espacios y el nombre exacto del archivo oficial de nodejs.org.
HUELLA_NODE = re.compile(r"\b[0-9a-f]{64}(?=  node-v\d+\.\d+\.\d+-linux-(?:arm64|x64)\.tar\.xz\b)")


def test_ningun_archivo_de_deploy_tiene_secretos():
    archivos = [p for p in DEPLOY.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    assert archivos
    for archivo in archivos:
        texto = HUELLA_NODE.sub("<huella de node>", archivo.read_text(encoding="utf-8"))
        for patron in PATRONES_SECRETO:
            encontrado = patron.search(texto)
            assert encontrado is None, f"{archivo.name}: parece un secreto real"


def test_el_detector_de_secretos_funciona():
    from finanzas.seguridad import generar_hash

    ejemplos = [
        generar_hash("contrasena-de-prueba"),
        "Xy9_" * 16,  # misma forma que secrets.token_urlsafe(48), inventado
        "a1b2c3d4-e5f6-a7b8-c9d0-e1f2a3b4c5d6",
    ]
    for ejemplo in ejemplos:
        assert any(p.search(f"X={ejemplo}\n") for p in PATRONES_SECRETO), ejemplo


def test_la_excepcion_de_la_huella_de_node_es_estrecha():
    huella = "ab12" * 16  # 64 hexadecimales inventados
    assert HUELLA_NODE.sub("", f'echo "{huella}  node-v24.21.0-linux-arm64.tar.xz"') == (
        'echo "  node-v24.21.0-linux-arm64.tar.xz"'
    )
    # Fuera de esa forma exacta, el mismo valor sigue contando como secreto.
    for texto in (f"TOKEN={huella}", f"{huella} node-v24.21.0-linux-arm64.tar.xz", f"{huella}  otro.tar.xz"):
        restante = HUELLA_NODE.sub("", texto)
        assert any(p.search(restante) for p in PATRONES_SECRETO), texto


def test_guia_instala_node_fijo_y_verificado():
    guia = (DEPLOY / "GUIA.md").read_text(encoding="utf-8")
    seccion = _seccion(guia, "6.1 Node y el frontend nuevo")
    assert "https://nodejs.org/dist/v24.21.0/node-v24.21.0-linux-arm64.tar.xz" in seccion
    assert "sha256sum -c -" in seccion
    assert "npm ci --ignore-scripts" in seccion and "npm run build" in seccion
    actualizar = _seccion(guia, "13.2 Actualizar la app")
    assert "npm ci --ignore-scripts" in actualizar and "npm run build" in actualizar


# --- Guía -----------------------------------------------------------------------


def test_guia_cubre_lo_pedido():
    guia = (DEPLOY / "GUIA.md").read_text(encoding="utf-8")
    cerrar = _seccion(guia, "Cerrar todas las sesiones")
    assert "SESSION_SECRET" in cerrar
    assert "systemctl restart finanzas" in cerrar
    for texto in (
        "netfilter-persistent",
        "Security List",
        "chmod 600",
        "reprocesar",
        "Ubuntu",
        "24.04",
        "unattended-upgrades",
        "python3 -m venv",
        "python -m finanzas.seguridad",
        "secrets.token_urlsafe(48)",
        "COOKIE_SECURE=true",
        "DB_PATH",
        "GMAIL_TOKEN",
        "/var/lib/finanzas/gmail/token.json",
        "/var/backups/finanzas",
        "journalctl",
        "systemctl edit finanzas-sync.timer",
        "deploy/verificar.sh",
        "ErrorAutorizacionGmail",
        "database is locked",
        "403",
    ):
        assert texto.lower() in guia.lower(), texto
    # No se usa ufw junto con las reglas de iptables de Oracle.
    assert "No uses `ufw`" in guia


def test_guia_solo_usa_datos_de_ejemplo():
    guia = (DEPLOY / "GUIA.md").read_text(encoding="utf-8")
    ips = set(re.findall(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", guia))
    permitidas = {"0.0.0.0", "127.0.0.1"}
    for ip in ips - permitidas:
        assert ip.startswith("203.0.113."), ip  # rango reservado para documentación
    for dominio in re.findall(r"\b([\w-]+)\.duckdns\.org\b", guia):
        assert dominio in ("tu-subdominio", "www"), dominio


def test_scripts_de_shell_con_sintaxis_valida():
    if shutil.which("bash") is None:
        pytest.skip("no hay bash")
    for script in ("duckdns.sh", "verificar.sh"):
        r = subprocess.run(["bash", "-n", str(DEPLOY / script)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


def test_verificar_sh_exige_dominio_y_no_lee_secretos():
    texto = (DEPLOY / "verificar.sh").read_text(encoding="utf-8")
    assert "set -uo pipefail" in texto
    # Solo lee variables no secretas del .env.
    assert "APP_PASSWORD_HASH" not in texto
    assert "SESSION_SECRET" not in texto
    assert "DUCKDNS_TOKEN" not in texto
    assert "source" not in texto
    assert "ExecMainStatus" in texto
    for requisito in ("strict-transport-security", "content-security-policy", "no-store", "ss -ltn"):
        assert requisito in texto.lower(), requisito
    # Ítem 20: las cabeceras se comprueban en /app/ (ya no hay /login), / debe
    # llevar a /app/, la API sin sesión da 401 en JSON y la PWA tiene lo suyo.
    assert '"https://$DOMINIO/app/"' in texto
    assert "/login" not in texto and "/static" not in texto
    assert '"https://$DOMINIO/" 2>/dev/null' in texto and '"https://$DOMINIO/app/" ]]' in texto
    assert '"https://$DOMINIO/api/sesion"' in texto and '== "401"' in texto and "application/json" in texto
    assert "manifest.webmanifest sw.js" in texto
    if shutil.which("bash") is None:
        pytest.skip("no hay bash")
    r = subprocess.run(["bash", str(DEPLOY / "verificar.sh")], capture_output=True, text=True)
    assert r.returncode == 2


def test_guia_no_escribe_un_hash_vacio():
    """Si las contraseñas no coinciden, los bloques de 7.1 y 13.5 no tocan finanzas.env."""
    guia = (DEPLOY / "GUIA.md").read_text(encoding="utf-8")
    for titulo in ("7.1", "13.5"):
        seccion = _seccion(guia, titulo)
        assert "if [[ $HASH == scrypt:* ]]; then" in seccion, titulo
        assert "exit" not in seccion, titulo  # cerraría la sesión SSH


def _bloques_de_codigo(markdown: str) -> list[str]:
    """Contenido de cada bloque ```...``` (los de los recuadros "> " incluidos)."""
    lineas = [re.sub(r"^\s*> ?", "", l) for l in markdown.splitlines()]
    return re.findall(r"^\s*```[^\n]*\n(.*?)^\s*```\s*$", "\n".join(lineas), re.M | re.S)


def test_guia_la_contrasena_se_pide_en_un_bloque_aparte():
    """7.1 y 13.5: el bloque que pide la contraseña (parte A) no escribe finanzas.env.

    Si se pegara todo junto, las líneas pegadas después de ``finanzas.seguridad``
    se leerían como la contraseña. Por eso la parte A solo genera el hash y la
    parte B (que escribe el archivo) va en otro bloque.
    """
    guia = (DEPLOY / "GUIA.md").read_text(encoding="utf-8")
    for titulo in ("7.1", "13.5"):
        bloques = _bloques_de_codigo(_seccion(guia, titulo))
        parte_a = [b for b in bloques if "finanzas.seguridad" in b]
        assert len(parte_a) == 1, titulo
        a = parte_a[0]
        assert "HASH=$(.venv/bin/python -m finanzas.seguridad)" in a, titulo
        # La parte A no escribe nada ni sigue con más órdenes que se tomarían como contraseña.
        assert "tee /etc/finanzas/finanzas.env" not in a, titulo
        assert "sudo python3 -" not in a, titulo
        assert "if [[" not in a, titulo
        # Tras pedir la contraseña solo muestra el prefijo del hash, nunca el hash entero.
        despues = a.split("finanzas.seguridad)", 1)[1].strip().splitlines()
        assert despues == ['echo "${HASH:0:7}"'], (titulo, despues)
        # La parte B existe en otro bloque y conserva la garantía de no escribir un hash vacío.
        parte_b = [b for b in bloques if "if [[ $HASH == scrypt:* ]]; then" in b]
        assert len(parte_b) == 1, titulo
        assert "finanzas.seguridad" not in parte_b[0], titulo
    bloques_71 = _bloques_de_codigo(_seccion(guia, "7.1"))
    assert any("tee /etc/finanzas/finanzas.env" in b and "if [[ $HASH" in b for b in bloques_71)
    # 7.1 comprueba el archivo contando líneas, sin mostrarlo.
    parte_c = [b for b in bloques_71 if "unset HASH SECRETO" in b]
    assert len(parte_c) == 1
    assert "sudo grep -c = /etc/finanzas/finanzas.env" in parte_c[0]
    assert "sudo grep -c '^APP_PASSWORD_HASH=scrypt:' /etc/finanzas/finanzas.env" in parte_c[0]
    for bloque in _bloques_de_codigo(guia):
        assert not re.search(r"\bcat\b[^\n]*finanzas\.env", bloque), bloque


def test_guia_secretos_solo_de_root():
    guia = (DEPLOY / "GUIA.md").read_text(encoding="utf-8")
    assert "sudo install -d -o root -g root -m 0700 /etc/finanzas" in guia
    assert "sudo install -o root -g root -m 0600 /dev/null /etc/finanzas/finanzas.env" in guia
    assert "-g finanzas -m 0640" not in guia


def test_guia_gmail_opcion_sin_navegador():
    """Sección 8: opción B, autorizar desde la VM con --sin-navegador (ítem 07)."""
    guia = (DEPLOY / "GUIA.md").read_text(encoding="utf-8")
    seccion = _seccion(guia, "8. Gmail")
    assert "--sin-navegador" in seccion
    assert "--borrar-credenciales" in seccion
    opcion_b = _seccion(guia, "Opción B: desde la VM")
    assert "computador compartido" in opcion_b.lower()
    for texto in (
        "sudo install -o finanzas -g finanzas -m 0600 /dev/null /var/lib/finanzas/gmail/client_secret.json",
        "sudo -u finanzas nano /var/lib/finanzas/gmail/client_secret.json",
        "cd /opt/finanzas && sudo -u finanzas .venv/bin/python -m finanzas.gmail autorizar --sin-navegador",
        "http://localhost:1/",
        "sudo stat -c '%U:%G %a %n' /var/lib/finanzas/gmail/token.json",
        "finanzas:finanzas 600",
        "sudo systemctl start finanzas-sync.service",
        "journalctl -u finanzas-sync -n 5 --no-pager",
    ):
        assert texto in opcion_b, texto
    # La opción A (en casa) se mantiene.
    assert "scp -i ~/.ssh/oracle_finanzas ~/token_gmail.json" in _seccion(guia, "Opción A")
    # La plantilla del cliente OAuth es un JSON válido de "App de escritorio".
    plantillas = [b for b in _bloques_de_codigo(opcion_b) if '"installed"' in b]
    assert len(plantillas) == 1
    cliente = json.loads(plantillas[0])["installed"]
    assert {"client_id", "client_secret", "auth_uri", "token_uri", "redirect_uris"} <= set(cliente)
    # "App de escritorio": redirección de loopback en http://localhost (cualquier puerto).
    assert cliente["redirect_uris"] == ["http://localhost"]
    # Y el error esperado del navegador con el puerto 1 está explicado.
    assert "ERR_UNSAFE_PORT" in opcion_b


@pytest.mark.parametrize("ubicacion_paquete", ["backend/finanzas", "finanzas"])
def test_prueba_en_seco_worktree_usa_codigo_elegido(tmp_path, ubicacion_paquete):
    """La receta temporal debe vencer al paquete editable de la app desplegada."""
    guia = (DEPLOY / "GUIA.md").read_text(encoding="utf-8")
    receta = guia.split("worktree add --detach /opt/finanzas-prueba", 1)[1].split(
        "worktree remove --force /opt/finanzas-prueba", 1
    )[0]
    assert "-p Environment=PYTHONPATH=/opt/finanzas-prueba/backend:/opt/finanzas-prueba" in receta
    desplegada = guia.split("código nuevo ya está en `/opt/finanzas`, basta con `systemd-run`", 1)[1].split(
        "python -m finanzas.prueba_en_seco --ayn", 1
    )[0]
    assert "PYTHONPATH=/opt/finanzas-prueba" not in desplegada

    worktree = tmp_path / "finanzas-prueba"
    paquete = worktree / ubicacion_paquete
    paquete.mkdir(parents=True)
    (paquete / "__init__.py").write_text("", encoding="utf-8")
    (paquete / "prueba_en_seco.py").write_text("print('codigo-del-worktree')\n", encoding="utf-8")
    entorno = dict(os.environ, PYTHONPATH=os.pathsep.join((str(worktree / "backend"), str(worktree))))
    resultado = subprocess.run(
        [sys.executable, "-m", "finanzas.prueba_en_seco"],
        cwd=tmp_path, env=entorno, capture_output=True, text=True, timeout=30,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "codigo-del-worktree"
