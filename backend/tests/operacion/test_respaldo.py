"""Pruebas de ``deploy/respaldo.py`` (ítem 07). Sin root ni red."""

from __future__ import annotations

import importlib.util
import logging
import os
import sqlite3
import stat
import sys
import threading
from datetime import date, timedelta
from pathlib import Path

import pytest

RUTA_SCRIPT = Path(__file__).resolve().parents[3] / "deploy" / "respaldo.py"
_spec = importlib.util.spec_from_file_location("respaldo", RUTA_SCRIPT)
respaldo = importlib.util.module_from_spec(_spec)
sys.modules["respaldo"] = respaldo
_spec.loader.exec_module(respaldo)

HOY = date(2026, 9, 29)
# Texto inventado que nunca debe aparecer en los registros.
DATO_SENSIBLE = "COMERCIO INVENTADO ZXQ 987654"


def _crear_base(ruta: Path) -> None:
    conn = sqlite3.connect(ruta)
    with conn:
        conn.execute("CREATE TABLE pares (lote INTEGER, lado TEXT, texto TEXT)")
        conn.execute("INSERT INTO pares VALUES (0, 'a', ?), (0, 'b', ?)", (DATO_SENSIBLE, DATO_SENSIBLE))
    conn.close()


@pytest.fixture
def base(tmp_path: Path) -> Path:
    ruta = tmp_path / "datos" / "finanzas.db"
    ruta.parent.mkdir()
    _crear_base(ruta)
    return ruta


@pytest.fixture
def destino(tmp_path: Path) -> Path:
    carpeta = tmp_path / "respaldos"
    carpeta.mkdir(mode=0o700)
    return carpeta


def _argv(base: Path, destino: Path, *extra: str) -> list[str]:
    return ["--origen", str(base), "--destino", str(destino), *extra]


def _tocar(carpeta: Path, nombre: str) -> Path:
    ruta = carpeta / nombre
    ruta.write_bytes(b"x")
    return ruta


# --- Copia ------------------------------------------------------------------


def test_crea_el_respaldo_de_hoy_con_los_datos(base, destino):
    assert respaldo.main(_argv(base, destino), hoy=HOY) == 0
    final = destino / "finanzas-2026-09-29.db"
    conn = sqlite3.connect(final)
    try:
        assert conn.execute("SELECT count(*) FROM pares").fetchone() == (2,)
    finally:
        conn.close()
    # No quedan temporales.
    assert sorted(p.name for p in destino.iterdir()) == ["finanzas-2026-09-29.db"]


def test_permisos_0600_aunque_el_umask_sea_permisivo(base, destino):
    anterior = os.umask(0o022)
    try:
        assert respaldo.main(_argv(base, destino), hoy=HOY) == 0
    finally:
        os.umask(anterior)
    modo = stat.S_IMODE((destino / "finanzas-2026-09-29.db").stat().st_mode)
    assert modo == 0o600


def test_la_copia_pasa_integrity_check(base, destino):
    final = respaldo.crear_respaldo(base, destino, HOY)
    conn = sqlite3.connect(final)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    finally:
        conn.close()


def test_repetir_el_mismo_dia_reemplaza_el_respaldo(base, destino):
    respaldo.crear_respaldo(base, destino, HOY)
    conn = sqlite3.connect(base)
    with conn:
        conn.execute("INSERT INTO pares VALUES (1, 'a', 'x'), (1, 'b', 'x')")
    conn.close()
    final = respaldo.crear_respaldo(base, destino, HOY)
    copia = sqlite3.connect(final)
    try:
        assert copia.execute("SELECT count(*) FROM pares").fetchone() == (4,)
    finally:
        copia.close()


def test_copia_consistente_con_otra_conexion_escribiendo(base, destino):
    """Cada lote inserta dos filas en una transacción: la copia nunca tiene un lote a medias."""
    parar = threading.Event()
    errores: list[BaseException] = []
    lotes_escritos = [0]

    def escribir() -> None:
        conn = sqlite3.connect(base, timeout=30)
        try:
            lote = 1
            while not parar.is_set():
                with conn:
                    conn.execute("INSERT INTO pares VALUES (?, 'a', 'x')", (lote,))
                    conn.execute("INSERT INTO pares VALUES (?, 'b', 'x')", (lote,))
                lotes_escritos[0] = lote
                lote += 1
        except BaseException as error:  # pragma: no cover - se informa abajo
            errores.append(error)
        finally:
            conn.close()

    hilo = threading.Thread(target=escribir)
    hilo.start()
    try:
        copias = []
        for i in range(5):
            dia = HOY - timedelta(days=i)
            copias.append(respaldo.crear_respaldo(base, destino, dia))
    finally:
        parar.set()
        hilo.join()
    assert not errores
    assert lotes_escritos[0] > 0  # de verdad hubo escrituras concurrentes

    for copia in copias:
        conn = sqlite3.connect(copia)
        try:
            assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            total, = conn.execute("SELECT count(*) FROM pares").fetchone()
            assert total % 2 == 0
            incompletos = conn.execute(
                "SELECT lote FROM pares GROUP BY lote HAVING count(*) != 2"
            ).fetchall()
            assert incompletos == []
        finally:
            conn.close()


def test_si_la_comprobacion_falla_no_deja_nada(base, destino, monkeypatch):
    def falla(_ruta):
        raise respaldo.ErrorRespaldo("la copia no pasó PRAGMA integrity_check")

    monkeypatch.setattr(respaldo, "_comprobar_integridad", falla)
    assert respaldo.main(_argv(base, destino), hoy=HOY) == 1
    assert list(destino.iterdir()) == []


def test_una_comprobacion_fallida_no_reemplaza_el_respaldo_bueno(base, destino, monkeypatch):
    bueno = respaldo.crear_respaldo(base, destino, HOY)
    contenido = bueno.read_bytes()
    def falla(_ruta):
        raise respaldo.ErrorRespaldo("la copia no pasó PRAGMA integrity_check")

    monkeypatch.setattr(respaldo, "_comprobar_integridad", falla)
    with pytest.raises(respaldo.ErrorRespaldo):
        respaldo.crear_respaldo(base, destino, HOY)
    assert bueno.read_bytes() == contenido
    assert sorted(p.name for p in destino.iterdir()) == [bueno.name]


def test_integrity_check_detecta_una_base_corrupta(tmp_path):
    ruta = tmp_path / "rota.db"
    _crear_base(ruta)
    datos = bytearray(ruta.read_bytes())
    # Se estropea la segunda página (la tabla) sin tocar la cabecera.
    for i in range(4096 + 8, 4096 + 200):
        datos[i] = 0xFF
    ruta.write_bytes(bytes(datos))
    with pytest.raises((respaldo.ErrorRespaldo, sqlite3.DatabaseError)):
        respaldo._comprobar_integridad(ruta)


# --- Errores de rutas ---------------------------------------------------------


def test_origen_inexistente_falla_y_no_crea_una_base_vacia(tmp_path, destino):
    origen = tmp_path / "no-existe.db"
    assert respaldo.main(_argv(origen, destino), hoy=HOY) != 0
    assert not origen.exists()
    assert list(destino.iterdir()) == []


def test_destino_inexistente_falla_sin_crearlo(base, tmp_path):
    destino = tmp_path / "no-existe"
    assert respaldo.main(_argv(base, destino), hoy=HOY) != 0
    assert not destino.exists()


def test_dias_invalido_es_error_de_argumentos(base, destino):
    assert respaldo.main(_argv(base, destino, "--dias", "0"), hoy=HOY) == 2
    assert respaldo.main(_argv(base, destino, "--dias", "abc"), hoy=HOY) == 2
    assert list(destino.iterdir()) == []


# --- Rotación ---------------------------------------------------------------


def test_rotacion_borra_los_viejos_y_conserva_los_recientes(destino):
    viejo = _tocar(destino, "finanzas-2026-09-14.db")  # 15 días
    muy_viejo = _tocar(destino, "finanzas-2025-01-01.db")
    limite = _tocar(destino, "finanzas-2026-09-15.db")  # 14 días: se conserva
    reciente = _tocar(destino, "finanzas-2026-09-28.db")
    hoy = _tocar(destino, "finanzas-2026-09-29.db")

    borrados = respaldo.rotar(destino, HOY, 14)

    assert sorted(p.name for p in borrados) == ["finanzas-2025-01-01.db", "finanzas-2026-09-14.db"]
    assert not viejo.exists() and not muy_viejo.exists()
    assert limite.exists() and reciente.exists() and hoy.exists()


def test_rotacion_nunca_borra_el_de_hoy(destino):
    hoy = _tocar(destino, "finanzas-2026-09-29.db")
    respaldo.rotar(destino, HOY, 1)
    assert hoy.exists()


def test_rotacion_no_toca_archivos_ajenos_al_patron(destino):
    ajenos = [
        "notas.txt",
        "finanzas.db",
        "finanzas-2020-01-01.db.bak",
        "copia-finanzas-2020-01-01.db",
        "finanzas-2020-1-1.db",
        "finanzas-2020-13-40.db",  # fecha imposible
        "Finanzas-2020-01-01.db",
        ".finanzas-abc.db.tmp",
    ]
    for nombre in ajenos:
        _tocar(destino, nombre)
    (destino / "finanzas-2020-01-02.db").mkdir()  # carpeta con el patrón
    (destino / "finanzas-2020-01-03.db").symlink_to(destino / "notas.txt")

    assert respaldo.rotar(destino, HOY, 14) == []
    for nombre in ajenos:
        assert (destino / nombre).exists()
    assert (destino / "finanzas-2020-01-02.db").is_dir()
    assert (destino / "finanzas-2020-01-03.db").is_symlink()


def test_rotacion_conserva_fechas_futuras(destino):
    futuro = _tocar(destino, "finanzas-2027-01-01.db")
    respaldo.rotar(destino, HOY, 14)
    assert futuro.exists()


def test_dias_configurable_desde_la_linea_de_comandos(base, destino):
    _tocar(destino, "finanzas-2026-09-26.db")  # 3 días
    _tocar(destino, "finanzas-2026-09-27.db")  # 2 días
    assert respaldo.main(_argv(base, destino, "--dias", "2"), hoy=HOY) == 0
    assert sorted(p.name for p in destino.iterdir()) == [
        "finanzas-2026-09-27.db",
        "finanzas-2026-09-29.db",
    ]


def test_main_rota_con_14_dias_por_defecto(base, destino):
    _tocar(destino, "finanzas-2026-09-14.db")
    _tocar(destino, "finanzas-2026-09-15.db")
    assert respaldo.main(_argv(base, destino), hoy=HOY) == 0
    nombres = sorted(p.name for p in destino.iterdir())
    assert nombres == ["finanzas-2026-09-15.db", "finanzas-2026-09-29.db"]


# --- Registros ----------------------------------------------------------------


def test_los_registros_no_llevan_datos_de_la_base(base, destino, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    assert respaldo.main(_argv(base, destino), hoy=HOY) == 0
    salida = capsys.readouterr()
    todo = caplog.text + salida.out + salida.err
    assert "Respaldo creado" in todo
    assert DATO_SENSIBLE not in todo
    assert "ZXQ" not in todo


def test_los_errores_de_sqlite_solo_muestran_el_tipo(base, destino, caplog, monkeypatch):
    def falla(_origen):
        raise sqlite3.OperationalError(f"error con {DATO_SENSIBLE}")

    monkeypatch.setattr(respaldo, "_abrir_origen", falla)
    caplog.set_level(logging.DEBUG)
    assert respaldo.main(_argv(base, destino), hoy=HOY) == 1
    assert "OperationalError" in caplog.text
    assert DATO_SENSIBLE not in caplog.text
    assert list(destino.iterdir()) == []


def test_rotacion_no_acepta_digitos_unicode(destino):
    """``\\d`` aceptaría dígitos de ancho completo; el patrón solo admite 0-9."""
    ajenos = ["finanzas-２０２０-01-01.db", "finanzas-2020-٠١-01.db", "finanzas-2020-01-０１.db"]
    for nombre in ajenos:
        _tocar(destino, nombre)
        assert respaldo.fecha_de_respaldo(nombre) is None
    assert respaldo.rotar(destino, HOY, 14) == []
    for nombre in ajenos:
        assert (destino / nombre).exists()
