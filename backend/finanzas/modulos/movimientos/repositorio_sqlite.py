"""Participante SQLite: usa la transacción del dueño, sin abrirla ni confirmarla."""
from datetime import datetime
from dataclasses import asdict
from sqlalchemy import Connection, case, column, delete, func, insert, literal, literal_column, or_, select, update

from sqlalchemy import table as sa_table
from finanzas.infraestructura import persistencia as db
from finanzas.modulos.movimientos.consultas_sqlite import ajuste_posterior as _ajuste_posterior, _conciliado, _se_puede_borrar
from finanzas.modulos.movimientos.publico import MovimientoParaCategorizar, MovimientoPendiente, ResumenRegistroPendiente, MovimientoNuevo


class MovimientosSQLite:
    def __init__(self, conn: Connection):
        self._conn = conn

    def registrar(self, movimiento: MovimientoNuevo) -> int:
        return int(self._conn.execute(db.movimientos.insert().values(**asdict(movimiento))).inserted_primary_key[0])

    def registrar_correo_si_nuevo(self, movimiento: MovimientoNuevo) -> bool:
        resultado = self._conn.execute(db.insertar(self._conn, db.movimientos).values(**asdict(movimiento))
            .on_conflict_do_nothing(index_elements=["gmail_id"]))
        return resultado.rowcount == 1

    def uso_por_categoria(self, desde: datetime, hasta: datetime) -> dict[int, tuple[int, int]]:
        m = db.movimientos.c
        limites = (desde.isoformat(timespec="seconds"), hasta.isoformat(timespec="seconds"))
        en_mes = (m.fecha_hora >= limites[0]) & (m.fecha_hora < limites[1]) & m.borrado_en.is_(None)
        filas = self._conn.execute(select(m.categoria_id, func.sum(case((en_mes, 1), else_=0)), func.count())
            .where(m.categoria_id.is_not(None)).group_by(m.categoria_id))
        return {int(categoria): (int(mes), int(total)) for categoria, mes, total in filas}

    def contar_en_categoria(self, categoria_id: int) -> int:
        return int(self._conn.execute(
            select(func.count()).select_from(db.movimientos).where(db.movimientos.c.categoria_id == categoria_id)
        ).scalar_one())

    def reasignar_categoria(self, categoria_id: int, destino_id: int) -> None:
        self._conn.execute(
            update(db.movimientos).where(db.movimientos.c.categoria_id == categoria_id).values(categoria_id=destino_id)
        )

    @staticmethod
    def _consulta():
        m = db.movimientos.c
        return select(m.id, m.tipo, m.descripcion, m.monto_centavos, m.origen, m.referencia)

    def buscar_activo(self, movimiento_id: int) -> MovimientoParaCategorizar | None:
        m = db.movimientos.c
        fila = self._conn.execute(
            self._consulta().where(m.id == movimiento_id, m.borrado_en.is_(None))
        ).mappings().first()
        return MovimientoParaCategorizar(**fila) if fila is not None else None

    def listar_pendientes(self, tipo: str) -> list[MovimientoParaCategorizar]:
        m = db.movimientos.c
        return [MovimientoParaCategorizar(**fila) for fila in self._conn.execute(
            self._consulta().where(m.tipo == tipo, m.categoria_id.is_(None), m.borrado_en.is_(None))
        ).mappings()]

    def asignar_manual(self, movimiento_id: int, categoria_id: int) -> int:
        m = db.movimientos.c
        return self._conn.execute(
            update(db.movimientos).where(m.id == movimiento_id)
            .values(categoria_id=categoria_id, origen_categoria="manual", regla_id=None)
        ).rowcount

    def listar_pendientes_por_ids(self, ids: list[int], tipos: tuple[str, ...]) -> list[MovimientoParaCategorizar]:
        m = db.movimientos.c
        return [MovimientoParaCategorizar(**fila) for fila in self._conn.execute(
            self._consulta().where(m.id.in_(ids), m.tipo.in_(tipos), m.categoria_id.is_(None), m.borrado_en.is_(None))
        ).mappings()]

    def asignar_grupo_si_pendientes(self, ids: list[int], categoria_id: int) -> int:
        m = db.movimientos.c
        return self._conn.execute(
            update(db.movimientos).where(m.id.in_(ids), m.categoria_id.is_(None))
            .values(categoria_id=categoria_id, origen_categoria="manual", regla_id=None)
        ).rowcount

    def asignar_por_regla_si_pendiente(self, movimiento_id: int, categoria_id: int, regla_id: int) -> int:
        m = db.movimientos.c
        # La guarda histórica protege las categorías ya asignadas.
        return self._conn.execute(
            update(db.movimientos).where(m.id == movimiento_id, m.categoria_id.is_(None))
            .values(categoria_id=categoria_id, origen_categoria="regla", regla_id=regla_id)
        ).rowcount

    def ids_por_regla(self, regla_id: int) -> tuple[int, ...]:
        m = db.movimientos.c
        return tuple(int(i) for i in self._conn.execute(
            select(m.id).where(m.regla_id == regla_id).order_by(m.id)
        ).scalars())

    def desvincular_regla(self, regla_id: int) -> None:
        self._conn.execute(update(db.movimientos).where(db.movimientos.c.regla_id == regla_id).values(regla_id=None))

    def revincular_regla_si_compatible(self, ids: tuple[int, ...], categoria_id: int, regla_id: int) -> None:
        if not ids:
            return
        m = db.movimientos.c
        self._conn.execute(update(db.movimientos).where(
            m.id.in_(ids), m.origen_categoria == "regla", m.regla_id.is_(None), m.categoria_id == categoria_id,
        ).values(regla_id=regla_id))

    @staticmethod
    def _pendientes():
        m = db.movimientos.c
        return (m.categoria_id.is_(None), m.tipo.in_(("compra", "transferencia", "ingreso")), m.borrado_en.is_(None))

    def consultar_pendientes(self) -> list[MovimientoPendiente]:
        m = db.movimientos.c
        return [MovimientoPendiente(**f) for f in self._conn.execute(
            select(m.id, m.fecha_hora, m.monto_centavos, m.tipo, m.descripcion, m.origen)
            .where(*self._pendientes()).order_by(m.fecha_hora.desc(), m.id.desc())
        ).mappings()]

    def resumir_pendientes(self) -> ResumenRegistroPendiente:
        m = db.movimientos.c
        def suma(tipos):
            return func.coalesce(func.sum(case((m.tipo.in_(tipos), m.monto_centavos), else_=0)), 0)
        fila = self._conn.execute(select(func.count(), suma(("compra", "transferencia")), suma(("ingreso",)))
            .select_from(db.movimientos).where(*self._pendientes())).one()
        return ResumenRegistroPendiente(*(int(v) for v in fila))

    def filas_del_periodo(self, desde: datetime, hasta: datetime) -> tuple[list[dict], list[dict]]:
        limites = (desde.isoformat(timespec="seconds"), hasta.isoformat(timespec="seconds"))
        m, c, r = db.movimientos.c, db.categorias.c, db.reglas.c
        con_categoria = db.movimientos.outerjoin(db.categorias, c.id == m.categoria_id)
        con_regla = con_categoria.outerjoin(db.reglas, r.id == m.regla_id)
        del_mes = (m.fecha_hora >= limites[0], m.fecha_hora < limites[1], m.borrado_en.is_(None))

        # Por id: los nombres son únicos solo dentro de cada clase.
        filas_categoria = self._conn.execute(
            select(
                c.id.label("id"), c.nombre.label("nombre"), c.color.label("color"),
                c.icono.label("icono"), func.sum(m.monto_centavos).label("centavos"),
            )
            .select_from(con_categoria)
            .where(m.tipo.in_(("compra", "transferencia")), *del_mes)
            .group_by(c.id, c.nombre, c.color, c.icono)
        ).mappings().all()
        filas_movimientos = self._conn.execute(
            select(
                m.id, m.fecha_hora, m.tipo, m.descripcion, m.monto_centavos,
                c.nombre.label("categoria"), m.categoria_id, m.origen,
                c.clase.label("categoria_clase"), c.color.label("categoria_color"),
                c.icono.label("categoria_icono"),
                m.origen_categoria, r.id.label("regla_id"), r.campo.label("regla_campo"),
                r.texto.label("regla_texto"), r.monto_centavos.label("regla_monto_centavos"),
                r.modo_texto.label("regla_modo_texto"), r.origen_regla.label("regla_origen_regla"),
                r.texto_visible.label("regla_texto_visible"),
            )
            .select_from(con_regla)
            .where(*del_mes)
            .order_by(m.fecha_hora.desc(), m.id.desc())
        ).mappings().all()
        return ([dict(f) for f in filas_categoria], [dict(f) for f in filas_movimientos])


    def componentes_saldo(self) -> tuple[int, int, int, int] | None:
        """Las partes de ``saldo_actual`` en un único SELECT (mismas reglas y mismo filtro de fecha).

        Lanza ``SaldoNoConfigurado`` si falta la configuración.
        """
        c, m = (db.configuracion_saldo.c, db.movimientos.c)

        def suma(condicion):
            return func.coalesce(func.sum(case((condicion, m.monto_centavos), else_=0)), 0)
        desde = func.substr(c.fecha_inicio, 1, 10).concat(literal('T00:00:00'))
        fila = self._conn.execute(select(c.saldo_inicial_centavos, suma(m.tipo == "ingreso"), suma(m.tipo.in_(("compra", "transferencia"))), suma(m.tipo == "ajuste")).select_from(db.configuracion_saldo.outerjoin(db.movimientos, (m.fecha_hora >= desde) & m.borrado_en.is_(None))).where(c.id == 1).group_by(c.id)).first()
        if fila is None:
            return None
        return tuple(int(valor) for valor in fila)

    def suma_entre(self, tipos: tuple[str, ...], desde: str, hasta: str) -> int:
        m = db.movimientos.c
        total = self._conn.execute(select(func.coalesce(func.sum(m.monto_centavos), 0)).where(m.tipo.in_(tipos), m.fecha_hora >= desde, m.fecha_hora < hasta, m.borrado_en.is_(None))).scalar_one()
        return int(total)

    def ultimos_ingresos_y_ajustes(self, limite: int=20) -> list[dict]:
        """Los ingresos y ajustes más recientes (por fecha y hora, luego por id)."""
        m = db.movimientos.c
        return [dict(f) for f in self._conn.execute(select(m.id, m.fecha_hora, m.monto_centavos, m.tipo, m.descripcion).where(m.tipo.in_(("ingreso", "ajuste")), m.borrado_en.is_(None)).order_by(m.fecha_hora.desc(), m.id.desc()).limit(limite)).mappings()]

    def ingresos_y_ajustes_entre(self, desde: str, hasta: str) -> list[dict]:
        """Ingresos (de Gmail y manuales) y ajustes con ``desde <= fecha_hora < hasta``.

        Del más reciente al más antiguo. Cada fila trae ``origen`` y
        ``se_puede_borrar`` (la misma regla que aplica ``borrar_ingreso``: la
        pantalla solo la muestra).
        """
        m = db.movimientos.c
        return [dict(f) for f in self._conn.execute(select(m.id, m.fecha_hora, m.monto_centavos, m.tipo, m.descripcion, m.origen, case((_se_puede_borrar(m), True), else_=False).label('se_puede_borrar')).where(m.tipo.in_(("ingreso", "ajuste")), m.fecha_hora >= desde, m.fecha_hora < hasta, m.borrado_en.is_(None)).order_by(m.fecha_hora.desc(), m.id.desc())).mappings()]

    def ajustes_entre(self, desde: str, hasta: str) -> tuple[int, int]:
        """``(total en centavos con signo, cantidad)`` de los ajustes con ``desde <= fecha_hora < hasta``."""
        m = db.movimientos.c
        total, cantidad = self._conn.execute(select(func.coalesce(func.sum(m.monto_centavos), 0), func.count(m.id)).where(m.tipo == "ajuste", m.fecha_hora >= desde, m.fecha_hora < hasta)).one()
        return (int(total), int(cantidad))

    def hay_movimientos(self) -> bool:
        return self._conn.execute(select(db.movimientos.c.id).limit(1)).first() is not None

    def datos_borrabilidad(self, ident: int) -> dict | None:
        m = db.movimientos.c
        fila = self._conn.execute(select(m.tipo, m.origen, m.gmail_id, m.monto_centavos,
            _ajuste_posterior(m).label("ajuste_posterior"), _conciliado(m).label("conciliado"))
            .where(m.id == ident)).mappings().first()
        return None if fila is None else dict(fila)

    def copia_movimiento(self, ident: int) -> dict:
        # SELECT * preserva también las columnas de migraciones posteriores.
        return dict(self._conn.execute(select(literal_column("*")).select_from(db.movimientos)
            .where(db.movimientos.c.id == ident)).mappings().one())

    def categoria_identidad(self, ident: int) -> tuple[str, str] | None:
        c = db.categorias.c
        fila = self._conn.execute(select(c.nombre, c.clase).where(c.id == ident)).first()
        return None if fila is None else (str(fila[0]), str(fila[1]))

    def ultima_importacion_id(self) -> int:
        return int(self._conn.execute(select(func.coalesce(func.max(db.importaciones.c.id), 0))).scalar_one())

    def borrar_manual_si_permitido(self, ident: int) -> int:
        return self._conn.execute(delete(db.movimientos).where(db.movimientos.c.id == ident,
            _se_puede_borrar(db.movimientos.c))).rowcount

    def hay_ajuste_para_restaurar(self, ident: int, fecha_hora: str) -> bool:
        m = db.movimientos.c
        return self._conn.execute(select(m.id).where(m.tipo == "ajuste",
            or_(m.id >= ident, m.fecha_hora > fecha_hora)).limit(1)).first() is not None

    def hubo_importacion_desde(self, ident: int) -> bool:
        return self._conn.execute(select(db.importaciones.c.id).where(db.importaciones.c.id > ident).limit(1)).first() is not None

    def existe_regla(self, ident: int) -> bool:
        return self._conn.execute(select(db.reglas.c.id).where(db.reglas.c.id == ident)).first() is not None

    def existe_movimiento(self, ident: int) -> bool:
        return self._conn.execute(select(db.movimientos.c.id).where(db.movimientos.c.id == ident)).first() is not None

    def restaurar_fila_completa(self, valores: dict) -> int:
        tabla = sa_table(db.movimientos.name, *(column(nombre) for nombre in valores))
        resultado = self._conn.execute(insert(tabla).values(**valores))
        return int(valores["id"]) if "id" in valores else int(resultado.lastrowid)
