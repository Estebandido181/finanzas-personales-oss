"""Reservas y registro: participante de la transacción compartida."""
from sqlalchemy import Connection, select, update

from finanzas.infraestructura import persistencia as db
from finanzas.modulos.movimientos.descartes_contratos import MovimientoInexistente
from finanzas.modulos.movimientos.consultas_sqlite import ajuste_posterior


class DescartesSQLite:
    def __init__(self, conn: Connection):
        self._conn = conn

    def movimiento(self, ident: int) -> dict:
        fila = self._conn.execute(select(db.movimientos).where(db.movimientos.c.id == ident)).mappings().first()
        if fila is None:
            raise MovimientoInexistente("El movimiento no existe.")
        return dict(fila)

    def activo(self, ident: int) -> dict | None:
        t = db.descartes_movimientos
        fila = self._conn.execute(select(t).where(t.c.movimiento_id == ident, t.c.restaurado_en.is_(None))).mappings().first()
        return None if fila is None else dict(fila)

    def hubo(self, ident: int) -> bool:
        t = db.descartes_movimientos
        return self._conn.execute(select(t.c.id).where(t.c.movimiento_id == ident)).first() is not None

    def ajuste_posterior(self, ident: int) -> bool:
        m = db.movimientos.c
        return self._conn.execute(select(m.id).where(m.id == ident, ajuste_posterior(m))).first() is not None

    def pregunta_pendiente(self, ident: int) -> bool:
        p, k = db.preguntas_conciliacion, db.candidatos_pregunta
        return self._conn.execute(select(k.c.movimiento_id).join(p, p.c.id == k.c.pregunta_id)
            .where(k.c.movimiento_id == ident, p.c.respuesta.is_(None))).first() is not None

    def marcar_borrado(self, ident: int, momento: str | None) -> None:
        self._conn.execute(update(db.movimientos).where(db.movimientos.c.id == ident).values(borrado_en=momento))

    def guardar_reserva(self, valores: dict) -> None:
        self._conn.execute(db.descartes_movimientos.insert().values(**valores))

    def marcar_restaurado(self, reserva_id: int, momento: str) -> None:
        self.actualizar_respaldo(reserva_id, {"restaurado_en": momento})

    def movimientos_descartados(self) -> list[dict]:
        t, m = db.descartes_movimientos, db.movimientos
        return [dict(f) for f in self._conn.execute(select(m, t.c.id.label("descarte_id"), t.c.descartado_en)
            .join(t, t.c.movimiento_id == m.c.id).where(t.c.restaurado_en.is_(None)).order_by(t.c.id.desc())).mappings()]

    def reservas_activas(self) -> list[dict]:
        t = db.descartes_movimientos
        return [dict(f) for f in self._conn.execute(select(t).where(t.c.restaurado_en.is_(None)).order_by(t.c.id)).mappings()]

    def actualizar_respaldo(self, reserva_id: int, valores: dict) -> None:
        t = db.descartes_movimientos
        self._conn.execute(update(t).where(t.c.id == reserva_id).values(**valores))
