"""Unidad mínima sobre una conexión prestada; su dueño la cierra.

Participantes reciben esta misma conexión. Las fronteras reutilizan las
primitivas existentes: no introducen commits autónomos ni conexiones nuevas.
"""
from sqlalchemy import Connection
from finanzas.infraestructura import persistencia as db


class UnidadDeTrabajoSQLite:
    def __init__(self, conn: Connection):
        self._conn = conn

    def lectura(self):
        return db.lectura_consistente(self._conn)

    def en_transaccion(self) -> bool:
        return db.en_transaccion(self._conn)

    def escritura(self, inmediata: bool = False):
        # db.transaccion confirma al salir: solo el propietario puede abrirla.
        # Si ya hay una transacción, reutilizarla sin commit ni rollback local.
        from contextlib import nullcontext
        if db.en_transaccion(self._conn):
            return nullcontext()
        return db.transaccion(self._conn, inmediata=inmediata)
