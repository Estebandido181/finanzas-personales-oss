"""El lector y las reglas comparten el destino reducido, sin ampliar gramática."""

import pytest

from finanzas import categorizacion as cat, db
from finanzas.modulos.categorias.destinos import recortar_destino
from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import extraer_transferiste
from tests.soporte.extractor import transferiste


@pytest.mark.parametrize('destino', ['*1234','*3000002468','*00000000000000001357'])
def test_lector_solo_devuelve_cuatro_y_regla_equivalente(destino):
    movimiento = extraer_transferiste(transferiste().replace('*5678',destino))
    assert movimiento.descripcion == '*'+destino[-4:]
    assert cat.condiciones_de_regla('transferencia',destino,600000).texto == movimiento.descripcion
    assert movimiento.monto_centavos == 600000


@pytest.mark.parametrize('texto', ['PERSONA EJEMPLO','tienda *3000002468','*123','**3000002468','*3000 002468'])
def test_helper_no_adivina_ni_recorta_nombres(texto):
    assert recortar_destino(texto) == texto


def test_regla_historica_larga_se_recorta_sin_ampliar_lector():
    largo = '*'+ '0'*26 + '2468'
    assert recortar_destino(largo) == '*2468'
    assert cat.condiciones_de_regla('transferencia',largo,600000).texto == '*2468'
    assert extraer_transferiste(transferiste().replace('*5678',largo)) is None


def test_restaurar_copia_legacy_no_reintroduce_destino_completo(tmp_path):
    ruta = str(tmp_path/'inventada.db')
    db.preparar(ruta)
    conn = db.conectar(ruta)
    try:
        copia = cat.CopiaRegla(id=80,campo='cuenta_destino',texto='*3000002468',
                              monto_centavos=None,categoria_id=3,movimientos=())
        id_ = cat.restaurar_regla(conn,copia)
        regla = conn.exec_driver_sql('SELECT texto FROM reglas WHERE id=?',(id_,)).scalar_one()
        assert regla == '*2468'
        assert cat.regla_que_coincide(conn,'transferencia','*3111112468',600000)['id'] == id_
    finally:
        conn.close()
