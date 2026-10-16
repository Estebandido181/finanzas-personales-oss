"""Migraciones de Alembic (ítem 22, D19).

* ``env.py``: cómo corre Alembic (sobre la conexión que le pasa
  ``finanzas.migrar``, o desde ``DB_PATH`` con el comando ``alembic``).
* ``versions/``: una migración por cambio de estructura, en orden.
* ``esquema_v1.py``: la estructura de la v1, congelada, para reconocer la
  base de producción creada antes de las migraciones.

Para aplicarlas: ``python -m finanzas.migrar`` (ver el README y
``deploy/GUIA.md``).
"""
