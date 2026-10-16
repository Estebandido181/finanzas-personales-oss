"""Participante de reglas: persistencia sin transacciones propias."""
from sqlalchemy import Connection, case, delete, or_, select, update

from finanzas.infraestructura import persistencia as db
from finanzas.modulos.categorias.contratos import CopiaRegla, ReglaGuardada, ReglaConCategoria


class ReglasSQLite:
    def __init__(self, conn: Connection):
        self._conn = conn

    def buscar(self, regla_id: int) -> ReglaGuardada | None:
        fila = self._conn.execute(select(db.reglas).where(db.reglas.c.id == regla_id)).mappings().first()
        return None if fila is None else ReglaGuardada(**fila)

    def existe_equivalente(self, copia: CopiaRegla, texto: str | None) -> bool:
        r = db.reglas.c
        return self._conn.execute(select(r.id).where(
            r.campo == copia.campo,
            r.texto.is_(None) if texto is None else r.texto == texto,
            r.monto_centavos.is_(None) if copia.monto_centavos is None else r.monto_centavos == copia.monto_centavos,
            r.modo_texto == copia.modo_texto, r.origen_regla == copia.origen_regla,
        )).first() is not None

    def borrar(self, regla_id: int) -> None:
        self._conn.execute(delete(db.reglas).where(db.reglas.c.id == regla_id))

    def restaurar(self, copia: CopiaRegla, texto: str | None) -> int:
        valores = dict(campo=copia.campo, texto=texto, monto_centavos=copia.monto_centavos,
                       categoria_id=copia.categoria_id, modo_texto=copia.modo_texto,
                       origen_regla=copia.origen_regla, texto_visible=copia.texto_visible)
        if self.buscar(copia.id) is None:
            valores["id"] = copia.id
        return int(self._conn.execute(db.reglas.insert().values(**valores)).inserted_primary_key[0])

    def candidatas(self, campo: str, monto_centavos: int | None) -> list[ReglaGuardada]:
        r = db.reglas.c
        condicion = r.monto_centavos.is_(None) if monto_centavos is None else or_(r.monto_centavos.is_(None), r.monto_centavos == monto_centavos)
        return [ReglaGuardada(**fila) for fila in self._conn.execute(
            select(db.reglas).where(r.campo == campo, condicion)
        ).mappings()]

    def guardar(self, nueva, categoria_id: int) -> int:
        r = db.reglas.c
        regla_id = self._conn.execute(select(r.id).where(
            r.campo == nueva.campo,
            r.texto.is_(None) if nueva.texto is None else r.texto == nueva.texto,
            r.monto_centavos.is_(None) if nueva.monto_centavos is None else r.monto_centavos == nueva.monto_centavos,
            r.modo_texto == nueva.modo_texto, r.origen_regla == nueva.origen_regla,
        )).scalar()
        if regla_id is None:
            return int(self._conn.execute(db.reglas.insert().values(
                campo=nueva.campo, texto=nueva.texto, monto_centavos=nueva.monto_centavos,
                categoria_id=categoria_id, modo_texto=nueva.modo_texto,
                origen_regla=nueva.origen_regla, texto_visible=nueva.texto_visible,
            )).inserted_primary_key[0])
        valores = {"categoria_id": categoria_id}
        if nueva.texto_visible is not None:
            valores["texto_visible"] = nueva.texto_visible
        self._conn.execute(update(db.reglas).where(r.id == regla_id).values(**valores))
        return int(regla_id)

    def listar_con_categoria(self) -> list[ReglaConCategoria]:
        r, c = db.reglas.c, db.categorias.c
        especificidad = case((r.texto.is_not(None), 2), else_=0) + case((r.monto_centavos.is_not(None), 1), else_=0)
        consulta = select(db.reglas, c.nombre.label("categoria"), c.clase.label("categoria_clase"),
                          c.color.label("categoria_color"), c.icono.label("categoria_icono"))
        consulta = consulta.join_from(db.reglas, db.categorias, c.id == r.categoria_id)
        return [ReglaConCategoria(**f) for f in self._conn.execute(
            consulta.order_by(r.campo, especificidad.desc(), r.texto, r.monto_centavos, r.id)
        ).mappings()]
