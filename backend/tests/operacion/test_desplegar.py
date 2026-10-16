"""Pruebas de ``deploy/desplegar.sh`` con una VM simulada.

El repositorio es real (git en una carpeta temporal, con ``origin`` local).
``systemctl``, ``journalctl``, ``curl``, ``npm``, ``pip`` y ``sqlite3`` son
falsos pero llevan estado: la app está arrancada o parada, la base tiene una
revisión y la migración la sube a la última del código. Así se comprueban el
orden de los pasos, el candado, el freno por la revisión real de la base y
las dos vueltas atrás (completa e incompleta), sin root, red ni systemd.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[3] / "deploy"
SCRIPT = DEPLOY / "desplegar.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None or shutil.which("flock") is None,
    reason="necesita bash, git y flock",
)

FALSOS = {
    # Estado: $MOCK_DIR/app_activa existe si finanzas.service está arrancada.
    "systemctl": r"""#!/bin/bash
M="$MOCK_DIR"
printf '%s\n' "$*" >> "$M/systemctl.log"
case "$1" in
  start)
    if [[ "$2" == "finanzas-migrar.service" ]]; then
      rm -f "$M/app_activa"   # Conflicts=finanzas.service
      [[ -f "$M/migrar_falla" ]] && exit 1
      if [[ -f "$M/migrar_desacoplada" ]]; then
        # Como en systemd: la migración sigue aunque maten a este cliente.
        touch "$M/migrar_activa"
        setsid bash -c 'sleep 2
          ls "$APP_DIR"/backend/finanzas/migraciones/versions/ | grep -oE "^[0-9]{4}" | sort | tail -n 1 > "$MOCK_DIR/revision"
          rm -f "$MOCK_DIR/migrar_activa"' </dev/null >/dev/null 2>&1 &
        sleep 30
        exit 0
      fi
      ls "$APP_DIR"/backend/finanzas/migraciones/versions/ "$APP_DIR"/finanzas/migraciones/versions/ 2>/dev/null \
        | grep -oE '^[0-9]{4}' | sort | tail -n 1 > "$M/revision"
      exit 0
    fi
    [[ "$2" == "finanzas-respaldo.service" && -f "$M/respaldo_falla" ]] && exit 1
    [[ " $* " == *" finanzas.service "* ]] && touch "$M/app_activa"
    exit 0 ;;
  stop)
    [[ " $* " == *" finanzas.service "* ]] && rm -f "$M/app_activa"
    exit 0 ;;
  reload)
    [[ -f "$M/caddy_falla" && "$(git -C "$APP_DIR" rev-parse HEAD)" == "$(cat "$M/caddy_falla")" ]] && exit 1
    exit 0 ;;
  is-active) [[ -f "$M/app_activa" ]] && exit 0; exit 3 ;;
  is-enabled) [[ -f "$M/sync_apagada" ]] && exit 1; exit 0 ;;
  show) [[ -f "$M/migrar_activa" ]] && echo activating || echo inactive; exit 0 ;;
esac
exit 0
""",
    "journalctl": "#!/bin/bash\nexit 0\n",
    # Responde como la app solo si está arrancada y su commit no está "roto".
    "curl": r"""#!/bin/bash
M="$MOCK_DIR"
printf '%s\n' "$*" >> "$M/curl.log"
url="${@: -1}"
if [[ ! -f "$M/app_activa" ]]; then printf '000'; exit 7; fi
if [[ -f "$M/salud_mala" && "$(git -C "$APP_DIR" rev-parse HEAD)" == "$(cat "$M/salud_mala")" ]]; then printf '503'; exit 0; fi
case "$url" in
  */app/) printf '200' ;;
  */api/sesion) printf '401' ;;
  *) printf '000' ;;
esac
""",
    "npm": r"""#!/bin/bash
M="$MOCK_DIR"
printf 'npm %s (%s)\n' "$*" "$(git rev-parse --short HEAD)" >> "$M/pasos.log"
[[ "$1" == "ci" && -f "$M/npm_lento" ]] && sleep 3
if [[ "$1" == "run" && -f "$M/npm_falla" && "$(git rev-parse HEAD)" == "$(cat "$M/npm_falla")" ]]; then exit 1; fi
exit 0
""",
    # sqlite3 "file:...?mode=ro" "SELECT version_num FROM alembic_version"
    "sqlite3": r"""#!/bin/bash
[[ -f "$MOCK_DIR/sqlite_falla" ]] && exit 1
[[ -f "$MOCK_DIR/base_v1" ]] && { echo "Error: no such table: alembic_version" >&2; exit 1; }
[[ -f "$MOCK_DIR/revision" ]] || exit 1
cat "$MOCK_DIR/revision"
""",
}

PIP = r"""#!/bin/bash
printf 'pip %s\n' "$*" >> "$MOCK_DIR/pasos.log"
exit 0
"""

MIGRACION_12 = {"backend/finanzas/migraciones/versions/0012_descartes.py": "# 0012\n"}
CADDY_NUEVO = {"deploy/caddy/Caddyfile": "{$DOMINIO} {\n\tencode gzip\n}\n"}
ARRANQUE = "start finanzas.service finanzas-sync.timer finanzas-respaldo.timer"


def _ejecutable(ruta: Path, texto: str) -> None:
    ruta.write_text(texto, encoding="utf-8")
    ruta.chmod(0o755)


def _git(carpeta: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(carpeta), *args], check=True, capture_output=True, text=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "Prueba", "GIT_AUTHOR_EMAIL": "prueba@example.com",
             "GIT_COMMITTER_NAME": "Prueba", "GIT_COMMITTER_EMAIL": "prueba@example.com"},
    ).stdout.strip()


class VM:
    """``origin`` con commits y una VM con el código en el primero, la app
    arrancada y la base en la 0011."""

    def __init__(self, raiz: Path):
        self.raiz = raiz
        self.mock = raiz / "mock"
        self.bin = raiz / "bin"
        self.origen = raiz / "origen"
        self.app = raiz / "opt-finanzas"
        self.systemd = raiz / "systemd"
        self.estado = raiz / "estado"
        for carpeta in (self.mock, self.bin, self.origen, self.systemd):
            carpeta.mkdir()
        for nombre, texto in FALSOS.items():
            _ejecutable(self.bin / nombre, texto)
        self.override = raiz / "override.conf"
        self.override.write_text("[Service]\nEnvironment=DOMINIO=tu-subdominio.duckdns.org\n")
        self.caddyfile = raiz / "Caddyfile"
        self.db = raiz / "finanzas.db"
        self.db.write_bytes(b"base inventada")
        (self.mock / "revision").write_text("0011\n")
        (self.mock / "app_activa").touch()

        _git(self.origen, "init", "-q", "-b", "main")
        self._archivos({
            "backend/requirements.txt": "fastapi\n",
            "frontend/package.json": "{}\n",
            "deploy/caddy/Caddyfile": "{$DOMINIO} {\n}\n",
            "deploy/systemd/finanzas.service": "[Unit]\n",
            "deploy/systemd/finanzas-sync.timer": "[Unit]\n",
            "deploy/verificar.sh": "#!/bin/bash\necho 'verificar simulado'\n",
            "backend/finanzas/migraciones/versions/0011_arranque.py": "# 0011\n",
        })
        self.a = self._commit("A")
        self.caddyfile.write_text((self.origen / "deploy/caddy/Caddyfile").read_text())

        _git(self.raiz, "clone", "-q", str(self.origen), str(self.app))
        (self.app / ".venv/bin").mkdir(parents=True)
        _ejecutable(self.app / ".venv/bin/pip", PIP)

    def _archivos(self, archivos: dict[str, str]) -> None:
        for relativo, texto in archivos.items():
            ruta = self.origen / relativo
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(texto)

    def _commit(self, mensaje: str) -> str:
        _git(self.origen, "add", "-A")
        _git(self.origen, "commit", "-q", "-m", mensaje)
        return _git(self.origen, "rev-parse", "HEAD")

    def commit(self, mensaje: str, archivos: dict[str, str]) -> str:
        self._archivos(archivos)
        return self._commit(mensaje)

    def head(self) -> str:
        return _git(self.app, "rev-parse", "HEAD")

    def revision(self) -> str:
        ruta = self.mock / "revision"
        return ruta.read_text().strip() if ruta.exists() else ""

    def app_activa(self) -> bool:
        return (self.mock / "app_activa").exists()

    def systemctl(self) -> list[str]:
        log = self.mock / "systemctl.log"
        return log.read_text().splitlines() if log.exists() else []

    def historial(self) -> str:
        ruta = self.estado / "historial.log"
        return ruta.read_text() if ruta.exists() else ""

    def entorno(self, candado: Path | None = None) -> dict[str, str]:
        return {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}",
            "MOCK_DIR": str(self.mock),
            "APP_DIR": str(self.app),
            "DB": str(self.db),
            "NODE_BIN": str(self.bin),
            "ESTADO_DIR": str(self.estado),
            "CANDADO": str(candado or self.raiz / "candado.lock"),
            "CADDY_OVERRIDE": str(self.override),
            "CADDYFILE_SISTEMA": str(self.caddyfile),
            "SYSTEMD_DIR": str(self.systemd),
            "ESPERA_SALUD": "2",
            "PAUSA_SALUD": "1",
            "DESPLEGAR_PRUEBA": "1",
            "TMPDIR": str(self.raiz),
            "LANG": "C.UTF-8",
        }

    def desplegar(self, *args: str, candado: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(SCRIPT), *args], env=self.entorno(candado),
                              capture_output=True, text=True, timeout=120)


@pytest.fixture
def vm(tmp_path):
    return VM(tmp_path)


def _salida(r) -> str:
    return r.stdout + r.stderr


def _arranques(vm: VM) -> list[str]:
    return [l for l in vm.systemctl() if l.startswith(("start finanzas.service", "stop "))]


# --- Camino feliz --------------------------------------------------------------


def test_despliega_el_commit_exacto_en_orden(vm):
    b = vm.commit("B", {"frontend/app.ts": "nuevo\n"})
    r = vm.desplegar(b)
    assert r.returncode == 0, _salida(r)
    assert vm.head() == b and vm.app_activa()
    llamadas = vm.systemctl()
    orden = [
        "start finanzas-respaldo.service",
        "stop finanzas-sync.timer finanzas-respaldo.timer finanzas-sync.service finanzas.service",
        "daemon-reload",
        "start finanzas-migrar.service",
        ARRANQUE,
    ]
    posiciones = [llamadas.index(paso) for paso in orden]
    assert posiciones == sorted(posiciones), llamadas
    pasos = (vm.mock / "pasos.log").read_text()
    assert "-e " in pasos and "backend/requirements.txt" in pasos
    assert "npm ci --ignore-scripts" in pasos and "npm run build" in pasos
    assert (vm.systemd / "finanzas.service").is_file()
    assert vm.historial().rstrip().endswith(f"-> {b} OK")
    assert "verificar simulado" in r.stdout


def test_la_salud_se_mide_en_esta_vm_y_no_por_dns(vm):
    b = vm.commit("B", {"frontend/x": "1\n"})
    assert vm.desplegar(b).returncode == 0
    assert "--resolve tu-subdominio.duckdns.org:443:127.0.0.1" in (vm.mock / "curl.log").read_text()


def test_no_deja_copias_temporales_del_script(vm):
    b = vm.commit("B", {"frontend/x": "1\n"})
    assert vm.desplegar(b).returncode == 0
    assert not list(vm.raiz.glob("desplegar.*"))


def test_el_caddyfile_cambiado_se_copia_y_recarga(vm):
    b = vm.commit("B", CADDY_NUEVO)
    assert vm.desplegar(b).returncode == 0
    assert "encode gzip" in vm.caddyfile.read_text()
    assert "reload caddy" in vm.systemctl()


# --- Entradas inválidas y "no se hizo nada" -------------------------------------


@pytest.mark.parametrize("sha", ["", "abc123", "A" * 40, "g" * 40])
def test_rechaza_un_sha_invalido(vm, sha):
    r = vm.desplegar(sha) if sha else vm.desplegar()
    assert r.returncode == 2
    assert vm.systemctl() == []


def test_rechaza_opciones_desconocidas(vm):
    b = vm.commit("B", {"frontend/x": "1\n"})
    assert vm.desplegar(b, "--forzar").returncode == 2


def test_solo_despliega_commits_de_main(vm):
    _git(vm.origen, "checkout", "-q", "-b", "otra")
    otro = vm.commit("fuera de main", {"frontend/x": "1\n"})
    _git(vm.origen, "checkout", "-q", "main")
    r = vm.desplegar(otro)
    assert r.returncode == 2
    assert "origin/main" in r.stderr
    assert vm.head() == vm.a and vm.systemctl() == []


def test_sin_dominio_en_caddy_no_hace_nada(vm):
    vm.override.write_text("[Service]\n")
    b = vm.commit("B", {"frontend/x": "1\n"})
    assert vm.desplegar(b).returncode == 2
    assert vm.systemctl() == []


def test_dos_despliegues_a_la_vez_no(vm, tmp_path):
    b = vm.commit("B", {"frontend/x": "1\n"})
    candado = tmp_path / "ocupado.lock"
    ocupado = subprocess.Popen(["flock", str(candado), "sleep", "30"])
    try:
        for _ in range(100):  # esperar a que el candado esté tomado
            if subprocess.run(["flock", "-n", str(candado), "true"]).returncode != 0:
                break
            time.sleep(0.1)
        r = vm.desplegar(b, candado=candado)
    finally:
        ocupado.kill()
    assert r.returncode == 6
    assert "otro despliegue" in r.stderr
    assert vm.head() == vm.a and vm.systemctl() == []


def test_si_el_respaldo_falla_no_toca_nada(vm):
    b = vm.commit("B", {"frontend/x": "1\n"})
    (vm.mock / "respaldo_falla").touch()
    r = vm.desplegar(b)
    assert r.returncode == 6, _salida(r)
    assert vm.head() == vm.a and vm.app_activa()
    assert _arranques(vm) == []


# --- Freno por la revisión real de la base -------------------------------------


def test_migraciones_nuevas_exigen_permiso_y_no_tocan_nada(vm):
    b = vm.commit("B", MIGRACION_12)
    r = vm.desplegar(b)
    assert r.returncode == 3, _salida(r)
    assert "0011 -> 0012" in r.stderr
    assert vm.head() == vm.a and vm.systemctl() == []


def test_con_permiso_aplica_las_migraciones(vm):
    b = vm.commit("B", MIGRACION_12)
    r = vm.desplegar(b, "--permitir-migraciones")
    assert r.returncode == 0, _salida(r)
    assert vm.head() == b and vm.revision() == "0012" and vm.app_activa()


def test_base_atrasada_respecto_del_codigo_anterior_tambien_frena(vm):
    # Tras un --bajar-a o una caída a medias: el código ya tiene la 0011 pero
    # la base sigue en la 0010. Comparar archivos entre commits no lo vería.
    (vm.mock / "revision").write_text("0010\n")
    b = vm.commit("B", {"frontend/x": "1\n"})
    r = vm.desplegar(b)
    assert r.returncode == 3, _salida(r)
    assert vm.head() == vm.a and vm.systemctl() == []


def test_sin_base_tambien_pide_permiso(vm):
    (vm.mock / "revision").unlink()
    vm.db.unlink()
    b = vm.commit("B", {"frontend/x": "1\n"})
    assert vm.desplegar(b).returncode == 3


def test_un_commit_mas_viejo_que_la_base_no_se_despliega(vm):
    (vm.mock / "revision").write_text("0013\n")
    b = vm.commit("B", {"frontend/x": "1\n"})
    r = vm.desplegar(b, "--permitir-migraciones")
    assert r.returncode == 6, _salida(r)
    assert "caso 2" in r.stderr
    assert vm.head() == vm.a and vm.systemctl() == []


def test_si_no_se_puede_leer_la_revision_no_toca_nada(vm):
    (vm.mock / "sqlite_falla").touch()
    b = vm.commit("B", {"frontend/x": "1\n"})
    r = vm.desplegar(b, "--permitir-migraciones")
    assert r.returncode == 6, _salida(r)
    assert "revisión de la base" in r.stderr
    assert vm.head() == vm.a and vm.systemctl() == []


def test_base_de_la_v1_remite_a_la_via_manual(vm):
    (vm.mock / "base_v1").touch()
    b = vm.commit("B", {"frontend/x": "1\n"})
    r = vm.desplegar(b, "--permitir-migraciones")
    assert r.returncode == 6, _salida(r)
    assert "v1" in r.stderr and "a mano" in r.stderr
    assert vm.systemctl() == []


def test_sin_base_y_commit_sin_migraciones_pide_permiso_sin_error_de_arbol(vm):
    (vm.mock / "revision").unlink()
    vm.db.unlink()
    _git(vm.origen, "rm", "-q", "backend/finanzas/migraciones/versions/0011_arranque.py")
    viejo = vm._commit("sin migraciones")
    r = vm.desplegar(viejo)
    assert "árbol" not in r.stderr, _salida(r)
    assert r.returncode == 0, _salida(r)  # sin base ni migraciones: nada que migrar


def test_en_una_vm_de_pruebas_no_enciende_la_sincronizacion(vm):
    (vm.mock / "sync_apagada").touch()
    b = vm.commit("B", {"frontend/x": "1\n"})
    assert vm.desplegar(b).returncode == 0
    assert not any("finanzas-sync.timer" in l for l in vm.systemctl() if l.startswith("start "))


def test_commit_sin_migraciones_con_base_versionada_no_se_despliega(vm):
    # Un commit anterior a las migraciones no entiende una base con Alembic.
    _git(vm.origen, "rm", "-q", "backend/finanzas/migraciones/versions/0011_arranque.py")
    viejo = vm._commit("sin migraciones")
    r = vm.desplegar(viejo, "--permitir-migraciones")
    assert r.returncode == 6, _salida(r)
    assert vm.head() == vm.a and vm.systemctl() == []


def test_mover_las_migraciones_a_backend_no_cuenta_como_nuevas(vm):
    # La reorganización movió finanzas/ a backend/finanzas/: misma revisión.
    _git(vm.origen, "mv", "backend/finanzas", "finanzas")
    raiz = vm._commit("antes de backend/")
    _git(vm.app, "fetch", "-q", "origin")
    _git(vm.app, "checkout", "-q", raiz)
    _git(vm.origen, "mv", "finanzas", "backend/finanzas")
    movido = vm._commit("a backend/")
    r = vm.desplegar(movido)
    assert r.returncode == 0, _salida(r)


# --- Vueltas atrás ---------------------------------------------------------------


def test_si_la_compilacion_falla_vuelve_al_commit_anterior(vm):
    b = vm.commit("B", {"frontend/x": "1\n"})
    (vm.mock / "npm_falla").write_text(b)
    r = vm.desplegar(b)
    assert r.returncode == 1, _salida(r)
    assert vm.head() == vm.a and vm.app_activa()
    assert "start finanzas-migrar.service" not in vm.systemctl()
    assert "FALLO-VUELTO-ATRAS" in vm.historial()


def test_si_la_migracion_falla_vuelve_atras_porque_la_base_no_cambio(vm):
    b = vm.commit("B", MIGRACION_12)
    (vm.mock / "migrar_falla").touch()
    r = vm.desplegar(b, "--permitir-migraciones")
    assert r.returncode == 1, _salida(r)
    assert vm.head() == vm.a and vm.revision() == "0011" and vm.app_activa()


def test_sin_migraciones_si_la_app_no_responde_vuelve_atras(vm):
    b = vm.commit("B", {"frontend/x": "1\n"})
    (vm.mock / "salud_mala").write_text(b)
    r = vm.desplegar(b)
    assert r.returncode == 1, _salida(r)
    assert vm.head() == vm.a and vm.app_activa()


def test_con_la_base_migrada_no_vuelve_atras_solo(vm):
    b = vm.commit("B", MIGRACION_12)
    (vm.mock / "salud_mala").write_text(b)
    r = vm.desplegar(b, "--permitir-migraciones")
    assert r.returncode == 4, _salida(r)
    assert vm.head() == b and vm.revision() == "0012"
    assert "caso 2" in r.stderr
    assert "FALLO-CON-MIGRACIONES" in vm.historial()
    assert _arranques(vm)[-1] == ARRANQUE


def test_vuelta_atras_incompleta_igual_arranca_y_lo_dice(vm):
    # B cambia el Caddyfile y no compila; al volver a A, recargar Caddy falla.
    b = vm.commit("B", CADDY_NUEVO)
    (vm.mock / "npm_falla").write_text(b)
    (vm.mock / "caddy_falla").write_text(vm.a)
    r = vm.desplegar(b)
    assert r.returncode == 5, _salida(r)
    assert _arranques(vm)[-1] == ARRANQUE  # siempre intenta arrancar
    assert "FALLO-VUELTA-ATRAS-INCOMPLETA" in vm.historial()


def test_vuelve_atras_a_codigo_anterior_a_backend(vm):
    # El commit anterior tiene requirements.txt en la raíz (antes de backend/).
    _git(vm.origen, "mv", "backend/requirements.txt", "requirements.txt")
    raiz = vm._commit("antes de backend/")
    _git(vm.app, "fetch", "-q", "origin")
    _git(vm.app, "checkout", "-q", raiz)
    _git(vm.origen, "mv", "requirements.txt", "backend/requirements.txt")
    nuevo = vm._commit("a backend/")
    (vm.mock / "npm_falla").write_text(nuevo)
    r = vm.desplegar(nuevo)
    assert r.returncode == 1, _salida(r)
    assert vm.head() == raiz
    pasos = (vm.mock / "pasos.log").read_text()
    assert "uninstall" in pasos and f"-r {vm.app}/requirements.txt" in pasos


def test_un_corte_a_mitad_vuelve_atras(vm):
    b = vm.commit("B", {"frontend/x": "1\n"})
    (vm.mock / "npm_lento").touch()
    proceso = subprocess.Popen(["bash", str(SCRIPT), b], env=vm.entorno(),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    pasos = vm.mock / "pasos.log"
    for _ in range(200):
        if pasos.exists() and "npm ci" in pasos.read_text():
            break
        time.sleep(0.1)
    proceso.send_signal(signal.SIGHUP)
    salida, error = proceso.communicate(timeout=60)
    assert proceso.returncode == 1, salida + error
    assert "interrumpido" in salida
    assert vm.head() == vm.a and vm.app_activa()


def test_un_corte_durante_la_migracion_espera_y_no_mezcla_codigo_y_base(vm):
    # El corte mata al cliente systemctl, pero la migración termina dentro de
    # systemd: volver al código anterior lo dejaría sobre la base nueva.
    b = vm.commit("B", MIGRACION_12)
    (vm.mock / "migrar_desacoplada").touch()
    proceso = subprocess.Popen(["bash", str(SCRIPT), b, "--permitir-migraciones"], env=vm.entorno(),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               start_new_session=True)
    for _ in range(200):
        if (vm.mock / "migrar_activa").exists():
            break
        time.sleep(0.1)
    os.killpg(proceso.pid, signal.SIGHUP)
    salida, error = proceso.communicate(timeout=60)
    assert proceso.returncode == 4, salida + error
    assert vm.revision() == "0012"
    assert vm.head() == b  # el código que entiende la base
    assert "FALLO-CON-MIGRACIONES" in vm.historial()


# --- Repetir un despliegue ---------------------------------------------------------


def test_repetir_un_despliegue_correcto_no_hace_nada(vm):
    b = vm.commit("B", {"frontend/x": "1\n"})
    assert vm.desplegar(b).returncode == 0
    antes = len(vm.systemctl())
    r = vm.desplegar(b)
    assert r.returncode == 0, _salida(r)
    assert not any(l.startswith(("stop", "start finanzas-migrar")) for l in vm.systemctl()[antes:])


def test_repetir_tras_un_4_no_da_por_bueno_lo_roto(vm):
    b = vm.commit("B", MIGRACION_12)
    (vm.mock / "salud_mala").write_text(b)
    assert vm.desplegar(b, "--permitir-migraciones").returncode == 4
    r = vm.desplegar(b)
    assert r.returncode == 5, _salida(r)


def test_repetir_tras_un_4_ya_arreglado_lo_confirma(vm):
    b = vm.commit("B", MIGRACION_12)
    (vm.mock / "salud_mala").write_text(b)
    assert vm.desplegar(b, "--permitir-migraciones").returncode == 4
    (vm.mock / "salud_mala").unlink()
    (vm.mock / "app_activa").unlink()
    r = vm.desplegar(b)
    assert r.returncode == 0, _salida(r)
    assert vm.app_activa()
    assert vm.historial().rstrip().endswith(f"-> {b} OK")


# --- preparar-servidor.sh ----------------------------------------------------------


def test_preparar_servidor_tiene_sintaxis_valida_y_reglas_clave():
    texto = (DEPLOY / "preparar-servidor.sh").read_text(encoding="utf-8")
    r = subprocess.run(["bash", "-n", str(DEPLOY / "preparar-servidor.sh")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # DuckDNS solo con la bandera, y nunca se apaga solo.
    assert "PRODUCCION=0" in texto
    assert "disable --now duckdns" not in texto
    # No migra ni arranca sobre una base ajena: eso es de desplegar.sh.
    assert "start finanzas-migrar" not in texto
    # La huella de GitHub es la misma que publica la guía.
    guia = (DEPLOY / "GUIA.md").read_text(encoding="utf-8")
    huella = "SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU"
    assert huella in texto and huella in guia
    assert "StrictHostKeyChecking=yes" in texto
    # Node: misma versión y huellas que la guía (6.1).
    for linea in texto.splitlines():
        if linea.endswith(".tar.xz") and "  node-v" in linea:
            assert linea.strip() in guia, linea
