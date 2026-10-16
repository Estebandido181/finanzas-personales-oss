"""Persistencia de elecciones por multiplicidad, con datos inventados."""
from datetime import datetime
import pytest
from sqlalchemy import select, update
from finanzas import db, gestion_importaciones as gestion
from finanzas.modulos.importaciones import elecciones_sqlite as elecciones
from tests.soporte.ayudas_api import *  # noqa: F401,F403


def pregunta(config, ordinal=1):
    return ejecutar_sql(config, "INSERT INTO preguntas_conciliacion (tipo,fuente,fecha,monto_centavos,ocurrencia_banco) VALUES ('es_el_mismo','banco','2026-08-10',-12300,?)", (ordinal,)).lastrowid


def responder(conn, ident, elegido, respuesta="si"):
    conn.execute(update(db.preguntas_conciliacion).where(db.preguntas_conciliacion.c.id == ident).values(
        respuesta=respuesta, respondida_en="2026-08-11T10:00:00"))
    elecciones.guardar_eleccion_banco(conn, ident, elegido)


def test_ultima_respuesta_inversa_ordinal_e_idempotencia(config, monkeypatch):
    p1, p2, p3 = pregunta(config), pregunta(config), pregunta(config,2)
    m1 = insertar_movimiento(config, descripcion="COMERCIO UNO INVENTADO")
    m2 = insertar_movimiento(config, descripcion="COMERCIO DOS INVENTADO")
    tiempos = iter([datetime(2026,8,11,10,0,0,1), datetime(2026,8,11,10,0,0,2), datetime(2026,8,11,10,0,0,3)])
    monkeypatch.setattr(elecciones.hora, "ahora_colombia", lambda: next(tiempos))
    with db.conectar(config.db_path) as conn, db.transaccion(conn, inmediata=True):
        responder(conn,p2,m2)
        responder(conn,p1,m1)
        responder(conn,p3,m2,"no")
        elecciones.guardar_eleccion_banco(conn,p2,m2)  # no cambia orden ni hora
        lista = elecciones.listar_elecciones_banco(conn)
        assert {f["ocurrencia_banco"]: f["movimiento_elegido_id"] for f in lista} == {1:m1,2:m2}
        assert all(f["fecha"] == "2026-08-10" and f["monto_centavos"] == -12300 and f["referencia"] is None for f in lista)
        assert set(lista[0]) == {"fecha","monto_centavos","referencia","ocurrencia_banco","movimiento_elegido_id"}


def test_guardas_transaccion_respuesta_fk_y_no_reescritura(config):
    p = pregunta(config)
    m1 = insertar_movimiento(config, descripcion="COMERCIO UNO INVENTADO")
    m2 = insertar_movimiento(config, descripcion="COMERCIO DOS INVENTADO")
    with db.conectar(config.db_path) as conn:
        with pytest.raises(ValueError,match="transacción"):
            elecciones.guardar_eleccion_banco(conn,p,m1)
        with db.transaccion(conn,inmediata=True):
            with pytest.raises(ValueError,match="respuesta"):
                elecciones.guardar_eleccion_banco(conn,p,m1)
            conn.execute(update(db.preguntas_conciliacion).where(db.preguntas_conciliacion.c.id==p).values(respuesta="si",respondida_en="2026-08-11T10:00:00"))
            with pytest.raises(ValueError,match="existe"):
                elecciones.guardar_eleccion_banco(conn,p,999999)
            elecciones.guardar_eleccion_banco(conn,p,m1)
            with pytest.raises(ValueError,match="otra elección"):
                elecciones.guardar_eleccion_banco(conn,p,m2)
        assert elecciones.listar_elecciones_banco(conn)[0]["movimiento_elegido_id"] == m1


def test_undo_no_desvincula_pregunta_y_borra_movimiento_nuevo(config):
    p = pregunta(config)
    with db.conectar(config.db_path) as conn:
        with db.transaccion(conn,inmediata=True):
            antes = gestion._foto(conn)
            m = conn.execute(db.movimientos.insert().values(fecha_hora="2026-08-10T00:00:00",
                monto_centavos=12300,tipo="compra",descripcion="TIENDA INVENTADA",origen="extracto",
                estado="sin_aviso",fecha_banco="2026-08-10")).inserted_primary_key[0]
            responder(conn,p,m,"no")
            cambios = gestion.diario(antes, gestion._foto(conn))
            assert not gestion._hijos_ajenos(conn,cambios)
            assert gestion._coincide(conn,cambios)
            gestion._revertir(conn,cambios)
            assert gestion._foto(conn) == antes
        assert elecciones.listar_elecciones_banco(conn) == []


def test_undo_eleccion_ajena_conflicto_y_diario_legacy_null(config):
    p = pregunta(config)
    m = insertar_movimiento(config)
    with db.conectar(config.db_path) as conn, db.transaccion(conn,inmediata=True):
        fila = dict(conn.execute(select(db.preguntas_conciliacion).where(db.preguntas_conciliacion.c.id==p)).mappings().one())
        fila["ocurrencia_banco"] = None
        conn.execute(update(db.preguntas_conciliacion).where(db.preguntas_conciliacion.c.id==p).values(ocurrencia_banco=None))
        legacy = {k:v for k,v in fila.items() if k not in ("ocurrencia_banco","movimiento_elegido_id")}
        cambios = [dict(tabla="preguntas_conciliacion",clave={"id":p},antes=legacy,despues=legacy)]
        assert gestion._coincide(conn,cambios)
        conn.execute(update(db.preguntas_conciliacion).where(db.preguntas_conciliacion.c.id==p).values(ocurrencia_banco=1))
        assert not gestion._coincide(conn,cambios)
        responder(conn,p,m)
        padre = dict(conn.execute(select(db.movimientos).where(db.movimientos.c.id==m)).mappings().one())
        assert gestion._hijos_ajenos(conn,[dict(tabla="movimientos",clave={"id":m},antes=None,despues=padre)])


def test_respuesta_y_eleccion_rollback_juntas(config):
    p = pregunta(config)
    m = insertar_movimiento(config)
    with db.conectar(config.db_path) as conn:
        antes = gestion.huella(conn)
        with pytest.raises(RuntimeError):
            with db.transaccion(conn,inmediata=True):
                responder(conn,p,m)
                raise RuntimeError("fallo inventado")
        assert gestion.huella(conn) == antes
        assert elecciones.listar_elecciones_banco(conn) == []


def test_cas_no_sobrescribe_eleccion_cambiada_entre_lectura_y_escritura(config, monkeypatch):
    from sqlalchemy.sql.dml import Update
    p = pregunta(config)
    m1 = insertar_movimiento(config,descripcion="COMERCIO UNO INVENTADO")
    m2 = insertar_movimiento(config,descripcion="COMERCIO DOS INVENTADO")
    with db.conectar(config.db_path) as conn, db.transaccion(conn,inmediata=True):
        conn.execute(update(db.preguntas_conciliacion).where(db.preguntas_conciliacion.c.id==p).values(
            respuesta="si",respondida_en="2026-08-11T10:00:00"))
        ejecutar = conn.execute
        intervenido = False
        def intercalar(sentencia, *args, **kwargs):
            nonlocal intervenido
            if isinstance(sentencia, Update) and sentencia.table is db.preguntas_conciliacion and not intervenido:
                intervenido = True
                ejecutar(update(db.preguntas_conciliacion).where(db.preguntas_conciliacion.c.id==p).values(movimiento_elegido_id=m2))
            return ejecutar(sentencia,*args,**kwargs)
        monkeypatch.setattr(conn,"execute",intercalar)
        with pytest.raises(ValueError,match="cambió"):
            elecciones.guardar_eleccion_banco(conn,p,m1)
        assert elecciones.listar_elecciones_banco(conn)[0]["movimiento_elegido_id"] == m2
