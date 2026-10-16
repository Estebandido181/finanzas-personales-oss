"""Destinos inventados: privacidad, categorías, conflictos y rollback del41."""
from finanzas.bootstrap.saldo import componer_saldo

import os
import importlib

import pytest
from alembic.util import CommandError

from finanzas import categorizacion, db, migrar
from tests.soporte.migracion_0005 import _sql, _subir_hasta
from tests.soporte.migracion_0008 import _saldo
from tests.soporte.migraciones import crear_base_v1, huella, revision


@pytest.fixture
def base(tmp_path):
    ruta = tmp_path / "inventada.db"
    crear_base_v1(ruta)
    _subir_hasta(ruta, "0008")
    return ruta


def _regla(base, id_, texto, categoria=3, monto=None):
    _sql(base, "INSERT INTO reglas (id,campo,texto,categoria_id,monto_centavos) "
               "VALUES (?,'cuenta_destino',?,?,?)", (id_, texto, categoria, monto))


def test_revision():
    assert migrar.revision_final() == "0012"
    assert migrar._scripts().get_revision("0009").down_revision == "0008"


def test_recorta_todas_las_superficies_sin_cambiar_dinero_o_categorias(base):
    _regla(base, 20, "*3000002468")
    _sql(base, "UPDATE movimientos SET descripcion='*3000002468', categoria_id=3, "
               "origen_categoria='regla', regla_id=20 WHERE id=2")
    _sql(base, "INSERT INTO preguntas_conciliacion "
               "(tipo,fuente,fecha,monto_centavos,descripcion,gmail_id,tipo_movimiento) "
               "VALUES ('es_el_mismo','correo','2026-08-15T09:00:00',620000,'*3000001357',"
               "'inventado-pregunta','transferencia')")
    anterior = _saldo(base)
    asignaciones = _sql(base, "SELECT id,categoria_id,regla_id,monto_centavos FROM movimientos ORDER BY id")
    # La regla exacta histórica apuntaba a3; tras recortar debe seguir igual.
    assert _sql(base, "SELECT categoria_id FROM reglas WHERE texto='*3000002468'") == [(3,)]
    migrar.aplicar(str(base))
    assert _sql(base, "SELECT descripcion FROM movimientos WHERE id=2") == [("*2468",)]
    assert _sql(base, "SELECT descripcion FROM preguntas_conciliacion") == [("*1357",)]
    assert _sql(base, "SELECT texto FROM reglas WHERE id=20") == [("*2468",)]
    assert _sql(base, "SELECT id,categoria_id,regla_id,monto_centavos FROM movimientos ORDER BY id") == asignaciones
    conn = db.conectar(str(base))
    assert componer_saldo(conn).saldo_actual() == anterior
    assert categorizacion.regla_que_coincide(conn, 'transferencia', '*3000002468', 600000)['categoria_id'] == 3
    conn.close()
    assert _sql(base, "PRAGMA foreign_key_check") == []
    antes = huella(base)
    assert migrar.aplicar(str(base)).al_dia
    assert huella(base) == antes


@pytest.mark.parametrize("monto", [None, 500000])
def test_choque_detiene_todo_aun_con_montos_diferentes(base, monto):
    _regla(base, 20, '*3000002468', 3)
    _regla(base, 21, '*3111112468', 8, monto)
    antes = huella(base)
    with pytest.raises(CommandError) as error:
        migrar.aplicar(str(base))
    texto = str(error.value)
    assert '*2468' in texto and 'regla 20' in texto and 'regla 21' in texto
    assert '3000002468' not in texto and '3111112468' not in texto
    assert '500000' not in texto
    assert huella(base) == antes and revision(base) == '0008'


def test_consolida_equivalentes_y_conserva_condiciones_monto(base):
    _regla(base, 20, '*3000002468')
    _regla(base, 21, '*3111112468')
    _regla(base, 22, '*2468', monto=600000)
    _sql(base, "UPDATE movimientos SET origen_categoria='regla',regla_id=21,categoria_id=3 WHERE id=2")
    migrar.aplicar(str(base))
    assert _sql(base, "SELECT id,texto,monto_centavos FROM reglas WHERE id>=20 ORDER BY id") == [
        (20,'*2468',None), (22,'*2468',600000)]
    assert _sql(base, "SELECT id,regla_id,categoria_id FROM movimientos WHERE id=2") == [(2,20,3)]
    assert _sql(base, "PRAGMA foreign_key_check") == []


def test_no_recorta_comercios_remitentes_o_nombres_breb(base):
    _regla(base, 20, 'persona ejemplo')
    _sql(base, "UPDATE movimientos SET descripcion='TIENDA *3000002468' WHERE id=1")
    _sql(base, "UPDATE movimientos SET descripcion='PERSONA EJEMPLO' WHERE id=2")
    antes = _sql(base, "SELECT id,descripcion FROM movimientos ORDER BY id")
    migrar.aplicar(str(base))
    assert _sql(base, "SELECT id,descripcion FROM movimientos ORDER BY id") == antes
    assert _sql(base, "SELECT texto FROM reglas WHERE id=20") == [('persona ejemplo',)]


def test_recorta_destino_numerico_largo_en_regla_y_movimiento(base):
    largo = '*'+ '0'*26 + '2468'
    _regla(base,20,largo)
    _sql(base, "UPDATE movimientos SET descripcion=? WHERE id=2",(largo,))
    migrar.aplicar(str(base))
    assert _sql(base, "SELECT texto FROM reglas WHERE id=20") == [('*2468',)]
    assert _sql(base, "SELECT descripcion FROM movimientos WHERE id=2") == [('*2468',)]


def test_recorte_limpia_celdas_liberadas_de_base_inventada(base):
    _regla(base,20,'*3000002468')
    _regla(base,21,'*3111112468')
    _sql(base,"UPDATE movimientos SET descripcion='*3000001357' WHERE id=2")
    assert b'3000002468' in base.read_bytes()
    migrar.aplicar(str(base))
    for original in (b'3000002468',b'3111112468',b'3000001357'):
        assert original not in base.read_bytes()


@pytest.mark.parametrize('fallar',[False,True])
def test_borrado_seguro_se_limita_a_conexion_y_restaura_pragma(base,fallar):
    modulo=importlib.import_module('finanzas.migraciones.versions.0009_destinos_correo')
    conn=db.conectar(str(base))
    conn.exec_driver_sql('PRAGMA secure_delete=OFF')
    try:
        try:
            with modulo._borrado_seguro(conn):
                assert conn.exec_driver_sql('PRAGMA secure_delete').scalar_one() == 1
                if fallar:
                    raise RuntimeError('fallo inventado')
        except RuntimeError:
            assert fallar
        assert conn.exec_driver_sql('PRAGMA secure_delete').scalar_one() == 0
    finally:
        conn.close()


def test_fallo_sql_revierte_recorte_consolidacion_y_revision(base):
    _regla(base, 20, '*3000002468')
    _regla(base, 21, '*3111112468')
    _sql(base, "UPDATE movimientos SET descripcion='*3000002468', origen_categoria='regla', "
               "regla_id=21, categoria_id=3 WHERE id=2")
    _sql(base, "CREATE TRIGGER fallo_inventado BEFORE UPDATE ON movimientos "
               "BEGIN SELECT RAISE(ABORT,'fallo inventado'); END")
    antes = huella(base)
    with pytest.raises(Exception, match='fallo inventado'):
        migrar.aplicar(str(base))
    assert huella(base) == antes and revision(base) == '0008'


def test_downgrade_se_niega_sin_tocar_nada(base):
    migrar.aplicar(str(base))
    antes = huella(base)
    with pytest.raises(CommandError, match='respaldo previo'):
        migrar.bajar_a(str(base), '0008')
    assert huella(base) == antes and revision(base) == '0012'


@pytest.mark.skipif(os.name == 'nt', reason='Respaldo seguro requiere permisos/fsync POSIX; CI Ubuntu')
def test_comando_respalda_original_y_exige_restaurarlo(base,tmp_path,capsys):
    _regla(base, 20, '*3000002468')
    carpeta = tmp_path / 'respaldos'
    carpeta.mkdir()
    assert migrar.main(['--base', str(base), '--respaldos', str(carpeta)]) == 0
    salida = capsys.readouterr().out
    assert '*3000002468' not in salida and '*2468' not in salida
    [copia] = carpeta.glob('finanzas-antes-de-migrar-0008-*.db')
    assert revision(copia) == '0008'
    assert _sql(copia, 'SELECT texto FROM reglas WHERE id=20') == [('*3000002468',)]
    assert migrar.main(['--base', str(base),'--respaldos',str(carpeta),'--bajar-a','0008']) == 1
    assert 'respaldo previo' in capsys.readouterr().err
