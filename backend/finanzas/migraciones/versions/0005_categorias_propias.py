"""Categorías propias de gasto y de ingreso; reglas de ingreso por quien envía.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-01

Ítem 15. Hasta la 0004 las categorías eran la lista fija de la v1: una tabla
``categorias`` (``id``, ``nombre`` único) con 8 filas que nadie cambiaba.
Movimientos y reglas ya las referencian por ``id`` (clave foránea), así que
**ninguna asignación cambia**: los ids se conservan tal cual.

``upgrade``:

1. ``categorias`` gana ``clase`` (``gasto`` | ``ingreso``), ``color`` e
   ``icono``, y el nombre pasa a ser único **por clase** (``UNIQUE(nombre,
   clase)``). ``color`` es la clave de un token de ``frontend/diseno/tokens.css``
   (``cat-mercado`` por ``--cat-mercado``) e ``icono`` el nombre de un ícono de
   Lucide (``shopping-basket``), según la tabla "Categorías: color e ícono" de
   ``frontend/diseno/SISTEMA.md``. Nunca valores sueltos (``#5A6B1C``): el
   color exacto depende del modo claro u oscuro.
   Clase, color e ícono salen del nombre (``CATEGORIAS_INICIALES``): las 8 de
   la v1 quedan como ``gasto``. Un nombre que no esté en la tabla (en la v1 no
   puede existir) quedaría como gasto con el color y el ícono de "Otros".
2. Se añaden "Antojos" (gasto) y "Sueldo", "Préstamos" y "Otros ingresos"
   (ingreso), si no existen ya (p. ej. tras bajar a la 0004 y volver a subir).
3. ``reglas.campo`` admite ``quien_envia`` (reglas de ingresos).
4. Comprueba que ningún movimiento quede con una categoría de otra clase (un
   gasto con una de ingreso o al revés). En la base de la v1 no puede pasar:
   solo se categorizaban gastos y todas las categorías eran de gasto. Si
   pasara, se detiene sin cambiar nada (``CommandError``): adivinar movería
   dinero de un lado al otro del reporte.

SQLite no cambia un ``UNIQUE`` ni un ``CHECK`` con ``ALTER TABLE``: las dos
tablas se reconstruyen. Ambas están referenciadas (``movimientos.categoria_id``,
``reglas.categoria_id`` y ``movimientos.regla_id``), y renombrar una tabla
nueva sobre la vieja dejaría las claves foráneas sin padre para SQLite (el
``DROP`` cuenta a los hijos como violaciones diferidas y el ``RENAME`` no las
descuenta). Por eso se hace así, dentro de la transacción de la migración y
con ``PRAGMA defer_foreign_keys`` (``env.py``):

    copia temporal  ->  DROP de la tabla  ->  CREATE con el mismo nombre  ->
    INSERT desde la copia (mismos ids)  ->  DROP de la copia

Al volver a insertar los padres con el mismo nombre de tabla, SQLite
descuenta las violaciones. Si quedara alguna (un id perdido), el ``COMMIT``
falla y no cambia nada.

``downgrade``: vuelve a la estructura exacta de la 0004 **sin perder datos**,
o se niega (``CommandError``) sin tocar nada. Conserva todas las categorías
con sus ids (también las de ingreso, así ningún movimiento queda huérfano) y
quita ``clase``, ``color`` e ``icono``, que el ``upgrade`` vuelve a deducir
del nombre. Por eso solo baja si cada categoría es una de las 12 iniciales
sin cambios, y si no hay reglas de ingreso (el ``CHECK`` de la 0004 no las
admite). Si el dueño ya creó, renombró o recoloreó categorías, o guardó
reglas de ingreso, la 0004 no puede guardar eso: hay que restaurar el
respaldo previo a la migración (D26).

Como toda migración, está escrita sin depender de ``finanzas.db``.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from alembic.util import CommandError

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (nombre, clase, color, ícono) de las categorías iniciales (SISTEMA.md).
CATEGORIAS_INICIALES = (
    ("Mercado", "gasto", "cat-mercado", "shopping-basket"),
    ("Restaurantes", "gasto", "cat-restaurantes", "utensils"),
    ("Transporte", "gasto", "cat-transporte", "bus"),
    ("Vivienda y servicios", "gasto", "cat-vivienda", "house"),
    ("Salud", "gasto", "cat-salud", "heart-pulse"),
    ("Entretenimiento", "gasto", "cat-entretenimiento", "ticket"),
    ("Compras", "gasto", "cat-compras", "shopping-bag"),
    ("Antojos", "gasto", "cat-antojos", "ice-cream-cone"),
    ("Otros", "gasto", "cat-otros", "shapes"),
    ("Sueldo", "ingreso", "cat-sueldo", "briefcase"),
    ("Préstamos", "ingreso", "cat-prestamos", "handshake"),
    ("Otros ingresos", "ingreso", "cat-otros-ingresos", "coins"),
)
NUEVAS = ("Antojos", "Sueldo", "Préstamos", "Otros ingresos")
# Un nombre que no está en la tabla (no debería haber ninguno).
POR_DEFECTO = ("gasto", "cat-otros", "shapes")

MENSAJE_CLASE_MEZCLADA = (
    "Hay movimientos con una categoría de otra clase (un gasto con una categoría de ingreso "
    "o al revés): no se puede saber cuál es la buena. No se cambió nada. Corrige esas "
    "categorías en la versión actual de la app y vuelve a migrar."
)
MENSAJE_NO_SE_PUEDE_BAJAR = (
    "No se puede volver a la revisión 0004 sin perder datos: {motivo}. No se cambió nada. "
    "Restaura el respaldo previo a la migración (deploy/GUIA.md)."
)


def _crear_categorias_0005() -> None:
    op.create_table(
        "categorias",
        sa.Column("id", sa.Integer, primary_key=True, nullable=True),
        sa.Column("nombre", sa.Text, sa.CheckConstraint("nombre <> ''"), nullable=False),
        sa.Column(
            "clase",
            sa.Text,
            sa.CheckConstraint("clase IN ('gasto', 'ingreso')"),
            nullable=False,
        ),
        sa.Column("color", sa.Text, sa.CheckConstraint("color <> ''"), nullable=False),
        sa.Column("icono", sa.Text, sa.CheckConstraint("icono <> ''"), nullable=False),
        sa.UniqueConstraint("nombre", "clase"),
    )


def _crear_categorias_0004() -> None:
    op.create_table(
        "categorias",
        sa.Column("id", sa.Integer, primary_key=True, nullable=True),
        sa.Column("nombre", sa.Text, nullable=False, unique=True),
    )


def _crear_reglas(campos: str) -> None:
    op.create_table(
        "reglas",
        sa.Column("id", sa.Integer, primary_key=True, nullable=True),
        sa.Column("campo", sa.Text, sa.CheckConstraint(f"campo IN ({campos})"), nullable=False),
        sa.Column("texto", sa.Text, sa.CheckConstraint("texto <> ''"), nullable=False),
        sa.Column("categoria_id", sa.Integer, sa.ForeignKey("categorias.id"), nullable=False),
        sa.UniqueConstraint("campo", "texto"),
    )


def _rehacer(tabla: str, crear, columnas: str, seleccion: str | None = None) -> None:
    """Reconstruye ``tabla`` con ``crear()`` conservando las filas y sus ids (ver el docstring)."""
    copia = f"{tabla}_copia_0005"
    op.execute(f"CREATE TABLE {copia} AS SELECT * FROM {tabla}")
    op.drop_table(tabla)
    crear()
    op.execute(f"INSERT INTO {tabla} ({columnas}) SELECT {seleccion or columnas} FROM {copia}")
    op.drop_table(copia)


def _caso(columna: int) -> str:
    # Valores fijos de esta migración, no del usuario: se pueden escribir en el SQL.
    ramas = " ".join(f"WHEN '{fila[0]}' THEN '{fila[columna]}'" for fila in CATEGORIAS_INICIALES)
    return f"CASE nombre {ramas} ELSE '{POR_DEFECTO[columna - 1]}' END"


def upgrade() -> None:
    conexion = op.get_bind()
    _rehacer(
        "categorias",
        _crear_categorias_0005,
        "id, nombre, clase, color, icono",
        f"id, nombre, {_caso(1)}, {_caso(2)}, {_caso(3)}",
    )
    for nombre, clase, color, icono in CATEGORIAS_INICIALES:
        if nombre in NUEVAS:
            conexion.execute(
                sa.text(
                    "INSERT INTO categorias (nombre, clase, color, icono) "
                    "SELECT :nombre, :clase, :color, :icono WHERE NOT EXISTS "
                    "(SELECT 1 FROM categorias WHERE nombre = :nombre AND clase = :clase)"
                ),
                {"nombre": nombre, "clase": clase, "color": color, "icono": icono},
            )
    _rehacer(
        "reglas",
        lambda: _crear_reglas("'comercio', 'cuenta_destino', 'quien_envia'"),
        "id, campo, texto, categoria_id",
    )
    mezclados = conexion.execute(
        sa.text(
            "SELECT COUNT(*) FROM movimientos m JOIN categorias c ON c.id = m.categoria_id "
            "WHERE (m.tipo IN ('compra', 'transferencia') AND c.clase <> 'gasto') "
            "OR (m.tipo = 'ingreso' AND c.clase <> 'ingreso')"
        )
    ).scalar_one()
    if mezclados:
        # La excepción deshace toda la transacción (también lo de arriba).
        raise CommandError(MENSAJE_CLASE_MEZCLADA)


def downgrade() -> None:
    conexion = op.get_bind()
    if conexion.execute(sa.text("SELECT COUNT(*) FROM reglas WHERE campo = 'quien_envia'")).scalar_one():
        raise CommandError(MENSAJE_NO_SE_PUEDE_BAJAR.format(motivo="hay reglas de ingreso"))
    iniciales = set(CATEGORIAS_INICIALES)
    filas = conexion.execute(sa.text("SELECT nombre, clase, color, icono FROM categorias")).all()
    if any(tuple(fila) not in iniciales for fila in filas):
        raise CommandError(
            MENSAJE_NO_SE_PUEDE_BAJAR.format(
                motivo="hay categorías creadas o cambiadas desde la app (la 0004 no guarda clase, color ni ícono)"
            )
        )
    _rehacer("reglas", lambda: _crear_reglas("'comercio', 'cuenta_destino'"), "id, campo, texto, categoria_id")
    _rehacer("categorias", _crear_categorias_0004, "id, nombre")
