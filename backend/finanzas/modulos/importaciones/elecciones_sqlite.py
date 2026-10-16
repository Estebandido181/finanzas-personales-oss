"""Decisiones explícitas del dueño por ocurrencia de una fila bancaria.

No decide identidad ni consume reservas: el motor revalida cada elección
frente al respaldo actual y usa cada movimiento una sola vez.
"""
from sqlalchemy import Connection, select, update

from finanzas.infraestructura import persistencia as db
from finanzas.compartido import hora


def listar_elecciones_banco(conn: Connection) -> list[dict]:
    """Última elección por (fecha, monto firmado, referencia, ordinal).

    El ordinal lo calcula el motor sobre todas las filas del reporte dentro
    de esa clave exacta, sin descripción. El caller conserva su snapshot.
    """
    t = db.preguntas_conciliacion
    filas = conn.execute(select(t).where(t.c.fuente == "banco",
        t.c.respuesta.is_not(None), t.c.movimiento_elegido_id.is_not(None),
        t.c.ocurrencia_banco.is_not(None)).order_by(t.c.respondida_en.desc(), t.c.id.desc())).mappings()
    ultimas = {}
    for fila in filas:
        clave = (fila["fecha"], fila["monto_centavos"], fila["referencia"], fila["ocurrencia_banco"])
        if clave not in ultimas:
            ultimas[clave] = {nombre: fila[nombre] for nombre in (
                "fecha", "monto_centavos", "referencia", "ocurrencia_banco", "movimiento_elegido_id")}
    return list(ultimas.values())


def guardar_eleccion_banco(conn: Connection, pregunta_id: int, movimiento_id: int) -> None:
    """Después de aplicar una respuesta, dentro de la MISMA transacción.

    Sirve tanto para el candidato elegido como para el movimiento creado
    por una respuesta «no». No puede reescribir una elección ya guardada.
    """
    if not db.en_transaccion(conn):
        raise ValueError("La elección requiere la transacción de la respuesta.")
    if type(pregunta_id) is not int or pregunta_id <= 0 or type(movimiento_id) is not int or movimiento_id <= 0:
        raise ValueError("Identidad de elección inválida.")
    t = db.preguntas_conciliacion
    fila = conn.execute(select(t).where(t.c.id == pregunta_id)).mappings().first()
    if fila is None or fila["fuente"] != "banco" or fila["respuesta"] not in ("si", "no") or fila["respondida_en"] is None or fila["ocurrencia_banco"] is None:
        raise ValueError("La pregunta necesita una respuesta aplicada y una ocurrencia bancaria.")
    if conn.execute(select(db.movimientos.c.id).where(db.movimientos.c.id == movimiento_id)).first() is None:
        raise ValueError("El movimiento elegido no existe.")
    if fila["movimiento_elegido_id"] not in (None, movimiento_id):
        raise ValueError("Esta pregunta ya conserva otra elección.")
    if fila["movimiento_elegido_id"] is None:
        # Hora del servidor con precisión suficiente para respuestas 2→1;
        # repetir el helper no convierte una elección vieja en la última.
        resultado = conn.execute(update(t).where(t.c.id == pregunta_id,
            t.c.movimiento_elegido_id.is_(None), t.c.respuesta == fila["respuesta"],
            t.c.respondida_en == fila["respondida_en"], t.c.ocurrencia_banco == fila["ocurrencia_banco"]).values(
            movimiento_elegido_id=movimiento_id,
            respondida_en=hora.ahora_colombia().replace(tzinfo=None).isoformat(timespec="microseconds")))
        if resultado.rowcount != 1:
            raise ValueError("La respuesta cambió mientras se guardaba la elección.")
