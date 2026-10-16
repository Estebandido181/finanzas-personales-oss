"""Conciliación en seco (``python -m finanzas.conciliacion_en_seco``, ítem 29, D44).

Corre el motor con un Excel y la base sin guardar nada y muestra solo
conteos. Datos inventados; el Excel se genera en memoria
(``tests/soporte/excel_inventado.py``) y solo se escribe en la carpeta temporal de la
prueba, como lo haría el dueño en la VM.
"""

from __future__ import annotations

import hashlib
import io
from datetime import date
from pathlib import Path

import pytest

from finanzas.modulos.importaciones.reportes_aplicacion import OperarReportes
from finanzas import conciliacion_en_seco, db, migrar
from tests.soporte import excel_inventado
from tests.soporte.ayudas_db import sql
from tests.soporte.migracion_0005 import _subir_hasta

FILAS = [
    (date(2026, 8, 5), "COMPRA EN  TIENDA EJEMPLO", None, -25900),       # ya llegó por correo
    (date(2026, 8, 6), "COBRO VIAJE TRANSPORTE MASIVO", None, -10650),   # falta
    (date(2026, 8, 7), "COBRO VIAJE TRANSPORTE MASIVO", None, -7100),    # falta
    (date(2026, 8, 18), "COMPRA EN  WOMPI EJEMPLO", None, -9800),        # parecido sin apoyo: pregunta
    (date(2026, 8, 22), "TRANSFERENCIA CTA SUC VIRTUAL", "00000000002", 160000),  # confirma el manual
    (date(2026, 8, 25), "TRANSFERENCIAS A NEQUI", "PSE0000001", -6200),  # Referencia sin formato
    (date(2026, 7, 30), "COMPRA EN  TIENDA EJEMPLO", None, -1000),       # anterior a la fecha de inicio
]
# Lo que nunca debe salir en pantalla: montos, nombres, referencias, fechas.
PRIVADO = ["25900", "2590000", "10650", "9800", "160000", "16000000", "6200", "TIENDA", "WOMPI",
           "SUPERMERCADO", "NEQUI", "0000000002", "*0002", "PSE0000001", "2026-08", "08/2026", "$"]


@pytest.fixture
def ruta_db(tmp_path):
    return str(tmp_path / "seco.db")


@pytest.fixture
def base(ruta_db):
    conn = db.conectar(ruta_db)
    db.inicializar(conn)
    with db.transaccion(conn):
        sql(conn, "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) VALUES (1, ?, ?)",
            (100_000_000, "2026-08-01"))
        for gmail_id, fecha, monto, descripcion in (
            ("id-inventado-1", "2026-08-05T10:00:00", 2590000, "TIENDA EJEMPLO"),
            ("id-inventado-2", "2026-08-18T10:00:00", 950000, "SUPERMERCADO INVENTADO"),
            ("id-inventado-3", "2026-08-10T10:00:00", 123400, "TIENDA EJEMPLO"),  # no está en el banco
        ):
            sql(conn, "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, origen, gmail_id) "
                      "VALUES (?, ?, 'compra', ?, 'gmail', ?)", (fecha, monto, descripcion, gmail_id))
        sql(conn, "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, origen, estado) "
                  "VALUES ('2026-08-22T09:00:00', 16000000, 'ingreso', 'Consignación', 'manual', 'provisional')")
    conn.close()
    return ruta_db


@pytest.fixture
def entorno(monkeypatch, ruta_db):
    from finanzas.seguridad import generar_hash

    monkeypatch.setenv("APP_PASSWORD_HASH", generar_hash("clave-de-prueba-inventada"))
    monkeypatch.setenv("SESSION_SECRET", "secreto-de-prueba-inventado-de-mas-de-32-caracteres")
    monkeypatch.setenv("DB_PATH", ruta_db)
    monkeypatch.setenv("GMAIL_TOKEN", "/ruta/inventada/token.json")
    monkeypatch.delenv("GMAIL_REMITENTE", raising=False)


@pytest.fixture
def archivo(tmp_path):
    ruta = tmp_path / "Movimientos.xlsx"
    ruta.write_bytes(excel_inventado.generar_excel(FILAS))
    return ruta


def _huella(ruta_db: str):
    carpeta = Path(ruta_db).parent
    return hashlib.sha256(Path(ruta_db).read_bytes()).hexdigest(), sorted(p.name for p in carpeta.iterdir())


def test_muestra_solo_conteos_y_no_escribe_nada(base, entorno, archivo, capsys):
    antes = _huella(base)
    assert conciliacion_en_seco.main([str(archivo)]) == 0
    salida = capsys.readouterr()
    assert _huella(base) == antes  # la base no cambió (ni se creó nada al lado)
    texto = salida.out
    assert "Filas del reporte: 7." in texto
    assert "Resumen: 2 ya estaban, 3 faltaban, 1 para preguntar, 1 no están en el banco." in texto
    assert "- anteriores a tu fecha de inicio (no se importarían): 1" in texto
    assert "- con Referencia sin formato (entrarían sin destino): 1" in texto
    assert "- para preguntar \"¿es el mismo?\": 1" in texto
    for dato in PRIVADO:
        assert dato not in texto + salida.err


def test_lee_el_archivo_de_la_entrada_estandar(base, entorno, archivo, capsys):
    entrada = io.BytesIO(archivo.read_bytes())
    assert conciliacion_en_seco.main(["-"], entrada=entrada) == 0
    assert "Resumen: 2 ya estaban, 3 faltaban" in capsys.readouterr().out


def test_correrla_dos_veces_da_lo_mismo(base, entorno, archivo, capsys):
    conciliacion_en_seco.main([str(archivo)])
    primera = capsys.readouterr().out
    conciliacion_en_seco.main([str(archivo)])
    assert capsys.readouterr().out == primera


def test_la_base_se_abre_en_solo_lectura(base):
    from sqlalchemy import text

    conn = conciliacion_en_seco.conectar_solo_lectura(base)
    try:
        with pytest.raises(Exception, match="readonly"):
            conn.execute(text("DELETE FROM movimientos"))
    finally:
        conn.close()


def test_funciona_con_una_base_de_la_0007(tmp_path, entorno, archivo, monkeypatch, capsys):
    from tests.soporte.migraciones import crear_base_v1

    ruta = tmp_path / "base-0007.db"
    crear_base_v1(ruta)
    _subir_hasta(ruta, "0007")
    monkeypatch.setenv("DB_PATH", str(ruta))
    antes = _huella(str(ruta))
    assert conciliacion_en_seco.main([str(archivo)]) == 0
    assert "Filas del reporte: 7." in capsys.readouterr().out
    assert _huella(str(ruta)) == antes
    assert migrar.revision_final() == "0012"  # y no la subió


def test_archivo_que_no_es_un_reporte(base, entorno, tmp_path, capsys):
    ruta = tmp_path / "otra-cosa.xlsx"
    ruta.write_bytes(b"no es un excel 3000000001")
    assert conciliacion_en_seco.main([str(ruta)]) == 2
    salida = capsys.readouterr()
    assert "no se reconoce" in salida.err and "3000000001" not in salida.err + salida.out


def test_sin_base_sin_archivo_o_sin_fecha_de_inicio(entorno, archivo, tmp_path, ruta_db, monkeypatch, capsys):
    assert conciliacion_en_seco.main([str(archivo)]) == 2  # no existe la base
    assert "No existe la base" in capsys.readouterr().err
    conn = db.conectar(ruta_db)
    db.inicializar(conn)
    conn.close()
    assert conciliacion_en_seco.main([str(archivo)]) == 2  # sin fecha de inicio
    assert "fecha de inicio" in capsys.readouterr().err
    assert conciliacion_en_seco.main([str(tmp_path / "no-existe.xlsx")]) == 2
    assert "No se pudo leer el archivo" in capsys.readouterr().err


def test_un_error_inesperado_solo_muestra_su_tipo(base, entorno, archivo, monkeypatch, capsys):
    def falla(*_args, **_kw):
        raise ValueError("dato secreto 3000000001 $25.900")

    monkeypatch.setattr(OperarReportes, "planear", falla)
    assert conciliacion_en_seco.main([str(archivo)]) == 1
    error = capsys.readouterr().err
    assert "ValueError" in error and "3000000001" not in error and "25.900" not in error


def test_sin_configuracion_de_entorno(monkeypatch, archivo, capsys):
    monkeypatch.delenv("APP_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    assert conciliacion_en_seco.main([str(archivo)]) == 2
    assert "Error de configuración" in capsys.readouterr().err
