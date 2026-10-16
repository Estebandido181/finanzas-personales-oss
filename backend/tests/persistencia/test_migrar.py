"""Comando ``python -m finanzas.migrar`` (ítem 22): respaldo previo, salida y códigos.

Datos inventados. Los montos y textos de ``crear_base_v1`` sirven de
centinela: nunca deben aparecer en lo que imprime el comando.
"""

from __future__ import annotations

import os
import sqlite3
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from finanzas import migrar
from tests.soporte.migraciones import crear_base_v1, huella, revision, volcado

RAIZ = Path(__file__).resolve().parents[3]
CENTINELAS = ("6863000", "68630", "123456789", "COMERCIO INVENTADO", "PERSONA INVENTADA",
              "Asunto inventado", "id-inventado")


@pytest.fixture
def base_v1(tmp_path) -> Path:
    ruta = tmp_path / "produccion-inventada.db"
    crear_base_v1(ruta)
    return ruta


@pytest.fixture
def respaldos(tmp_path) -> Path:
    carpeta = tmp_path / "respaldos"
    carpeta.mkdir()
    return carpeta


def _correr(capsys, *argv) -> tuple[int, str]:
    codigo = migrar.main(list(argv))
    salida = capsys.readouterr()
    return codigo, salida.out + salida.err


def _previos(carpeta: Path) -> list[Path]:
    return sorted(carpeta.glob("finanzas-antes-de-migrar-*.db"))


def _sin_datos(texto: str) -> None:
    for centinela in CENTINELAS:
        assert centinela not in texto, centinela


def test_migrar_la_base_v1_hace_respaldo_previo_y_la_marca(capsys, base_v1, respaldos):
    antes = volcado(base_v1)
    codigo, salida = _correr(capsys, "--base", str(base_v1), "--respaldos", str(respaldos))

    assert codigo == 0, salida
    assert "se marca como 0001" in salida
    assert revision(base_v1) == migrar.revision_final()
    assert volcado(base_v1) == antes
    [previo] = _previos(respaldos)
    assert previo.name.startswith("finanzas-antes-de-migrar-v1-")
    assert previo.name in salida
    # El respaldo es una copia íntegra de la base **antes** de migrar (sin versión).
    assert stat.S_IMODE(previo.stat().st_mode) == 0o600
    assert volcado(previo) == antes
    assert revision(previo) is None
    conn = sqlite3.connect(previo)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        conn.close()
    _sin_datos(salida)


def test_la_segunda_vez_no_hace_nada_ni_respalda(capsys, base_v1, respaldos):
    _correr(capsys, "--base", str(base_v1), "--respaldos", str(respaldos))
    huella_antes = huella(base_v1)

    codigo, salida = _correr(capsys, "--base", str(base_v1), "--respaldos", str(respaldos))

    assert codigo == 0
    assert "ya está al día" in salida and "No se cambió nada" in salida
    assert huella(base_v1) == huella_antes
    assert len(_previos(respaldos)) == 1


def test_base_nueva_se_crea_sin_respaldo_y_con_permisos_600(capsys, tmp_path, respaldos):
    ruta = tmp_path / "nueva.db"
    codigo, salida = _correr(capsys, "--base", str(ruta), "--respaldos", str(respaldos))
    assert codigo == 0, salida
    assert "Base nueva" in salida
    assert revision(ruta) == migrar.revision_final()
    assert stat.S_IMODE(ruta.stat().st_mode) == 0o600
    assert _previos(respaldos) == []


def test_si_el_respaldo_falla_no_migra(capsys, base_v1, tmp_path):
    huella_antes = huella(base_v1)
    codigo, salida = _correr(capsys, "--base", str(base_v1), "--respaldos", str(tmp_path / "no-existe"))
    assert codigo == 1
    assert "respaldo previo falló" in salida
    assert huella(base_v1) == huella_antes
    assert revision(base_v1) is None


def test_estructura_distinta_se_detiene_sin_respaldo_ni_cambios(capsys, base_v1, respaldos):
    conn = sqlite3.connect(base_v1)
    with conn:
        conn.execute("ALTER TABLE reglas ADD COLUMN extra TEXT")
    conn.close()
    huella_antes = huella(base_v1)

    codigo, salida = _correr(capsys, "--base", str(base_v1), "--respaldos", str(respaldos))

    assert codigo == 1
    assert "no es la de la v1" in salida and "tabla reglas" in salida
    assert huella(base_v1) == huella_antes
    assert _previos(respaldos) == []
    _sin_datos(salida)


def test_comprobar_no_escribe_ni_crea_la_base(capsys, base_v1, tmp_path, respaldos):
    ruta = tmp_path / "no-existe.db"
    assert _correr(capsys, "--base", str(ruta), "--comprobar")[0] == 1
    assert not ruta.exists()

    huella_antes = huella(base_v1)
    codigo, salida = _correr(capsys, "--base", str(base_v1), "--comprobar")
    assert codigo == 1 and "v1" in salida
    assert huella(base_v1) == huella_antes

    _correr(capsys, "--base", str(base_v1), "--respaldos", str(respaldos))
    codigo, salida = _correr(capsys, "--base", str(base_v1), "--comprobar")
    assert codigo == 0 and "al día" in salida


def test_bajar_a_base_no_se_permite(capsys, base_v1, respaldos):
    _correr(capsys, "--base", str(base_v1), "--respaldos", str(respaldos))
    huella_antes = huella(base_v1)
    for destino in ("base", "0000", "no-existe"):
        codigo, salida = _correr(capsys, "--base", str(base_v1), "--respaldos", str(respaldos), "--bajar-a", destino)
        assert codigo == 1
        assert "restaura el respaldo" in salida
    assert huella(base_v1) == huella_antes


def test_bajar_a_la_revision_actual_no_hace_nada(capsys, base_v1, respaldos):
    _correr(capsys, "--base", str(base_v1), "--respaldos", str(respaldos))
    codigo, salida = _correr(
        capsys, "--base", str(base_v1), "--respaldos", str(respaldos), "--bajar-a", migrar.revision_final()
    )
    assert codigo == 0 and "No se cambió nada" in salida
    assert len(_previos(respaldos)) == 1


def test_argumentos_invalidos(capsys):
    assert _correr(capsys, "--comprobar", "--bajar-a", "0001")[0] == 2
    assert _correr(capsys, "--opcion-inventada")[0] == 2


def test_nombre_del_respaldo_previo_no_lo_toca_la_rotacion():
    nombre = migrar.nombre_respaldo_previo(None, datetime(2026, 9, 30, 10, 15, 0))
    assert nombre == "finanzas-antes-de-migrar-v1-20260930T101500.db"
    assert migrar._modulo_respaldo().fecha_de_respaldo(nombre) is None  # no sigue el patrón diario
    assert migrar.nombre_respaldo_previo("0001", datetime(2026, 9, 30)).startswith("finanzas-antes-de-migrar-0001-")


def test_como_modulo_usa_db_path(tmp_path, respaldos):
    ruta = tmp_path / "desde-entorno.db"
    entorno = {**os.environ, "DB_PATH": str(ruta)}
    r = subprocess.run(
        [sys.executable, "-m", "finanzas.migrar", "--respaldos", str(respaldos)],
        cwd=RAIZ, env=entorno, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert revision(ruta) == migrar.revision_final()
