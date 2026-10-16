"""Conciliación con el banco: estados, destino, importaciones y preguntas.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-02

Ítem 29 (D37 a D40, D44 y D45). El número 0008 lo fijó el team leader.

``upgrade``:

1. ``movimientos`` se reconstruye (SQLite no cambia un CHECK sin rehacer la
   tabla) con los mismos ids y datos, y cuatro columnas nuevas al final:

   * ``estado``: ``confirmado`` (lo respalda el banco), ``provisional``
     (ingreso manual aún sin respaldo, D39) o ``sin_aviso`` (vino del banco y
     no del correo). Lo del correo sin conciliar y los ajustes quedan en NULL
     (D45). Un CHECK amarra cada estado a su origen.
   * ``referencia``: destino que trajo el banco, **solo** ``*`` + 4 dígitos
     (D37). Un CHECK rechaza cualquier otra forma: la base no puede guardar
     un número completo.
   * ``fecha_banco``: día de la fila del banco que respalda el movimiento.
     Es la clave para que importar dos veces no cambie nada.
   * ``no_en_banco``: 1 si es del correo, está dentro de las fechas de un
     reporte y el banco no lo trae (D38). Solo es una marca: nada se borra.

   Además: ``origen`` admite ``extracto``; un movimiento del banco puede
   llevar el ``gmail_id`` del aviso que llegó después (D45); y un ajuste
   puede quedar en 0 cuando lo importado lo reduce del todo (D45; el
   "deshacer" del 30 lo restaura). ``saldo.ajustar_saldo`` sigue sin guardar
   ajustes de 0.

   Los ingresos manuales que ya existen pasan a ``provisional`` (D39). Nada
   más cambia: el saldo es exactamente el mismo.

2. Tablas nuevas, vacías:

   * ``importaciones``: una fila por importación, con las fechas del reporte
     y los conteos. Nunca el archivo.
   * ``cambios_importacion``: qué movimiento entró o cambió en cada
     importación y sus valores anteriores, para el "deshacer" del ítem 30.
   * ``preguntas_conciliacion`` y ``candidatos_pregunta``: lo que decide el
     dueño ("¿es el mismo?" y "¿ya estaba en el saldo que ajustaste?"). Lo
     dudoso espera aquí y no mueve el saldo hasta la respuesta.

``downgrade``: vuelve a la estructura exacta de la 0007 **sin perder
datos**, o se niega (``CommandError``) sin tocar nada. Solo baja si no hay
nada de la conciliación: ningún movimiento del banco, confirmado o marcado,
ningún ajuste en 0, ninguna importación ni pregunta. Si las hay, se restaura
el respaldo previo a la migración (D26).

Como toda migración, está escrita sin depender de ``finanzas.db``.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from alembic.util import CommandError

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AHORA = sa.text("(strftime('%Y-%m-%dT%H:%M:%S', 'now'))")
REFERENCIA_VALIDA = "referencia IS NULL OR referencia GLOB '[*][0-9][0-9][0-9][0-9]'"
FECHA_VALIDA = "{c} IS NULL OR {c} GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'"

CHECK_ESTADO_POR_ORIGEN = (
    "CASE origen "
    "WHEN 'extracto' THEN COALESCE(estado, '') IN ('confirmado', 'sin_aviso') "
    "WHEN 'manual' THEN (tipo = 'ajuste' AND estado IS NULL) "
    "OR (tipo <> 'ajuste' AND COALESCE(estado, 'provisional') IN ('provisional', 'confirmado')) "
    "ELSE estado IS NULL OR estado = 'confirmado' END"
)
CHECK_FECHA_BANCO = "(fecha_banco IS NOT NULL) = (COALESCE(estado, '') IN ('confirmado', 'sin_aviso'))"
CHECK_NO_EN_BANCO = "no_en_banco = 0 OR (origen = 'gmail' AND estado IS NULL)"
CHECK_GMAIL_ID = (
    "(origen = 'gmail' AND gmail_id IS NOT NULL) OR (origen = 'manual' AND gmail_id IS NULL) "
    "OR origen = 'extracto'"
)

COLUMNAS_0007 = (
    "id, fecha_hora, monto_centavos, tipo, descripcion, categoria_id, origen, gmail_id, "
    "registrado_en, origen_categoria, regla_id"
)

MENSAJE_NO_SE_PUEDE_BAJAR = (
    "No se puede volver a la revisión 0007 sin perder datos: ya hay movimientos importados "
    "del banco, confirmados o marcados, ajustes en 0, importaciones o preguntas de la "
    "conciliación, que la 0007 no puede guardar. No se cambió nada. Restaura el respaldo "
    "previo a la migración (deploy/GUIA.md)."
)


def _solo_sqlite(texto: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(texto).ddl_if(dialect="sqlite")


def _entero_no_negativo(nombre: str) -> sa.Column:
    return sa.Column(
        nombre,
        sa.Integer,
        _solo_sqlite(f"typeof({nombre}) = 'integer'"),
        sa.CheckConstraint(f"{nombre} >= 0"),
        nullable=False,
        server_default="0",
    )


def _columnas_base(origenes: str) -> list:
    return [
        sa.Column("id", sa.Integer, primary_key=True, nullable=True),
        sa.Column("fecha_hora", sa.Text, nullable=False),
        sa.Column(
            "monto_centavos",
            sa.Integer,
            _solo_sqlite("typeof(monto_centavos) = 'integer'"),
            nullable=False,
        ),
        sa.Column(
            "tipo",
            sa.Text,
            sa.CheckConstraint("tipo IN ('compra', 'transferencia', 'ingreso', 'ajuste')"),
            nullable=False,
        ),
        sa.Column("descripcion", sa.Text, nullable=False, server_default=""),
        sa.Column("categoria_id", sa.Integer, sa.ForeignKey("categorias.id")),
        sa.Column("origen", sa.Text, sa.CheckConstraint(f"origen IN ({origenes})"), nullable=False),
        sa.Column("gmail_id", sa.Text, unique=True),
        sa.Column("registrado_en", sa.Text, nullable=False, server_default=AHORA),
        sa.Column(
            "origen_categoria", sa.Text, sa.CheckConstraint("origen_categoria IN ('manual', 'regla')")
        ),
        sa.Column("regla_id", sa.Integer, sa.ForeignKey("reglas.id")),
    ]


def _crear_movimientos_0008() -> None:
    op.create_table(
        "movimientos",
        *_columnas_base("'gmail', 'manual', 'extracto'"),
        sa.Column(
            "estado",
            sa.Text,
            sa.CheckConstraint("estado IN ('confirmado', 'provisional', 'sin_aviso')"),
        ),
        sa.Column("referencia", sa.Text, _solo_sqlite(REFERENCIA_VALIDA)),
        sa.Column("fecha_banco", sa.Text, _solo_sqlite(FECHA_VALIDA.format(c="fecha_banco"))),
        sa.Column(
            "no_en_banco",
            sa.Integer,
            sa.CheckConstraint("no_en_banco IN (0, 1)"),
            nullable=False,
            server_default="0",
        ),
        sa.CheckConstraint("tipo = 'ajuste' OR monto_centavos > 0"),
        sa.CheckConstraint(CHECK_GMAIL_ID),
        sa.CheckConstraint("regla_id IS NULL OR COALESCE(origen_categoria, '') = 'regla'"),
        sa.CheckConstraint(CHECK_ESTADO_POR_ORIGEN),
        sa.CheckConstraint(CHECK_FECHA_BANCO),
        sa.CheckConstraint(CHECK_NO_EN_BANCO),
        sa.CheckConstraint("referencia IS NULL OR fecha_banco IS NOT NULL"),
    )
    op.create_index("idx_movimientos_fecha_hora", "movimientos", ["fecha_hora"])


def _crear_movimientos_0007() -> None:
    op.create_table(
        "movimientos",
        *_columnas_base("'gmail', 'manual'"),
        sa.CheckConstraint(
            "(tipo = 'ajuste' AND monto_centavos <> 0) OR (tipo <> 'ajuste' AND monto_centavos > 0)"
        ),
        sa.CheckConstraint("(origen = 'gmail') = (gmail_id IS NOT NULL)"),
        sa.CheckConstraint("regla_id IS NULL OR COALESCE(origen_categoria, '') = 'regla'"),
    )
    op.create_index("idx_movimientos_fecha_hora", "movimientos", ["fecha_hora"])


def _crear_tablas_nuevas() -> None:
    op.create_table(
        "importaciones",
        sa.Column("id", sa.Integer, primary_key=True, nullable=True),
        sa.Column("hecha_en", sa.Text, nullable=False, server_default=AHORA),
        sa.Column("desde", sa.Text, _solo_sqlite(FECHA_VALIDA.format(c="desde"))),
        sa.Column("hasta", sa.Text, _solo_sqlite(FECHA_VALIDA.format(c="hasta"))),
        _entero_no_negativo("filas"),
        _entero_no_negativo("ya_estaban"),
        _entero_no_negativo("agregados"),
        _entero_no_negativo("confirmados"),
        _entero_no_negativo("corregidos"),
        _entero_no_negativo("preguntas"),
        _entero_no_negativo("no_en_banco"),
        _entero_no_negativo("anteriores"),
        _entero_no_negativo("sin_formato"),
        sa.Column("deshecha_en", sa.Text),
    )
    op.create_table(
        "cambios_importacion",
        sa.Column("id", sa.Integer, primary_key=True, nullable=True),
        sa.Column("importacion_id", sa.Integer, sa.ForeignKey("importaciones.id"), nullable=False),
        sa.Column("movimiento_id", sa.Integer, sa.ForeignKey("movimientos.id"), nullable=False),
        sa.Column(
            "accion",
            sa.Text,
            sa.CheckConstraint(
                "accion IN ('agregado', 'confirmado', 'corregido', 'marcado', 'ajuste_reducido')"
            ),
            nullable=False,
        ),
        # Valores del movimiento antes del cambio (NULL en "agregado").
        sa.Column("monto_anterior", sa.Integer),
        sa.Column("estado_anterior", sa.Text),
        sa.Column("no_en_banco_anterior", sa.Integer),
        sa.Column("fecha_banco_anterior", sa.Text),
        sa.Column("referencia_anterior", sa.Text, _solo_sqlite(
            "referencia_anterior IS NULL OR referencia_anterior GLOB '[*][0-9][0-9][0-9][0-9]'"
        )),
        sa.UniqueConstraint("importacion_id", "movimiento_id", "accion"),
    )
    op.create_table(
        "preguntas_conciliacion",
        sa.Column("id", sa.Integer, primary_key=True, nullable=True),
        sa.Column(
            "tipo",
            sa.Text,
            sa.CheckConstraint("tipo IN ('es_el_mismo', 'ya_estaba_en_ajuste')"),
            nullable=False,
        ),
        # De dónde viene lo que espera: una fila del banco o un aviso del correo.
        sa.Column("fuente", sa.Text, sa.CheckConstraint("fuente IN ('banco', 'correo')"), nullable=False),
        sa.Column("importacion_id", sa.Integer, sa.ForeignKey("importaciones.id")),
        sa.Column("creada_en", sa.Text, nullable=False, server_default=AHORA),
        # Banco: día (AAAA-MM-DD) y monto con signo. Correo: fecha y hora, y monto > 0.
        sa.Column("fecha", sa.Text, nullable=False),
        sa.Column(
            "monto_centavos",
            sa.Integer,
            _solo_sqlite("typeof(monto_centavos) = 'integer'"),
            sa.CheckConstraint("monto_centavos <> 0"),
            nullable=False,
        ),
        sa.Column("descripcion", sa.Text, nullable=False, server_default=""),
        sa.Column("referencia", sa.Text, _solo_sqlite(REFERENCIA_VALIDA)),
        # Solo en las del correo: lo necesario para guardarlo si no es el mismo.
        sa.Column("gmail_id", sa.Text, unique=True),
        sa.Column(
            "tipo_movimiento",
            sa.Text,
            sa.CheckConstraint("tipo_movimiento IN ('compra', 'transferencia', 'ingreso')"),
        ),
        sa.Column("categoria_al_leer", sa.Text),
        sa.Column("ajuste_id", sa.Integer, sa.ForeignKey("movimientos.id")),
        sa.Column("respondida_en", sa.Text),
        sa.Column("respuesta", sa.Text, sa.CheckConstraint("respuesta IN ('si', 'no')")),
        sa.CheckConstraint("(fuente = 'correo') = (gmail_id IS NOT NULL)"),
        sa.CheckConstraint("(fuente = 'correo') = (tipo_movimiento IS NOT NULL)"),
        sa.CheckConstraint("fuente = 'banco' OR monto_centavos > 0"),
        sa.CheckConstraint("(respuesta IS NULL) = (respondida_en IS NULL)"),
    )
    op.create_table(
        "candidatos_pregunta",
        sa.Column(
            "pregunta_id", sa.Integer, sa.ForeignKey("preguntas_conciliacion.id"), primary_key=True
        ),
        sa.Column("movimiento_id", sa.Integer, sa.ForeignKey("movimientos.id"), primary_key=True),
        # 1 si el candidato es un aviso que llegó después de importar (D45).
        sa.Column(
            "de_aviso",
            sa.Integer,
            sa.CheckConstraint("de_aviso IN (0, 1)"),
            nullable=False,
            server_default="0",
        ),
    )


def upgrade() -> None:
    op.execute(f"CREATE TABLE movimientos_copia_0008 AS SELECT {COLUMNAS_0007} FROM movimientos")
    op.drop_table("movimientos")
    _crear_movimientos_0008()
    op.execute(
        f"INSERT INTO movimientos ({COLUMNAS_0007}, estado) "
        f"SELECT {COLUMNAS_0007}, "
        "CASE WHEN origen = 'manual' AND tipo = 'ingreso' THEN 'provisional' END "
        "FROM movimientos_copia_0008"
    )
    op.drop_table("movimientos_copia_0008")
    _crear_tablas_nuevas()


def downgrade() -> None:
    conexion = op.get_bind()
    hay = conexion.execute(
        sa.text(
            "SELECT (SELECT COUNT(*) FROM movimientos WHERE origen = 'extracto' "
            "OR COALESCE(estado, '') IN ('confirmado', 'sin_aviso') OR no_en_banco = 1 "
            "OR referencia IS NOT NULL OR fecha_banco IS NOT NULL "
            "OR (tipo = 'ajuste' AND monto_centavos = 0)) "
            "+ (SELECT COUNT(*) FROM importaciones) "
            "+ (SELECT COUNT(*) FROM preguntas_conciliacion)"
        )
    ).scalar_one()
    if hay:
        raise CommandError(MENSAJE_NO_SE_PUEDE_BAJAR)
    for tabla in ("candidatos_pregunta", "preguntas_conciliacion", "cambios_importacion", "importaciones"):
        op.drop_table(tabla)
    op.execute(f"CREATE TABLE movimientos_copia_0008 AS SELECT {COLUMNAS_0007} FROM movimientos")
    op.drop_table("movimientos")
    _crear_movimientos_0007()
    op.execute(f"INSERT INTO movimientos ({COLUMNAS_0007}) SELECT {COLUMNAS_0007} FROM movimientos_copia_0008")
    op.drop_table("movimientos_copia_0008")
