"""Casos borde del despliegue (ítem 07): duckdns.sh, verificar.sh, respaldo.py,
los comandos de la guía para rotar secretos y la coherencia guía/archivos.

Todo con datos inventados, en carpetas temporales y con comandos simulados en
``PATH`` (curl, systemctl, ss, iptables, stat). Sin red ni systemd reales.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
DEPLOY = RAIZ / "deploy"
GUIA = DEPLOY / "GUIA.md"

necesita_bash = pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="requiere entorno POSIX con bash (Windows/WSL no ejecuta estos mocks)",
)

# Valores inventados. Ninguno es real.
TOKEN_FALSO = "fedcba98-7654-3210-fedc-ba9876543210"
SECRETO_FALSO = "SecretoInventadoDePrueba_abcdefghijklmnopqrstuvwxyz0123456789XYZ"
HASH_FALSO = "scrypt:16384:8:1:" + "ab" * 16 + ":" + "cd" * 32


def _ejecutable(ruta: Path, texto: str) -> None:
    ruta.write_text(texto)
    ruta.chmod(0o755)


# =============================================================================
# duckdns.sh
# =============================================================================


def _duckdns(tmp_path: Path, contenido: str | bytes, respuesta: str = "OK", codigo: int = 0,
             como_argumento: bool = False):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _ejecutable(
        bin_dir / "curl",
        "#!/bin/bash\n"
        f'printf "%s\\n" "$@" > "{tmp_path}/argv.txt"\n'
        f'env > "{tmp_path}/env.txt"\n'
        f'cat > "{tmp_path}/stdin.txt"\n'
        f"printf '%s' '{respuesta}'\n"
        f"exit {codigo}\n",
    )
    cred = tmp_path / "cred"
    cred.mkdir()
    archivo = cred / "duckdns.env"
    if isinstance(contenido, bytes):
        archivo.write_bytes(contenido)
    else:
        archivo.write_text(contenido)
    archivo.chmod(0o600)
    entorno = {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
    argv = ["bash", str(DEPLOY / "duckdns.sh")]
    if como_argumento:
        argv.append(str(archivo))
    else:
        entorno["CREDENTIALS_DIRECTORY"] = str(cred)
    return subprocess.run(argv, env=entorno, capture_output=True, text=True, timeout=30)


def _curl_llamado(tmp_path: Path) -> bool:
    return (tmp_path / "argv.txt").exists()


@necesita_bash
@pytest.mark.parametrize(
    "token",
    [
        "",  # vacío
        "pega-aqui-tu-token",  # el texto de ejemplo de la guía
        TOKEN_FALSO[:-1],  # 35 caracteres
        TOKEN_FALSO + "0",  # 37 caracteres
        "g" + TOKEN_FALSO[1:],  # carácter no hexadecimal
        f'"{TOKEN_FALSO}"',  # entre comillas
        f"{TOKEN_FALSO} ",  # espacio final
        TOKEN_FALSO[:18] + " " + TOKEN_FALSO[19:],  # espacio en medio
        TOKEN_FALSO[:30] + '"\nx="',  # intento de inyectar otra opción de curl
    ],
)
def test_duckdns_token_invalido_no_llama_a_curl(tmp_path, token):
    r = _duckdns(tmp_path, f"DUCKDNS_DOMINIO=tu-subdominio\nDUCKDNS_TOKEN={token}\n")
    assert r.returncode == 2
    assert not _curl_llamado(tmp_path)
    if token:
        assert token.strip().strip('"') not in r.stdout + r.stderr


@necesita_bash
@pytest.mark.parametrize("dominio", ["Tu-Subdominio", "tu_subdominio", "tu subdominio", "a" * 64, ""])
def test_duckdns_dominio_invalido_no_llama_a_curl(tmp_path, dominio):
    r = _duckdns(tmp_path, f"DUCKDNS_DOMINIO={dominio}\nDUCKDNS_TOKEN={TOKEN_FALSO}\n")
    assert r.returncode == 2
    assert not _curl_llamado(tmp_path)
    assert TOKEN_FALSO not in r.stdout + r.stderr


@necesita_bash
def test_duckdns_sin_archivo_de_configuracion(tmp_path):
    entorno = {"PATH": os.environ.get("PATH", ""), "CREDENTIALS_DIRECTORY": str(tmp_path / "no-existe")}
    r = subprocess.run(["bash", str(DEPLOY / "duckdns.sh")], env=entorno, capture_output=True, text=True)
    assert r.returncode == 2


@necesita_bash
@pytest.mark.parametrize("como_argumento", [False, True])
def test_duckdns_token_nunca_en_argv_entorno_ni_salida(tmp_path, como_argumento):
    r = _duckdns(tmp_path, f"DUCKDNS_DOMINIO=tu-subdominio\nDUCKDNS_TOKEN={TOKEN_FALSO}\n",
                 como_argumento=como_argumento)
    assert r.returncode == 0, r.stderr
    assert TOKEN_FALSO not in (tmp_path / "argv.txt").read_text()
    assert TOKEN_FALSO not in (tmp_path / "env.txt").read_text()  # no se exporta
    assert TOKEN_FALSO in (tmp_path / "stdin.txt").read_text()  # solo por stdin
    assert TOKEN_FALSO not in r.stdout + r.stderr
    assert "duckdns.org/update" not in r.stdout + r.stderr


@necesita_bash
@pytest.mark.parametrize("respuesta", ["KO", "", "ok", "OK KO", "<html>error</html>"])
def test_duckdns_respuesta_distinta_de_ok_falla(tmp_path, respuesta):
    r = _duckdns(tmp_path, f"DUCKDNS_DOMINIO=tu-subdominio\nDUCKDNS_TOKEN={TOKEN_FALSO}\n",
                 respuesta=respuesta)
    assert r.returncode != 0
    assert TOKEN_FALSO not in r.stdout + r.stderr


@necesita_bash
def test_duckdns_ok_pero_curl_falla_es_error(tmp_path):
    r = _duckdns(tmp_path, f"DUCKDNS_DOMINIO=tu-subdominio\nDUCKDNS_TOKEN={TOKEN_FALSO}\n",
                 respuesta="OK", codigo=28)
    assert r.returncode == 1
    assert TOKEN_FALSO not in r.stdout + r.stderr


@necesita_bash
def test_duckdns_acepta_finales_de_linea_windows_y_sin_salto_final(tmp_path):
    contenido = f"DUCKDNS_DOMINIO=tu-subdominio.duckdns.org\r\nDUCKDNS_TOKEN={TOKEN_FALSO}".encode()
    r = _duckdns(tmp_path, contenido)
    assert r.returncode == 0, r.stderr
    stdin = (tmp_path / "stdin.txt").read_text()
    assert "domains=tu-subdominio&" in stdin
    assert "\r" not in stdin


@necesita_bash
def test_duckdns_ignora_otras_lineas_y_no_ejecuta_nada(tmp_path):
    marca = tmp_path / "ejecutado"
    contenido = (
        "# comentario\n"
        f"touch {marca}\n"
        f"$(touch {marca})\n"
        "DUCKDNS_DOMINIO=tu-subdominio\n"
        f"DUCKDNS_TOKEN={TOKEN_FALSO}\n"
    )
    r = _duckdns(tmp_path, contenido)
    assert r.returncode == 0, r.stderr
    assert not marca.exists()


# =============================================================================
# verificar.sh
# =============================================================================

# Ítem 20: las cabeceras se piden a /app/ (el cascarón del frontend, con la
# CSP completa de la app); ya no hay /login.
CABECERAS_BUENAS = (
    "HTTP/2 200\r\n"
    "strict-transport-security: max-age=31536000\r\n"
    "content-security-policy: default-src 'self'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; object-src 'none'\r\n"
    "cache-control: no-store\r\n"
    "\r\n"
)
SS_APP_BUENO = "LISTEN 0 2048 127.0.0.1:8000 0.0.0.0:*\n"
SS_TODO_BUENO = (
    "LISTEN 0 4096 127.0.0.53%lo:53 0.0.0.0:*\n"
    "LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\n"
    "LISTEN 0 2048 127.0.0.1:8000 0.0.0.0:*\n"
    "LISTEN 0 4096 *:80 *:*\n"
    "LISTEN 0 4096 *:443 *:*\n"
    "LISTEN 0 128 [::]:22 [::]:*\n"
    "LISTEN 0 4096 [::1]:2019 [::]:*\n"
)
IPTABLES_BUENO = (
    "-P INPUT ACCEPT\n"
    "-A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT\n"
    "-A INPUT -p tcp -m state --state NEW -m tcp --dport 22 -j ACCEPT\n"
    "-A INPUT -p tcp -m state --state NEW -m tcp --dport 80 -j ACCEPT\n"
    "-A INPUT -p tcp -m state --state NEW -m tcp --dport 443 -j ACCEPT\n"
    "-A INPUT -j REJECT --reject-with icmp-host-prohibited\n"
)

SIMULADOS = {
    "systemctl": r"""#!/bin/bash
M="$MOCK_DIR"
case "$1" in
  is-active|is-enabled)
    u="${@: -1}"
    grep -qxF "$1 $u" "$M/caidas.txt" 2>/dev/null && exit 3
    exit 0 ;;
  show)
    case "$*" in
      *ExecMainExitTimestampMonotonic*) cat "$M/sync_ts.txt" ;;
      *ExecMainStatus*) cat "$M/sync_status.txt" ;;
    esac
    exit 0 ;;
esac
exit 1
""",
    "curl": r"""#!/bin/bash
M="$MOCK_DIR"
printf '%s\n' "$*" >> "$M/curl_argv.txt"
url="${@: -1}"
for a in "$@"; do
  if [[ "$a" == "-D" ]]; then
    [[ "$url" == https://*/app/ ]] && { cat "$M/cabeceras.txt"; exit 0; }
    exit 7
  fi
done
case "$url" in
  http://*) cat "$M/redireccion.txt" ;;
  https://*/api/sesion) cat "$M/api_sesion.txt" ;;
  https://*/app/manifest.webmanifest) cat "$M/manifest.txt" ;;
  https://*/app/sw.js) cat "$M/sw.txt" ;;
  https://*/) cat "$M/raiz.txt" ;;
  *) exit 7 ;;
esac
""",
    "ss": r"""#!/bin/bash
M="$MOCK_DIR"
if [[ "$*" == *sport* ]]; then cat "$M/ss_app.txt"; else cat "$M/ss_todo.txt"; fi
""",
    "iptables": r"""#!/bin/bash
cat "$MOCK_DIR/iptables.txt"
""",
    # runuser -u finanzas -- python -m finanzas.migrar ... --comprobar (ítem 22).
    "runuser": r"""#!/bin/bash
printf '%s\n' "$*" >> "$MOCK_DIR/runuser_argv.txt"
exit "$(cat "$MOCK_DIR/migrar.txt")"
""",
    # stat -c FORMATO -- RUTA: responde según stat.txt ("ruta<TAB>usuario:grupo modo").
    "stat": r"""#!/bin/bash
ruta="${@: -1}"
linea="$(grep -F -- "$ruta	" "$MOCK_DIR/stat.txt" | head -n 1)"
[[ -z "$linea" ]] && exit 1
printf '%s\n' "${linea#*	}"
""",
}


class Escenario:
    """VM simulada donde todas las comprobaciones de verificar.sh pasan."""

    def __init__(self, raiz: Path):
        self.raiz = raiz
        self.mock = raiz / "mock"
        self.bin = raiz / "bin"
        self.etc = raiz / "etc"
        self.datos = raiz / "datos"
        self.respaldos = raiz / "respaldos"
        for carpeta in (self.mock, self.bin, self.etc, self.datos / "gmail", self.respaldos):
            carpeta.mkdir(parents=True)
        for nombre, texto in SIMULADOS.items():
            _ejecutable(self.bin / nombre, texto)
        self.db = self.datos / "finanzas.db"
        self.token = self.datos / "gmail" / "token.json"
        self.db.write_bytes(b"base inventada")
        self.token.write_text('{"refresh_token": "inventado"}')
        self.env = {
            "APP_PASSWORD_HASH": HASH_FALSO,
            "SESSION_SECRET": SECRETO_FALSO,
            "COOKIE_SECURE": "true",
            "DB_PATH": str(self.db),
            "GMAIL_TOKEN": str(self.token),
        }
        (self.etc / "duckdns.env").write_text(f"DUCKDNS_DOMINIO=tu-subdominio\nDUCKDNS_TOKEN={TOKEN_FALSO}\n")
        hoy = subprocess.run(["date", "+%F"], capture_output=True, text=True).stdout.strip()
        self.respaldo = self.respaldos / f"finanzas-{hoy}.db"
        self.respaldo.write_bytes(b"respaldo inventado")
        # Compilación del frontend (ítem 12) en APP_DIR/frontend/dist.
        self.indice_frontend = raiz / "frontend" / "dist" / "index.html"
        self.indice_frontend.parent.mkdir(parents=True)
        self.indice_frontend.write_text("<!doctype html>")
        self.permisos = {
            # Ronda 1 del ítem 07: systemd lee el .env como root, así que la
            # carpeta y finanzas.env pasan a ser solo de root (antes 750/640).
            self.etc: "root:root 700",
            self.etc / "finanzas.env": "root:root 600",
            self.etc / "duckdns.env": "root:root 600",
            self.datos: "finanzas:finanzas 700",
            self.respaldos: "finanzas:finanzas 700",
            self.db: "finanzas:finanzas 600",
            self.token.parent: "finanzas:finanzas 700",
            self.token: "finanzas:finanzas 600",
            self.respaldo: "finanzas:finanzas 600",
        }
        self.archivos = {
            "caidas.txt": "",
            "sync_ts.txt": "123456789\n",
            "sync_status.txt": "0\n",
            "cabeceras.txt": CABECERAS_BUENAS,
            "redireccion.txt": "308 https://tu-subdominio.duckdns.org/",
            "raiz.txt": "307 https://tu-subdominio.duckdns.org/app/",
            "api_sesion.txt": "401 application/json",
            "manifest.txt": "200",
            "sw.txt": "200",
            "ss_app.txt": SS_APP_BUENO,
            "ss_todo.txt": SS_TODO_BUENO,
            "iptables.txt": IPTABLES_BUENO,
            "migrar.txt": "0\n",
        }
        self.env_extra = ""

    def ejecutar(self):
        texto_env = "".join(f"{k}={v}\n" for k, v in self.env.items()) + self.env_extra
        (self.etc / "finanzas.env").write_text(texto_env)
        for nombre, texto in self.archivos.items():
            (self.mock / nombre).write_text(texto)
        (self.mock / "stat.txt").write_text(
            "".join(f"{ruta}\t{valor}\n" for ruta, valor in self.permisos.items())
        )
        entorno = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}",
            "MOCK_DIR": str(self.mock),
            "ETC_DIR": str(self.etc),
            "DATOS_DIR": str(self.datos),
            "RESPALDOS_DIR": str(self.respaldos),
            "APP_DIR": str(self.raiz),
            "LANG": "C.UTF-8",
        }
        return subprocess.run(
            ["bash", str(DEPLOY / "verificar.sh"), "tu-subdominio.duckdns.org"],
            env=entorno, capture_output=True, text=True, timeout=60,
        )


requiere_root = pytest.mark.skipif(
    getattr(os, "geteuid", lambda: -1)() != 0, reason="verificar.sh exige root POSIX"
)


@pytest.fixture
def vm(tmp_path):
    return Escenario(tmp_path)


def _sin_secretos(r) -> None:
    salida = r.stdout + r.stderr
    for secreto in (SECRETO_FALSO, HASH_FALSO, TOKEN_FALSO, "refresh_token", "inventado"):
        assert secreto not in salida, secreto


def _fallos(r) -> list[str]:
    return [l for l in r.stdout.splitlines() if l.startswith("✘")]


@necesita_bash
@requiere_root
def test_verificar_todo_en_orden(vm):
    r = vm.ejecutar()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Todo en orden." in r.stdout
    assert _fallos(r) == []
    _sin_secretos(r)


@necesita_bash
@requiere_root
def test_verificar_comprueba_la_migracion_como_finanzas_y_sin_escribir(vm):
    # Ítem 22: solo --comprobar (no escribe) y como el usuario de la app.
    r = vm.ejecutar()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "la base de datos está en la última migración" in r.stdout
    argv = (vm.mock / "runuser_argv.txt").read_text().split()
    assert argv[:3] == ["-u", "finanzas", "--"]
    assert argv[argv.index("--base") + 1] == str(vm.db)
    assert "--comprobar" in argv
    assert "--respaldos" not in argv and "--bajar-a" not in argv


def _caer(unidad):
    return lambda vm: vm.archivos.__setitem__("caidas.txt", f"is-active {unidad}\n")


def _cabeceras_sin(nombre):
    return lambda vm: vm.archivos.__setitem__(
        "cabeceras.txt", "".join(l + "\r\n" for l in CABECERAS_BUENAS.split("\r\n") if not l.startswith(nombre))
    )


def _permiso(atributo, valor):
    def cambiar(vm):
        ruta = atributo(vm)
        vm.permisos[ruta] = valor
    return cambiar


def _sin_permiso(atributo):
    return lambda vm: vm.permisos.pop(atributo(vm))


def _sin_variable(nombre):
    return lambda vm: vm.env.pop(nombre)


CASOS_FALLO = {
    "finanzas.service caído": (_caer("finanzas.service"), "finanzas.service no está activo"),
    "caddy.service caído": (_caer("caddy.service"), "caddy.service no está activo"),
    "timer sync caído": (_caer("finanzas-sync.timer"), "finanzas-sync.timer no está activo"),
    "timer respaldo caído": (_caer("finanzas-respaldo.timer"), "finanzas-respaldo.timer no está activo"),
    "timer duckdns caído": (_caer("duckdns.timer"), "duckdns.timer no está activo"),
    "servicio no habilitado": (
        lambda vm: vm.archivos.__setitem__("caidas.txt", "is-enabled finanzas.service\n"),
        "finanzas.service no está activo",
    ),
    "sync nunca ejecutado": (lambda vm: vm.archivos.__setitem__("sync_ts.txt", "0\n"), "todavía no se ha ejecutado"),
    "sync con código 1": (lambda vm: vm.archivos.__setitem__("sync_status.txt", "1\n"), "terminó con código 1"),
    "sync con código 2": (lambda vm: vm.archivos.__setitem__("sync_status.txt", "2\n"), "terminó con código 2"),
    "sin respaldo": (lambda vm: vm.respaldo.unlink(), "no hay respaldo de hoy ni de ayer"),
    "respaldo vacío": (lambda vm: vm.respaldo.write_bytes(b""), "no hay respaldo de hoy ni de ayer"),
    "respaldo legible por otros": (
        _permiso(lambda vm: vm.respaldo, "finanzas:finanzas 644"), "permisos del respaldo: es finanzas:finanzas 644"
    ),
    "/app no responde 200": (
        lambda vm: vm.archivos.__setitem__("cabeceras.txt", CABECERAS_BUENAS.replace("HTTP/2 200", "HTTP/2 503")),
        "/app/ no responde 200 (respondió: 503)",
    ),
    "https no responde": (
        lambda vm: vm.archivos.__setitem__("cabeceras.txt", CABECERAS_BUENAS.replace("HTTP/2 200", "HTTP/2 502")),
        "no responde 200 (respondió: 502)",
    ),
    "sin HSTS": (_cabeceras_sin("strict-transport-security"), "falta HSTS"),
    "HSTS con max-age=0": (
        lambda vm: vm.archivos.__setitem__("cabeceras.txt", CABECERAS_BUENAS.replace("max-age=31536000", "max-age=0")),
        "falta HSTS",
    ),
    "sin CSP": (_cabeceras_sin("content-security-policy"), "falta Content-Security-Policy"),
    "CSP con unsafe-inline": (
        lambda vm: vm.archivos.__setitem__(
            "cabeceras.txt", CABECERAS_BUENAS.replace("style-src 'self';", "style-src 'self' 'unsafe-inline';")
        ),
        "/app no lleva la CSP estricta",
    ),
    "CSP sin script-src": (
        lambda vm: vm.archivos.__setitem__("cabeceras.txt", CABECERAS_BUENAS.replace("script-src 'self'; ", "")),
        "/app no lleva la CSP estricta",
    ),
    "sin no-store": (_cabeceras_sin("cache-control"), "falta Cache-Control: no-store"),
    "frontend sin compilar": (lambda vm: vm.indice_frontend.unlink(), "el frontend no está compilado"),
    "/ sigue siendo la v1": (
        lambda vm: vm.archivos.__setitem__("raiz.txt", "303 https://tu-subdominio.duckdns.org/login"),
        "no redirige a /app/",
    ),
    "/ responde 200": (lambda vm: vm.archivos.__setitem__("raiz.txt", "200 "), "no redirige a /app/"),
    "/ con 301": (
        lambda vm: vm.archivos.__setitem__("raiz.txt", "301 https://tu-subdominio.duckdns.org/app/"),
        "no redirige a /app/",
    ),
    "/ lleva a otro dominio": (
        lambda vm: vm.archivos.__setitem__("raiz.txt", "307 https://otro.example/app/"), "no redirige a /app/"
    ),
    "/api/sesion da 200 sin sesión": (
        lambda vm: vm.archivos.__setitem__("api_sesion.txt", "200 application/json"), "no responde 401 en JSON"
    ),
    "/api/sesion redirige": (
        lambda vm: vm.archivos.__setitem__("api_sesion.txt", "303 text/html"), "no responde 401 en JSON"
    ),
    "/api/sesion 401 en HTML": (
        lambda vm: vm.archivos.__setitem__("api_sesion.txt", "401 text/html; charset=utf-8"),
        "no responde 401 en JSON",
    ),
    "sin manifest": (
        lambda vm: vm.archivos.__setitem__("manifest.txt", "404"), "/app/manifest.webmanifest no responde 200"
    ),
    "sin sw.js": (lambda vm: vm.archivos.__setitem__("sw.txt", "503"), "/app/sw.js no responde 200"),
    "http sin redirección": (lambda vm: vm.archivos.__setitem__("redireccion.txt", "200 "), "no redirige a https"),
    "http redirige a http": (
        lambda vm: vm.archivos.__setitem__("redireccion.txt", "301 http://tu-subdominio.duckdns.org/"),
        "no redirige a https",
    ),
    "nada en el puerto 8000": (lambda vm: vm.archivos.__setitem__("ss_app.txt", ""), "nada escucha en el puerto 8000"),
    "puerto público extra": (
        lambda vm: vm.archivos.__setitem__("ss_todo.txt", SS_TODO_BUENO + "LISTEN 0 128 0.0.0.0:5432 0.0.0.0:*\n"),
        "hay puertos TCP escuchando hacia fuera: 5432",
    ),
    "puerto público extra en IPv6": (
        lambda vm: vm.archivos.__setitem__("ss_todo.txt", SS_TODO_BUENO + "LISTEN 0 128 [::]:9090 [::]:*\n"),
        "hay puertos TCP escuchando hacia fuera: 9090",
    ),
    "iptables sin 443": (
        lambda vm: vm.archivos.__setitem__(
            "iptables.txt", "\n".join(l for l in IPTABLES_BUENO.splitlines() if "--dport 443" not in l) + "\n"
        ),
        "iptables no acepta el puerto 443",
    ),
    "iptables 80 después del REJECT": (
        lambda vm: vm.archivos.__setitem__(
            "iptables.txt",
            IPTABLES_BUENO.replace("-A INPUT -p tcp -m state --state NEW -m tcp --dport 80 -j ACCEPT\n", "")
            + "-A INPUT -p tcp -m state --state NEW -m tcp --dport 80 -j ACCEPT\n",
        ),
        "iptables no acepta el puerto 80",
    ),
    "iptables solo 8080": (
        lambda vm: vm.archivos.__setitem__("iptables.txt", IPTABLES_BUENO.replace("--dport 80 ", "--dport 8080 ")),
        "iptables no acepta el puerto 80",
    ),
    "carpeta etc mal": (_permiso(lambda vm: vm.etc, "root:root 755"), "carpeta "),
    "finanzas.env legible por todos": (
        _permiso(lambda vm: vm.etc / "finanzas.env", "root:finanzas 644"), "finanzas.env: es root:finanzas 644"
    ),
    "duckdns.env legible por el grupo": (
        _permiso(lambda vm: vm.etc / "duckdns.env", "root:finanzas 640"), "duckdns.env: es root:finanzas 640"
    ),
    "duckdns.env no existe": (_sin_permiso(lambda vm: vm.etc / "duckdns.env"), "duckdns.env: no existe"),
    "carpeta de datos mal": (_permiso(lambda vm: vm.datos, "finanzas:finanzas 755"), "carpeta de datos"),
    "carpeta de respaldos mal": (
        _permiso(lambda vm: vm.respaldos, "root:root 755"), "carpeta de respaldos"
    ),
    "base legible por otros": (_permiso(lambda vm: vm.db, "finanzas:finanzas 644"), "base de datos: es"),
    "carpeta del token mal": (
        _permiso(lambda vm: vm.token.parent, "finanzas:finanzas 755"), "carpeta del token de Gmail: es"
    ),
    "token legible por otros": (_permiso(lambda vm: vm.token, "finanzas:finanzas 644"), "token de Gmail: es"),
    "base sin migrar": (
        lambda vm: vm.archivos.__setitem__("migrar.txt", "1\n"), "no está en la última migración"
    ),
    "sin DB_PATH": (_sin_variable("DB_PATH"), "finanzas.env no define DB_PATH"),
    "sin GMAIL_TOKEN": (_sin_variable("GMAIL_TOKEN"), "finanzas.env no define GMAIL_TOKEN"),
    "COOKIE_SECURE=false": (lambda vm: vm.env.__setitem__("COOKIE_SECURE", "false"), "COOKIE_SECURE no es true"),
    "sin COOKIE_SECURE": (_sin_variable("COOKIE_SECURE"), "COOKIE_SECURE no es true"),
    "COOKIE_SECURE repetido, gana el último": (
        lambda vm: setattr(vm, "env_extra", "COOKIE_SECURE=false\n"), "COOKIE_SECURE no es true"
    ),
}


@necesita_bash
@requiere_root
@pytest.mark.parametrize("caso", list(CASOS_FALLO), ids=list(CASOS_FALLO))
def test_verificar_cada_comprobacion_falla_por_separado(vm, caso):
    romper, esperado = CASOS_FALLO[caso]
    romper(vm)
    r = vm.ejecutar()
    assert r.returncode == 1, r.stdout
    fallos = _fallos(r)
    assert len(fallos) == 1, fallos
    assert esperado in fallos[0], fallos
    assert "Fallaron 1 comprobaciones." in r.stdout
    _sin_secretos(r)


@necesita_bash
@requiere_root
@pytest.mark.parametrize(
    "linea",
    ["LISTEN 0 4096 0.0.0.0:111 0.0.0.0:*\n", "LISTEN 0 4096 [::]:111 [::]:*\n"],
    ids=["ipv4", "ipv6"],
)
def test_verificar_puerto_111_sugiere_apagar_rpcbind(vm, linea):
    # Las imágenes de Oracle traen rpcbind en el 111: la pista dice qué es y cómo apagarlo.
    vm.archivos["ss_todo.txt"] = SS_TODO_BUENO + linea
    r = vm.ejecutar()
    assert r.returncode == 1, r.stdout
    fallos = _fallos(r)
    assert len(fallos) == 1, fallos
    assert "hay puertos TCP escuchando hacia fuera: 111" in fallos[0]
    lineas = r.stdout.splitlines()
    pista = lineas[lineas.index(fallos[0]) + 1]
    assert pista.lstrip().startswith("→")
    assert "rpcbind" in pista
    assert "sudo systemctl disable --now rpcbind.socket rpcbind.service" in pista
    _sin_secretos(r)


@necesita_bash
@requiere_root
def test_verificar_otro_puerto_no_menciona_rpcbind(vm):
    vm.archivos["ss_todo.txt"] = SS_TODO_BUENO + "LISTEN 0 128 0.0.0.0:5432 0.0.0.0:*\n"
    r = vm.ejecutar()
    assert r.returncode == 1
    assert "rpcbind" not in r.stdout
    assert "sudo ss -ltnp" in r.stdout


@necesita_bash
@requiere_root
def test_verificar_app_en_todas_las_interfaces_se_detecta(vm):
    # Si uvicorn escucha en 0.0.0.0:8000 fallan dos: la de la app y la de puertos públicos.
    vm.archivos["ss_app.txt"] = "LISTEN 0 2048 0.0.0.0:8000 0.0.0.0:*\n"
    vm.archivos["ss_todo.txt"] = SS_TODO_BUENO.replace("127.0.0.1:8000", "0.0.0.0:8000")
    r = vm.ejecutar()
    assert r.returncode == 1
    texto = "\n".join(_fallos(r))
    assert "la app escucha fuera de 127.0.0.1" in texto
    assert "8000" in texto
    _sin_secretos(r)


@necesita_bash
@requiere_root
def test_verificar_respaldo_de_ayer_basta(vm):
    ayer = subprocess.run(["date", "-d", "yesterday", "+%F"], capture_output=True, text=True).stdout.strip()
    nuevo = vm.respaldos / f"finanzas-{ayer}.db"
    vm.respaldo.rename(nuevo)
    vm.permisos[nuevo] = vm.permisos.pop(vm.respaldo)
    r = vm.ejecutar()
    assert r.returncode == 0, r.stdout


@necesita_bash
@requiere_root
def test_verificar_todo_roto_no_muestra_secretos(vm):
    # Peor caso: todo falla y el env tiene valores con comillas y espacios.
    vm.env["SESSION_SECRET"] = f'"{SECRETO_FALSO}"'
    vm.env["COOKIE_SECURE"] = "false"
    vm.archivos.update({
        "caidas.txt": "is-active finanzas.service\nis-active caddy.service\n",
        "sync_status.txt": "2\n", "cabeceras.txt": "", "redireccion.txt": "",
        "ss_app.txt": "", "iptables.txt": "",
    })
    vm.permisos.clear()
    r = vm.ejecutar()
    assert r.returncode == 1
    assert len(_fallos(r)) >= 10
    _sin_secretos(r)


@necesita_bash
@requiere_root
def test_verificar_rechaza_dominio_con_caracteres_raros(vm):
    r = subprocess.run(
        ["bash", str(DEPLOY / "verificar.sh"), "tu-subdominio.duckdns.org/$(id)"],
        capture_output=True, text=True,
    )
    assert r.returncode == 2


# =============================================================================
# respaldo.py
# =============================================================================

_spec = importlib.util.spec_from_file_location("respaldo_bordes", DEPLOY / "respaldo.py")
respaldo = importlib.util.module_from_spec(_spec)
sys.modules["respaldo_bordes"] = respaldo
_spec.loader.exec_module(respaldo)

HOY = date(2026, 9, 29)


def _base_valida(ruta: Path, filas: int = 200) -> None:
    conn = sqlite3.connect(ruta)
    with conn:
        conn.execute("CREATE TABLE movimientos (id INTEGER PRIMARY KEY, comercio TEXT, monto INTEGER)")
        conn.executemany(
            "INSERT INTO movimientos (comercio, monto) VALUES (?, ?)",
            [(f"COMERCIO INVENTADO {i:04d} " + "x" * 200, i * 1000) for i in range(filas)],
        )
    conn.close()


@pytest.fixture
def carpetas(tmp_path):
    datos = tmp_path / "datos"
    destino = tmp_path / "respaldos"
    datos.mkdir()
    destino.mkdir(mode=0o700)
    return datos / "finanzas.db", destino


def _argv(origen, destino, *extra):
    return ["--origen", str(origen), "--destino", str(destino), *extra]


def _contenido(destino: Path) -> list[str]:
    return sorted(p.name for p in destino.iterdir())


def test_respaldo_origen_no_es_sqlite_falla_sin_dejar_nada(carpetas, caplog):
    origen, destino = carpetas
    origen.write_bytes(b"esto no es una base SQLite, solo texto inventado " * 100)
    assert respaldo.main(_argv(origen, destino), hoy=HOY) == 1
    assert _contenido(destino) == []
    assert "texto inventado" not in caplog.text


def test_respaldo_base_con_paginas_corruptas_falla_sin_dejar_nada(carpetas):
    origen, destino = carpetas
    _base_valida(origen)
    datos = bytearray(origen.read_bytes())
    tam_pagina = int.from_bytes(datos[16:18], "big")
    assert len(datos) > 4 * tam_pagina
    # Destroza el contenido de las páginas 2 en adelante (la cabecera sigue bien).
    for i in range(tam_pagina, len(datos)):
        datos[i] = 0xA5
    origen.write_bytes(bytes(datos))
    assert respaldo.main(_argv(origen, destino), hoy=HOY) == 1
    assert _contenido(destino) == []


def test_respaldo_base_truncada_falla_sin_dejar_nada(carpetas):
    origen, destino = carpetas
    _base_valida(origen)
    datos = origen.read_bytes()
    origen.write_bytes(datos[: len(datos) // 2])
    assert respaldo.main(_argv(origen, destino), hoy=HOY) == 1
    assert _contenido(destino) == []


def test_respaldo_base_corrupta_no_toca_el_respaldo_bueno_de_hoy(carpetas):
    origen, destino = carpetas
    _base_valida(origen)
    assert respaldo.main(_argv(origen, destino), hoy=HOY) == 0
    bueno = destino / "finanzas-2026-09-29.db"
    antes = bueno.read_bytes()
    origen.write_bytes(b"basura inventada" * 500)
    assert respaldo.main(_argv(origen, destino), hoy=HOY) == 1
    assert _contenido(destino) == ["finanzas-2026-09-29.db"]
    assert bueno.read_bytes() == antes


def test_respaldo_origen_es_directorio(carpetas):
    origen, destino = carpetas
    origen.mkdir()
    assert respaldo.main(_argv(origen, destino), hoy=HOY) == 1
    assert _contenido(destino) == []


def test_respaldo_dos_veces_el_mismo_dia(carpetas):
    origen, destino = carpetas
    _base_valida(origen, filas=5)
    assert respaldo.main(_argv(origen, destino), hoy=HOY) == 0
    conn = sqlite3.connect(origen)
    with conn:
        conn.execute("INSERT INTO movimientos (comercio, monto) VALUES ('COMERCIO NUEVO INVENTADO', 1)")
    conn.close()
    assert respaldo.main(_argv(origen, destino), hoy=HOY) == 0
    assert _contenido(destino) == ["finanzas-2026-09-29.db"]  # uno solo, sin temporales
    final = destino / "finanzas-2026-09-29.db"
    assert stat.S_IMODE(final.stat().st_mode) == 0o600
    conn = sqlite3.connect(final)
    assert conn.execute("SELECT COUNT(*) FROM movimientos").fetchone() == (6,)
    conn.close()


@pytest.mark.parametrize(
    "nombre",
    [
        "finanzas-2020-01-01.db~",
        "finanzas-2020-01-01.DB",
        "finanzas-2020-01-01.db.gz",
        "finanzas-2020-01-01db",
        "finanzas_2020-01-01.db",
        "finanzas-20200101.db",
        "finanzas-2020-01-01 .db",
        " finanzas-2020-01-01.db",
        "finanzas-2020-02-30.db",  # fecha imposible
        "finanzas-0000-01-01.db",
        "finanzas-2020-01-01.db-journal",
        "finanzas-2020-01-01.db-wal",
    ],
)
def test_rotacion_no_borra_nombres_parecidos(carpetas, nombre):
    _, destino = carpetas
    ruta = destino / nombre
    ruta.write_bytes(b"x")
    assert respaldo.rotar(destino, HOY, 1) == []
    assert ruta.exists()


def test_rotacion_no_sigue_enlaces_ni_borra_su_destino(carpetas, tmp_path):
    _, destino = carpetas
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    importante = fuera / "importante.db"
    importante.write_bytes(b"dato inventado importante")
    # Un respaldo viejo real dentro de destino, y enlaces con el patrón que apuntan a él y fuera.
    viejo_real = destino / "finanzas-2020-01-01.db"
    viejo_real.write_bytes(b"x")
    (destino / "finanzas-2020-01-02.db").symlink_to(importante)
    (destino / "finanzas-2020-01-03.db").symlink_to(fuera)
    (destino / "finanzas-2020-01-04.db").symlink_to(tmp_path / "no-existe")  # enlace roto
    carpeta_patron = destino / "finanzas-2020-01-05.db"
    carpeta_patron.mkdir()
    (carpeta_patron / "finanzas-2020-01-01.db").write_bytes(b"x")  # anidado: no se recorre

    borrados = respaldo.rotar(destino, HOY, 14)
    assert borrados == [viejo_real]
    assert importante.read_bytes() == b"dato inventado importante"
    for n in ("finanzas-2020-01-02.db", "finanzas-2020-01-03.db", "finanzas-2020-01-04.db"):
        assert (destino / n).is_symlink()
    assert (carpeta_patron / "finanzas-2020-01-01.db").exists()


def test_respaldo_de_hoy_como_enlace_no_escribe_en_el_destino_del_enlace(carpetas, tmp_path):
    origen, destino = carpetas
    _base_valida(origen, filas=3)
    ajeno = tmp_path / "ajeno.txt"
    ajeno.write_bytes(b"archivo ajeno inventado")
    (destino / "finanzas-2026-09-29.db").symlink_to(ajeno)
    assert respaldo.main(_argv(origen, destino), hoy=HOY) == 0
    final = destino / "finanzas-2026-09-29.db"
    assert not final.is_symlink()
    assert ajeno.read_bytes() == b"archivo ajeno inventado"


def test_rotacion_limite_exacto_de_dias(carpetas):
    _, destino = carpetas
    justo = destino / "finanzas-2026-09-15.db"  # 14 días: se conserva
    pasado = destino / "finanzas-2026-09-14.db"  # 15 días: se borra
    justo.write_bytes(b"x")
    pasado.write_bytes(b"x")
    assert respaldo.rotar(destino, HOY, 14) == [pasado]
    assert justo.exists()


# =============================================================================
# Comandos de la guía para rotar SESSION_SECRET y la contraseña (13.4 y 13.5)
# =============================================================================

RUTA_ENV_GUIA = "/etc/finanzas/finanzas.env"


def _bloque_python(marca: str) -> tuple[str, str]:
    """Devuelve (línea de apertura del heredoc, cuerpo) del bloque que contiene ``marca``."""
    texto = GUIA.read_text(encoding="utf-8")
    patron = re.compile(r"^(sudo python3 - <<'?EOF'?)\n(.*?)^EOF$", re.M | re.S)
    for m in patron.finditer(texto):
        if marca in m.group(2):
            return m.group(1), m.group(2)
    raise AssertionError(f"la guía no tiene un bloque python con {marca!r}")


def _env_temporal(tmp_path: Path) -> Path:
    ruta = tmp_path / "finanzas.env"
    ruta.write_text(
        f"APP_PASSWORD_HASH={HASH_FALSO}\n"
        f"SESSION_SECRET={SECRETO_FALSO}\n"
        "COOKIE_SECURE=true\n"
        "DB_PATH=/var/lib/finanzas/finanzas.db\n"
        "GMAIL_TOKEN=/var/lib/finanzas/gmail/token.json\n"
    )
    # Ronda 1 del ítem 07: finanzas.env es 0600 root:root (antes 0640).
    os.chmod(ruta, 0o600)
    if os.geteuid() == 0:
        os.chown(ruta, 0, 4242)  # grupo inventado, para ver que se conserva
    return ruta


def _ejecutar_bloque(marca: str, ruta: Path, variables: dict[str, str] | None = None):
    apertura, cuerpo = _bloque_python(marca)
    assert cuerpo.count(RUTA_ENV_GUIA) == 1
    cuerpo = cuerpo.replace(RUTA_ENV_GUIA, str(ruta))
    guion = "".join(f"{k}='{v}'\n" for k, v in (variables or {}).items())
    guion += apertura.replace("sudo ", "") + "\n" + cuerpo + "EOF\n"
    return subprocess.run(["bash", "-c", guion], capture_output=True, text=True, timeout=30)


def _leer_env(ruta: Path) -> dict[str, str]:
    return dict(l.split("=", 1) for l in ruta.read_text().splitlines() if l)


@necesita_bash
def test_guia_cambiar_session_secret(tmp_path):
    ruta = _env_temporal(tmp_path)
    antes = _leer_env(ruta)
    st_antes = ruta.stat()
    r = _ejecutar_bloque("SESSION_SECRET", ruta)
    assert r.returncode == 0, r.stderr
    despues = _leer_env(ruta)
    assert list(despues) == list(antes)  # mismas variables y mismo orden
    assert despues["SESSION_SECRET"] != SECRETO_FALSO
    assert re.fullmatch(r"[A-Za-z0-9_-]{64}", despues["SESSION_SECRET"])
    for clave in antes:
        if clave != "SESSION_SECRET":
            assert despues[clave] == antes[clave]
    st = ruta.stat()
    assert stat.S_IMODE(st.st_mode) == 0o600  # ronda 1: antes 0o640
    assert (st.st_uid, st.st_gid) == (st_antes.st_uid, st_antes.st_gid)
    assert st.st_ino == st_antes.st_ino  # se reescribe el mismo archivo
    salida = r.stdout + r.stderr
    assert despues["SESSION_SECRET"] not in salida
    assert SECRETO_FALSO not in salida


@necesita_bash
def test_guia_cambiar_session_secret_dos_veces_da_valores_distintos(tmp_path):
    ruta = _env_temporal(tmp_path)
    assert _ejecutar_bloque("SESSION_SECRET", ruta).returncode == 0
    primero = _leer_env(ruta)["SESSION_SECRET"]
    assert _ejecutar_bloque("SESSION_SECRET", ruta).returncode == 0
    assert _leer_env(ruta)["SESSION_SECRET"] != primero


@necesita_bash
@pytest.mark.parametrize(
    "marca, contenido",
    [
        ("SESSION_SECRET", "APP_PASSWORD_HASH=x\nCOOKIE_SECURE=true\n"),  # falta
        ("SESSION_SECRET", "SESSION_SECRET=a\nSESSION_SECRET=b\n"),  # repetida
        ("SESSION_SECRET", "# SESSION_SECRET=a\n"),  # solo comentada
        ("APP_PASSWORD_HASH", "SESSION_SECRET=a\n"),
        ("APP_PASSWORD_HASH", "APP_PASSWORD_HASH=a\nAPP_PASSWORD_HASH=b\n"),
    ],
)
def test_guia_no_modifica_si_la_linea_falta_o_se_repite(tmp_path, marca, contenido):
    ruta = tmp_path / "finanzas.env"
    ruta.write_text(contenido)
    r = _ejecutar_bloque(marca, ruta, {"HASH": HASH_FALSO} if marca == "APP_PASSWORD_HASH" else None)
    assert r.returncode != 0
    assert ruta.read_text() == contenido


@necesita_bash
def test_guia_cambiar_contrasena(tmp_path):
    ruta = _env_temporal(tmp_path)
    antes = _leer_env(ruta)
    st_antes = ruta.stat()
    nuevo_hash = "scrypt:16384:8:1:" + "12" * 16 + ":" + "34" * 32
    r = _ejecutar_bloque("APP_PASSWORD_HASH", ruta, {"HASH": nuevo_hash})
    assert r.returncode == 0, r.stderr
    despues = _leer_env(ruta)
    assert list(despues) == list(antes)
    assert despues["APP_PASSWORD_HASH"] == nuevo_hash
    for clave in antes:
        if clave != "APP_PASSWORD_HASH":
            assert despues[clave] == antes[clave]
    st = ruta.stat()
    assert stat.S_IMODE(st.st_mode) == 0o600  # ronda 1: antes 0o640
    assert (st.st_uid, st.st_gid) == (st_antes.st_uid, st_antes.st_gid)
    salida = r.stdout + r.stderr
    assert nuevo_hash not in salida
    assert SECRETO_FALSO not in salida


def test_guia_el_hash_generado_es_seguro_como_reemplazo_de_re_sub():
    # 13.5 mete $HASH dentro de una cadena de Python usada como reemplazo de
    # re.subn: solo es seguro si el hash no tiene \, ", ni saltos de línea.
    from finanzas import seguridad

    h = seguridad.generar_hash("contrasena inventada de prueba")
    assert re.fullmatch(r"scrypt:[0-9]+:[0-9]+:[0-9]+:[0-9a-f]+:[0-9a-f]+", h)


# =============================================================================
# Coherencia guía ↔ deploy/
# =============================================================================

# No están en deploy/systemd: caddy.service la instala el paquete de Caddy y
# rpcbind.service viene en la imagen de Oracle (la guía la apaga, paso 5.3).
UNIDADES_DEL_SISTEMA = {"caddy.service", "rpcbind.service"}


def test_unidades_citadas_en_la_guia_existen():
    texto = GUIA.read_text(encoding="utf-8")
    citadas = set(re.findall(r"\b([a-z][a-z0-9-]*\.(?:service|timer))\b", texto))
    assert citadas, "la guía no cita unidades"
    faltan = sorted(u for u in citadas - UNIDADES_DEL_SISTEMA if not (DEPLOY / "systemd" / u).exists())
    assert faltan == []


def test_toda_unidad_de_deploy_aparece_en_la_guia():
    texto = GUIA.read_text(encoding="utf-8")
    for unidad in (DEPLOY / "systemd").iterdir():
        assert unidad.name in texto, unidad.name


def test_unidades_citadas_sin_extension_existen():
    # journalctl -u X / systemctl restart X sin .service
    texto = GUIA.read_text(encoding="utf-8")
    nombres = set(re.findall(r"(?:journalctl -u|systemctl (?:restart|start|stop|status)) ([a-z][a-z0-9-]*)(?=[\s`]|$)",
                             texto, re.M))
    faltan = sorted(n for n in nombres - {"caddy"} if not (DEPLOY / "systemd" / f"{n}.service").exists())
    assert faltan == []


def test_rutas_de_deploy_citadas_en_la_guia_existen():
    texto = GUIA.read_text(encoding="utf-8")
    rutas = set(re.findall(r"(?<![\w.])(?:/opt/finanzas/)?(deploy/[A-Za-z0-9_./*-]+)", texto))
    assert rutas
    faltan = []
    for ruta in rutas:
        ruta = ruta.rstrip(".")
        if "*" in ruta:
            if not list(RAIZ.glob(ruta)):
                faltan.append(ruta)
        elif not (RAIZ / ruta).exists():
            faltan.append(ruta)
    assert faltan == []


def test_rutas_del_repo_en_las_unidades_existen():
    for unidad in (DEPLOY / "systemd").iterdir():
        for ruta in re.findall(r"/opt/finanzas/((?:deploy|finanzas)/[A-Za-z0-9_./-]+)", unidad.read_text()):
            assert (RAIZ / ruta).exists(), f"{unidad.name}: {ruta}"


def test_rutas_de_la_guia_coinciden_con_verificar_y_unidades():
    texto = GUIA.read_text(encoding="utf-8")
    verificar = (DEPLOY / "verificar.sh").read_text()
    respaldo_srv = (DEPLOY / "systemd" / "finanzas-respaldo.service").read_text()
    for ruta in ("/etc/finanzas", "/var/lib/finanzas", "/var/backups/finanzas"):
        assert ruta in texto
        assert ruta in verificar
    assert "/var/lib/finanzas/finanzas.db" in respaldo_srv
    assert "/var/backups/finanzas" in respaldo_srv
    assert "DB_PATH=/var/lib/finanzas/finanzas.db" in texto
