"""Categorías de gasto "Retiro a efectivo" y "Pago de tarjeta".

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-01

Ítem 27 (D30). Los retiros en cajero ("Retiraste") se leen como gasto con la
categoría "Retiro a efectivo", asignada al leerlos, y los pagos de tarjeta de
crédito por PSE van en "Pago de tarjeta". Ninguna de las dos estaba entre las
iniciales de la 0005.

Ojo: la rama del ítem 17 (reglas con condiciones) también trae una 0006. Esta
se escribió aparte y el team leader renumera la que se integre después.

``upgrade``, con las mismas reglas que la app al crear una categoría
(``categorizacion._comprobar_unica``):

* el nombre se compara como en la app: sin distinguir mayúsculas, con los
  espacios colapsados, sin invisibles de formato y en Unicode NFC
  (``_clave_nombre``, copia de ``categorizacion.normalizar``). Si ya hay una
  categoría **de gasto** con un nombre equivalente (por ejemplo, "retiro a
  efectivo" creada por el dueño), no se crea otra ni se toca la que hay: la
  sincronización la encuentra con la misma comparación;
* el par color + ícono no puede repetir uno que ya use otra categoría. Se
  intenta primero el preferido y, si está ocupado, el primer par libre en el
  orden fijo de ``_CANDIDATOS`` (paleta e íconos de SISTEMA.md, "Categorías
  nuevas"). Si no quedara ninguno libre (no puede pasar con 144 pares y
  menos categorías), la migración se detiene sin cambiar nada.

Preferidos:

* "Retiro a efectivo": verde azulado (``cat-vivienda``) con ``coins``;
* "Pago de tarjeta": índigo desteñido (``cat-prestamos``) con ``coins``. La
  lista corta no tiene un ícono de tarjeta; si el diseño lo agrega, el dueño
  la puede cambiar desde la app.

No cambia ningún movimiento ni ninguna regla: los retiros ya guardados como
no reconocidos se leen al reprocesarlos (ítem 19).

``downgrade``: borra las categorías de gasto con exactamente esos dos nombres
**solo si ninguna está en uso**; si algún movimiento o alguna regla usa
cualquiera de las dos, se niega (``CommandError``) sin tocar nada y hay que
restaurar el respaldo previo a la migración (D26). Consecuencia aceptada: si
el dueño ya tenía antes de la 0006 una categoría con ese nombre exacto y nunca
la usó, bajar también la quita (está vacía y se puede volver a crear).

Como toda migración, está escrita sin depender de ``finanzas.db``.
"""
import unicodedata
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from alembic.util import CommandError

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (nombre, clase, color, ícono preferidos) de las categorías que añade esta migración.
NUEVAS = (
    ("Retiro a efectivo", "gasto", "cat-vivienda", "coins"),
    ("Pago de tarjeta", "gasto", "cat-prestamos", "coins"),
)
# Paleta e íconos de la 0005 / SISTEMA.md (``categorizacion.COLORES_CATEGORIA``
# e ``ICONOS_CATEGORIA``), copiados para no depender del código de la app.
_COLORES = (
    "cat-mercado", "cat-restaurantes", "cat-transporte", "cat-vivienda", "cat-salud", "cat-entretenimiento",
    "cat-compras", "cat-antojos", "cat-otros", "cat-sueldo", "cat-prestamos", "cat-otros-ingresos",
)
_ICONOS = (
    "shopping-basket", "utensils", "bus", "house", "heart-pulse", "ticket", "shopping-bag", "ice-cream-cone",
    "shapes", "briefcase", "handshake", "coins",
)
# Orden fijo de los pares de respaldo: primero ``coins`` con cada color, luego el resto.
_CANDIDATOS = tuple((c, "coins") for c in _COLORES) + tuple(
    (c, i) for i in _ICONOS if i != "coins" for c in _COLORES
)

MENSAJE_SIN_PAR = "No queda ningún par color + ícono libre para \"{nombre}\". No se cambió nada."
MENSAJE_NO_SE_PUEDE_BAJAR = (
    "No se puede volver a la revisión 0005 sin perder datos: {motivo}. No se cambió nada. "
    "Restaura el respaldo previo a la migración (deploy/GUIA.md)."
)
_INVISIBLES_EXTRA = frozenset("͏᠎")


def _clave_nombre(texto: str) -> str:
    """Como ``categorizacion.normalizar``: sin invisibles, NFC, casefold y espacios colapsados."""
    visible = "".join(c for c in texto if unicodedata.category(c) != "Cf" and c not in _INVISIBLES_EXTRA)
    return " ".join(unicodedata.normalize("NFC", visible).casefold().split())


def upgrade() -> None:
    conexion = op.get_bind()
    for nombre, clase, color, icono in NUEVAS:
        filas = conexion.execute(sa.text("SELECT nombre, clase, color, icono FROM categorias")).all()
        if any(f[1] == clase and _clave_nombre(f[0]) == _clave_nombre(nombre) for f in filas):
            continue  # ya existe una equivalente: no se duplica ni se cambia
        usados = {(f[2], f[3]) for f in filas}
        par = next((p for p in ((color, icono), *_CANDIDATOS) if p not in usados), None)
        if par is None:  # pragma: no cover - imposible con la paleta actual
            raise CommandError(MENSAJE_SIN_PAR.format(nombre=nombre))
        conexion.execute(
            sa.text("INSERT INTO categorias (nombre, clase, color, icono) VALUES (:nombre, :clase, :color, :icono)"),
            {"nombre": nombre, "clase": clase, "color": par[0], "icono": par[1]},
        )


def downgrade() -> None:
    conexion = op.get_bind()
    ids = [
        int(fila[0])
        for nombre, clase, _, _ in NUEVAS
        for fila in conexion.execute(
            sa.text("SELECT id FROM categorias WHERE nombre = :nombre AND clase = :clase"),
            {"nombre": nombre, "clase": clase},
        ).all()
    ]
    for categoria_id in ids:
        en_uso = conexion.execute(
            sa.text(
                "SELECT (SELECT COUNT(*) FROM movimientos WHERE categoria_id = :id) "
                "+ (SELECT COUNT(*) FROM reglas WHERE categoria_id = :id)"
            ),
            {"id": categoria_id},
        ).scalar_one()
        if en_uso:
            raise CommandError(
                MENSAJE_NO_SE_PUEDE_BAJAR.format(
                    motivo="hay movimientos o reglas con \"Retiro a efectivo\" o \"Pago de tarjeta\""
                )
            )
    # Solo se llega aquí si ninguna está en uso: se borran juntas.
    for categoria_id in ids:
        conexion.execute(sa.text("DELETE FROM categorias WHERE id = :id"), {"id": categoria_id})
