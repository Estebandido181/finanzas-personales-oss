"""Registro bancario prestado: mismas guardas SQL, sin motor consumidor ni commits."""
from sqlalchemy import Connection, text, select, update
from finanzas.infraestructura import persistencia as db
from finanzas.infraestructura.esquema_compatible import columnas as _columnas

_SQL_FILA_ACTUAL = text(
    "SELECT monto_centavos, estado, no_en_banco, fecha_banco, referencia FROM movimientos WHERE id = :id"
)


class RegistroBancarioSQLite:
    def __init__(self, conn: Connection):
        self._conn = conn

    def estado_actual(self, ident: int) -> tuple:
        return tuple(self._conn.execute(_SQL_FILA_ACTUAL, {"id": ident}).one())

    def confirmar(self, ident: int, fecha: str, referencia: str | None, monto_centavos: int, corregir: bool) -> None:
        self._conn.execute(text(
            "UPDATE movimientos SET estado = 'confirmado', fecha_banco = :fecha, "
            "referencia = COALESCE(referencia, :referencia), no_en_banco = 0"
            + (", monto_centavos = :monto" if corregir else "") + " WHERE id = :id AND fecha_banco IS NULL"),
            {"fecha": fecha, "referencia": referencia, "monto": monto_centavos, "id": ident})

    def confirmar_descartado(self, ident: int, monto_centavos: int, estado: str, fecha: str, referencia: str | None) -> bool:
        hecho = self._conn.execute(text(
            "UPDATE movimientos SET monto_centavos = :monto, estado = :estado, fecha_banco = :fecha, "
            "referencia = :referencia, no_en_banco = 0 WHERE id = :id AND borrado_en IS NOT NULL"),
            {"monto": monto_centavos, "estado": estado, "fecha": fecha, "referencia": referencia, "id": ident})
        return hecho.rowcount == 1

    def reducir_ajuste(self, ident: int, efecto: int) -> None:
        self._conn.execute(text("UPDATE movimientos SET monto_centavos = monto_centavos - :efecto WHERE id = :id AND tipo = 'ajuste'"),
            {"efecto": efecto, "id": ident})

    def marcar_ausencia(self, ident: int) -> None:
        self._conn.execute(text("UPDATE movimientos SET no_en_banco = 1 WHERE id = :id AND origen = 'gmail'"), {"id": ident})

    def vincular_descartado(self, ident: int, gmail_id: str) -> bool:
        hecho = self._conn.execute(text("UPDATE movimientos SET gmail_id = :g, estado = 'confirmado' "
            "WHERE id = :id AND origen = 'extracto' AND gmail_id IS NULL AND borrado_en IS NOT NULL"),
            {"g": gmail_id, "id": ident})
        return hecho.rowcount == 1

    def vincular_si_libre(self, ident: int, gmail_id: str) -> None:
        self._conn.execute(text("UPDATE movimientos SET gmail_id = :g, estado = 'confirmado' WHERE id = :id AND gmail_id IS NULL"),
            {"g": gmail_id, "id": ident})

    def vincular_extracto_activo(self, ident: int, gmail_id: str) -> bool:
        hecho = self._conn.execute(text("UPDATE movimientos SET gmail_id = :g, estado = 'confirmado' "
            "WHERE id = :id AND origen = 'extracto' AND gmail_id IS NULL"
            + (" AND borrado_en IS NULL" if "borrado_en" in _columnas(self._conn, "movimientos") else "")),
            {"g": gmail_id, "id": ident})
        return hecho.rowcount == 1

    def fila_para_aplicar(self, ident: int) -> dict | None:
        fila = self._conn.execute(text("SELECT tipo, monto_centavos, fecha_banco, referencia, "
            + ("borrado_en" if "borrado_en" in _columnas(self._conn, "movimientos") else "NULL AS borrado_en")
            + " FROM movimientos WHERE id = :id"), {"id": ident}).mappings().first()
        return None if fila is None else dict(fila)

    def filas_por_ids(self, ids: list[int]) -> list[dict]:
        return [dict(f) for f in self._conn.execute(select(db.movimientos).where(db.movimientos.c.id.in_(ids))).mappings()]

    def asignar_categoria_regla(self, ident: int, categoria_id: int, regla_id: int) -> None:
        self._conn.execute(update(db.movimientos).where(db.movimientos.c.id == ident).values(
            categoria_id=categoria_id, origen_categoria="regla", regla_id=regla_id))

    def marcar_decision(self, ident: int, borrado_en: str | None) -> None:
        self._conn.execute(update(db.movimientos).where(db.movimientos.c.id == ident).values(
            revisado_no_en_banco=1, borrado_en=borrado_en))
