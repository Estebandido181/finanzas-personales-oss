"""Fotografías y reversión del diario sobre una única conexión prestada."""
from sqlalchemy import select, update, delete, and_
from finanzas.infraestructura import persistencia as db
from .contratos import (TablaDiario, ConflictoImportacion, MENSAJE_REVERSION)
from .diario import _json, huella_de_foto

TABLAS_DIARIO = (db.configuracion_saldo, db.movimientos, db.preguntas_conciliacion,
    db.candidatos_pregunta, db.cambios_importacion, db.correos_no_reconocidos, db.estado_sincronizacion,
    db.descartes_movimientos)
TABLAS_HUELLA = (*TABLAS_DIARIO, db.importaciones, db.categorias, db.reglas)
TABLAS = {t.name: t for t in TABLAS_DIARIO}

def _foto(conn, tablas=TABLAS_DIARIO):
    return {t.name: [dict(f) for f in conn.execute(select(t).order_by(*t.primary_key.columns)).mappings()]
            for t in tablas}



def _clave(tabla, fila):
    return {col.name: fila[col.name] for col in tabla.primary_key.columns}



def _where(tabla, clave):
    return and_(*(tabla.c[k] == v for k, v in clave.items()))



def _coincide(conn, cambios):
    for cambio in cambios:
        t = TABLAS[cambio["tabla"]]
        actual = conn.execute(select(t).where(_where(t, cambio["clave"]))).mappings().first()
        esperado = cambio["despues"]
        if cambio["tabla"] == "preguntas_conciliacion" and esperado is not None:
            # Diarios previos a 0012 no conocían las columnas nuevas. Solo
            # equivalen a NULL: una elección posterior sigue siendo conflicto.
            esperado = {"ocurrencia_banco": None, "movimiento_elegido_id": None, **esperado}
        if (None if actual is None else dict(actual)) != esperado:
            return False
    return True



def _revertir(conn, cambios):
    if not _coincide(conn, cambios):
        raise ConflictoImportacion(MENSAJE_REVERSION)
    # Una respuesta «no» puede crear el movimiento elegido. Desvincular su
    # pregunta existente antes de borrar ese padre evita romper la FK.
    for cambio in cambios:
        if cambio["tabla"] == "preguntas_conciliacion" and cambio["antes"] is not None and cambio["despues"] is not None:
            if cambio["antes"].get("movimiento_elegido_id") is None and cambio["despues"].get("movimiento_elegido_id") is not None:
                conn.execute(update(db.preguntas_conciliacion).where(
                    _where(db.preguntas_conciliacion, cambio["clave"])).values(movimiento_elegido_id=None))
    # Primero hijos nuevos, luego padres. Después restituir valores y filas.
    for cambio in reversed(cambios):
        if cambio["antes"] is None:
            t = TABLAS[cambio["tabla"]]
            conn.execute(delete(t).where(_where(t, cambio["clave"])))
    for cambio in cambios:
        t = TABLAS[cambio["tabla"]]
        if cambio["antes"] is not None:
            if cambio["despues"] is None:
                conn.execute(t.insert().values(**cambio["antes"]))
            else:
                conn.execute(update(t).where(_where(t, cambio["clave"])).values(**cambio["antes"]))



def _hijos_ajenos(conn, cambios):
    """Detecta dependencias que sobrevivirían al borrado, sin ejecutar DELETE.

    Usa las claves completas del diario, incluidas las PK compuestas de los
    candidatos. Las lecturas comparten la transacción del detalle o del undo.
    """
    nuevos = [c for c in cambios if c["antes"] is None and c["despues"] is not None]
    eliminados = {(c["tabla"], _json(c["clave"])) for c in nuevos}
    por_clave = {(c["tabla"], _json(c["clave"])): c for c in cambios}
    for tabla in TABLAS_DIARIO:
        for fk in tabla.foreign_key_constraints:
            for padre in nuevos:
                if fk.referred_table.name != padre["tabla"]:
                    continue
                condicion = and_(*(e.parent == padre["despues"][e.column.name] for e in fk.elements))
                for hijo in conn.execute(select(tabla).where(condicion)).mappings():
                    if (tabla.name, _json(_clave(tabla, hijo))) not in eliminados:
                        propio = por_clave.get((tabla.name, _json(_clave(tabla, hijo))))
                        # Solo la FK de elección que _revertir desvincula,
                        # con la fila completa exactamente como en el diario.
                        if tabla is db.preguntas_conciliacion and {e.parent.name for e in fk.elements} == {"movimiento_elegido_id"} and propio and propio["antes"] is not None and propio["antes"].get("movimiento_elegido_id") is None and propio["despues"] == dict(hijo):
                            continue
                        return True
    return False



def tablas_del_diario() -> tuple[TablaDiario, ...]:
    return tuple(TablaDiario(t.name, tuple(col.name for col in t.primary_key.columns)) for t in TABLAS_DIARIO)


def huella(conn):
    return huella_de_foto(_foto(conn, TABLAS_HUELLA))


class DiarioSQLite:
    def __init__(self, conn):
        self._conn = conn

    def foto(self):
        return _foto(self._conn)

    def huella(self):
        return huella(self._conn)

    def revertir(self, cambios):
        _revertir(self._conn, cambios)

    def coincide(self, cambios):
        return _coincide(self._conn, cambios)

    def hijos_ajenos(self, cambios):
        return _hijos_ajenos(self._conn, cambios)
