"""Configuración persistida: participante sin transacciones autónomas."""
from datetime import date
from sqlalchemy import select
from finanzas.infraestructura import persistencia as db
from finanzas.modulos.saldo.contratos import Configuracion


class SaldoSQLite:
    def __init__(self, conn):
        self._conn = conn

    def leer(self) -> Configuracion | None:
        c = db.configuracion_saldo.c
        fila = self._conn.execute(select(c.saldo_inicial_centavos, c.fecha_inicio).where(c.id == 1)).first()
        return None if fila is None else Configuracion(int(fila[0]), date.fromisoformat(str(fila[1])[:10]))

    def guardar(self, monto: int, inicio: date) -> None:
        insercion = db.insertar(self._conn, db.configuracion_saldo).values(id=1, saldo_inicial_centavos=monto, fecha_inicio=inicio.isoformat())
        self._conn.execute(insercion.on_conflict_do_update(index_elements=["id"], set_={
            "saldo_inicial_centavos": insercion.excluded.saldo_inicial_centavos,
            "fecha_inicio": insercion.excluded.fecha_inicio,
        }))
