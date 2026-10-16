"""Expresiones del registro compartidas por sus adaptadores."""
from sqlalchemy import and_, exists, or_
from finanzas.infraestructura import persistencia as db


def ajuste_posterior(fila):
    """Condición SQL: hay un ajuste posterior al movimiento ``fila`` (columnas de ``movimientos``).

    "Posterior" en cualquiera de los dos sentidos: registrado después (id
    mayor) o con fecha y hora posterior. Así, un ingreso solo se puede borrar
    si quedó fuera de **todo** saldo ya cuadrado: si se registró antes del
    ajuste, el ajuste ya lo tuvo en cuenta; si tiene fecha anterior al ajuste
    (aunque se haya registrado después), en la lista aparecería antes del
    ajuste y borrarlo confundiría.
    """
    ajuste = db.movimientos.alias("ajuste")
    return exists().where(
        ajuste.c.tipo == "ajuste",
        or_(ajuste.c.id > fila.id, ajuste.c.fecha_hora > fila.fecha_hora),
    )


def _conciliado(fila):
    """Condición SQL: la conciliación con el banco (ítem 29) ya lo tocó.

    Lo confirmó el banco (``fecha_banco``), quedó en el registro de una
    importación o es candidato de una pregunta. Borrarlo dejaría una fila del
    banco sin su movimiento (al reimportar entraría otra vez) y rompería las
    claves de ``cambios_importacion`` y ``candidatos_pregunta``.
    """
    return or_(
        fila.fecha_banco.is_not(None),
        exists().where(db.cambios_importacion.c.movimiento_id == fila.id),
        exists().where(db.candidatos_pregunta.c.movimiento_id == fila.id),
    )


def _se_puede_borrar(fila):
    """Condición SQL de ``borrar_ingreso``: ingreso, manual, sin ajuste posterior y sin conciliar."""
    return and_(
        fila.tipo == "ingreso",
        fila.origen == "manual",
        fila.gmail_id.is_(None),
        ~ajuste_posterior(fila),
        ~_conciliado(fila),
    )
