"""Cómo corre Alembic en este proyecto.

Normalmente la conexión la abre ``finanzas.migrar`` (con el respaldo previo
y la transacción ya abierta) y llega en ``config.attributes["connection"]``.
Si se usa el comando ``alembic`` directamente (p. ej. ``alembic check`` o
``alembic revision --autogenerate`` en desarrollo), se abre la base de
``DB_PATH``. No hay modo "offline" (generar SQL sin base).

Toda la migración ocurre en **una sola transacción**: o se aplica entera o
no cambia nada. SQLite admite cambios de estructura dentro de una
transacción. Claves foráneas: la conexión de ``migrar`` las apaga (no se
pueden apagar dentro de una transacción) para poder reconstruir tablas,
como pide SQLite; al terminar, ``PRAGMA foreign_key_check`` compara las
claves rotas con las de antes de empezar y, si la migración dejó alguna
nueva, lanza un error y no se confirma nada. Las que ya estaban (filas
escritas alguna vez con las claves apagadas) se dejan tal cual: migrar no
"arregla" datos. Si la conexión llega con las claves encendidas (otro
llamador), ``PRAGMA defer_foreign_keys`` las comprueba al confirmar.
"""

from __future__ import annotations

import os

from alembic import context

from finanzas import db, migrar

config = context.config


def _correr(conexion) -> None:
    context.configure(
        connection=conexion,
        target_metadata=db.metadata,
        render_as_batch=True,  # en SQLite, ALTER TABLE se hace recreando la tabla
        transactional_ddl=True,
    )
    sqlite = conexion.dialect.name == "sqlite"
    if sqlite:
        conexion.exec_driver_sql("PRAGMA defer_foreign_keys = ON")
        rotas_antes = _claves_rotas(conexion)
    with context.begin_transaction():
        context.run_migrations()
        if sqlite and _claves_rotas(conexion) - rotas_antes:
            raise RuntimeError("La migración dejaría claves foráneas rotas; no se aplicó nada.")


def _claves_rotas(conexion) -> set[tuple]:
    """(tabla, rowid, tabla padre) de cada clave foránea rota.

    Sin el número de la clave: al reconstruir una tabla puede cambiar.
    """
    # Único caso que esta comparación no ve: una clave rota NUEVA que coincida
    # en (tabla, rowid, tabla padre) con una que ya estaba rota antes de
    # migrar cuenta como "ya estaba". Pasa si la migración cambia una clave ya
    # rota por otro valor también roto, o rompe otra columna de esa misma fila
    # que apunte a la misma tabla padre (hoy ninguna tabla tiene dos claves
    # hacia la misma tabla padre).
    return {tuple(f[:3]) for f in conexion.exec_driver_sql("PRAGMA foreign_key_check").fetchall()}


if context.is_offline_mode():
    raise SystemExit("Este proyecto no genera migraciones en modo offline.")

conexion_recibida = config.attributes.get("connection")
if conexion_recibida is not None:
    _correr(conexion_recibida)
else:
    ruta = os.environ.get("DB_PATH", "").strip() or "finanzas.db"
    with migrar.conectar_para_migrar(ruta) as conexion, conexion.begin():
        _correr(conexion)
