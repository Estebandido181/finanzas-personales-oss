"""Adaptador de la consulta; conserva el SQL y orden históricos."""
from datetime import datetime
from sqlalchemy import Connection, and_, case, delete, func, select, true, update
from finanzas.infraestructura import persistencia as db
from finanzas.modulos.categorias.contratos import Categoria, CategoriaConUso


class CategoriasSQLite:
    def __init__(self, conn: Connection):
        self._conn = conn

    def buscar(self, categoria_id: int) -> Categoria | None:
        fila = self._conn.execute(select(db.categorias).where(db.categorias.c.id == categoria_id)).mappings().first()
        return None if fila is None else Categoria(**fila)

    def otras(self, excepto: int | None) -> list[Categoria]:
        return [Categoria(**fila) for fila in self._conn.execute(
            select(db.categorias).where(db.categorias.c.id != excepto if excepto is not None else true())
        ).mappings()]

    def insertar(self, nombre: str, clase: str, color: str, icono: str, id_preferido: int | None = None) -> int:
        valores = dict(nombre=nombre, clase=clase, color=color, icono=icono)
        if id_preferido is not None and self.buscar(id_preferido) is None:
            valores["id"] = id_preferido
        return int(self._conn.execute(db.categorias.insert().values(**valores)).inserted_primary_key[0])

    def actualizar(self, categoria_id: int, nombre: str, color: str, icono: str) -> None:
        self._conn.execute(update(db.categorias).where(db.categorias.c.id == categoria_id)
                           .values(nombre=nombre, color=color, icono=icono))

    def contar_clase(self, clase: str) -> int:
        return int(self._conn.execute(select(func.count()).select_from(db.categorias)
                                     .where(db.categorias.c.clase == clase)).scalar_one())

    def contar_reglas(self, categoria_id: int) -> int:
        return int(self._conn.execute(select(func.count()).select_from(db.reglas)
                                     .where(db.reglas.c.categoria_id == categoria_id)).scalar_one())

    def mover_reglas(self, categoria_id: int, destino_id: int) -> None:
        self._conn.execute(update(db.reglas).where(db.reglas.c.categoria_id == categoria_id).values(categoria_id=destino_id))

    def borrar(self, categoria_id: int) -> None:
        self._conn.execute(delete(db.categorias).where(db.categorias.c.id == categoria_id))

    def consultar_con_uso(self, desde: datetime, hasta: datetime, clase: str | None = None, *, uso: dict[int, tuple[int, int]]) -> list[CategoriaConUso]:
        c, r = db.categorias.c, db.reglas.c
        reglas = select(func.count()).select_from(db.reglas).where(r.categoria_id == c.id).scalar_subquery()
        consulta = select(c.id, c.nombre, c.clase, c.color, c.icono, reglas.label('reglas'))
        consulta = consulta.order_by(c.clase, case((and_(c.clase == db.CLASE_GASTO, c.nombre == 'Otros'), 1), else_=0), c.id)
        if clase is not None:
            consulta = consulta.where(c.clase == clase)
        return [CategoriaConUso(**fila, movimientos_mes=uso.get(fila['id'], (0, 0))[0],
                                movimientos_total=uso.get(fila['id'], (0, 0))[1])
                for fila in self._conn.execute(consulta).mappings()]

    def listar(self, clase: str | None = None) -> list[Categoria]:
        c = db.categorias.c
        consulta = select(db.categorias).order_by(c.clase, case((and_(c.clase == "gasto", c.nombre == "Otros"), 1), else_=0), c.id)
        if clase is not None:
            consulta = consulta.where(c.clase == clase)
        return [Categoria(**f) for f in self._conn.execute(consulta).mappings()]
