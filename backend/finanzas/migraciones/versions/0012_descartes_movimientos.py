"""Descarte reversible de automáticos; respaldo previo obligatorio."""
from alembic import op
from alembic.util import CommandError
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _solo_sqlite(texto):
    return sa.CheckConstraint(texto).ddl_if(dialect="sqlite")


def upgrade():
    # SQLite admite FK y CHECK inline al añadir una columna; Alembic
    # intentaría crear la FK por ALTER TABLE separado, que SQLite no admite.
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE preguntas_conciliacion ADD COLUMN ocurrencia_banco INTEGER "
                   "CHECK(ocurrencia_banco IS NULL OR ocurrencia_banco > 0) "
                   "CHECK(ocurrencia_banco IS NULL OR typeof(ocurrencia_banco) = 'integer')")
        op.execute("ALTER TABLE preguntas_conciliacion ADD COLUMN movimiento_elegido_id INTEGER "
                   "CONSTRAINT fk_pregunta_movimiento_elegido REFERENCES movimientos(id) "
                   "CHECK(movimiento_elegido_id IS NULL OR (fuente = 'banco' AND respuesta IS NOT NULL AND ocurrencia_banco IS NOT NULL))")
    else:
        op.add_column("preguntas_conciliacion", sa.Column("ocurrencia_banco", sa.Integer(),
            sa.CheckConstraint("ocurrencia_banco IS NULL OR ocurrencia_banco > 0")))
        op.add_column("preguntas_conciliacion", sa.Column("movimiento_elegido_id", sa.Integer(),
            sa.ForeignKey("movimientos.id", name="fk_pregunta_movimiento_elegido"),
            sa.CheckConstraint("movimiento_elegido_id IS NULL OR (fuente = 'banco' AND respuesta IS NOT NULL AND ocurrencia_banco IS NOT NULL)")))
    op.create_table(
        "descartes_movimientos",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=True),
        sa.Column("movimiento_id", sa.Integer(), sa.ForeignKey("movimientos.id"), nullable=False),
        sa.Column("descartado_en", sa.Text(), nullable=False),
        sa.Column("restaurado_en", sa.Text()),
        sa.Column("fecha", sa.Text(), nullable=False),
        sa.Column("monto_centavos", sa.Integer(), nullable=False),
        sa.Column("referencia", sa.Text()),
        sa.Column("fecha_banco", sa.Text()),
        sa.Column("monto_banco_centavos", sa.Integer()),
        sa.Column("referencia_banco", sa.Text()),
        sa.Column("huella_movimiento", sa.Text(), nullable=False),
        sa.Column("huella_contexto", sa.Text(), nullable=False),
        _solo_sqlite("referencia IS NULL OR referencia GLOB '[*][0-9][0-9][0-9][0-9]'"),
        _solo_sqlite("referencia_banco IS NULL OR referencia_banco GLOB '[*][0-9][0-9][0-9][0-9]'"),
        _solo_sqlite("typeof(monto_centavos) = 'integer'"),
        sa.CheckConstraint("monto_centavos <> 0"),
        _solo_sqlite("monto_banco_centavos IS NULL OR typeof(monto_banco_centavos) = 'integer'"),
        sa.CheckConstraint("monto_banco_centavos IS NULL OR monto_banco_centavos <> 0"),
        sa.CheckConstraint("(fecha_banco IS NULL) = (monto_banco_centavos IS NULL)"),
        sa.CheckConstraint("fecha_banco IS NOT NULL OR referencia_banco IS NULL"),
    )
    op.create_index("un_descarte_activo_por_movimiento", "descartes_movimientos",
                    ["movimiento_id"], unique=True, sqlite_where=sa.text("restaurado_en IS NULL"),
                    postgresql_where=sa.text("restaurado_en IS NULL"))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM descartes_movimientos LIMIT 1")).first():
        raise CommandError("Hay historial de descartes: restaura el respaldo previo; no se perderá el rastro.")
    if op.get_bind().execute(sa.text("SELECT 1 FROM preguntas_conciliacion "
            "WHERE movimiento_elegido_id IS NOT NULL OR ocurrencia_banco IS NOT NULL LIMIT 1")).first():
        raise CommandError("Hay decisiones bancarias por ocurrencia: restaura el respaldo previo; no se perderá el rastro.")
    op.drop_column("preguntas_conciliacion", "movimiento_elegido_id")
    op.drop_column("preguntas_conciliacion", "ocurrencia_banco")
    op.drop_table("descartes_movimientos")
