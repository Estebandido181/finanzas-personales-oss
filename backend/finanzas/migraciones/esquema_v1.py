"""Estructura de la v1, congelada, y comparación con una base existente.

La base de producción la creó ``db.inicializar`` de la v1 con este mismo
texto (``CREATE TABLE IF NOT EXISTS``), sin tabla ``alembic_version``.
``python -m finanzas.migrar`` la marca como revisión ``0001`` **solo** si su
estructura coincide con esta; si no, se detiene sin tocar nada.

``ESQUEMA_V1`` no se modifica nunca: es la foto de lo que había. Las
pruebas lo usan para crear bases "de la v1" con datos inventados.

La comparación es estructural (no de texto): columnas con tipo, NOT NULL,
DEFAULT y clave primaria; índices con sus columnas y si son únicos; claves
foráneas; y las cláusulas CHECK con los espacios normalizados. Así una base
creada por la migración 0001 (que escribe el SQL con otro formato) y una
creada por la v1 se reconocen como iguales, y cualquier diferencia real
(una columna, un índice, un CHECK de más o de menos) no.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

ESQUEMA_V1 = """
CREATE TABLE IF NOT EXISTS categorias (
    id     INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS movimientos (
    id             INTEGER PRIMARY KEY,
    fecha_hora     TEXT NOT NULL,             -- ISO 8601, p. ej. 2026-08-07T16:42:00
    monto_centavos INTEGER NOT NULL CHECK (typeof(monto_centavos) = 'integer'),
    tipo           TEXT NOT NULL
                   CHECK (tipo IN ('compra', 'transferencia', 'ingreso', 'ajuste')),
    descripcion    TEXT NOT NULL DEFAULT '',  -- comercio o cuenta destino
    categoria_id   INTEGER REFERENCES categorias(id),
    origen         TEXT NOT NULL CHECK (origen IN ('gmail', 'manual')),
    gmail_id       TEXT UNIQUE,               -- NULL en los movimientos manuales
    registrado_en  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    CHECK (
        (tipo = 'ajuste' AND monto_centavos <> 0)
        OR (tipo <> 'ajuste' AND monto_centavos > 0)
    ),
    CHECK ((origen = 'gmail') = (gmail_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_movimientos_fecha_hora ON movimientos (fecha_hora);

CREATE TABLE IF NOT EXISTS reglas (
    id           INTEGER PRIMARY KEY,
    campo        TEXT NOT NULL CHECK (campo IN ('comercio', 'cuenta_destino')),
    texto        TEXT NOT NULL CHECK (texto <> ''),
    categoria_id INTEGER NOT NULL REFERENCES categorias(id),
    UNIQUE (campo, texto)
);

CREATE TABLE IF NOT EXISTS configuracion_saldo (
    id                     INTEGER PRIMARY KEY CHECK (id = 1),
    saldo_inicial_centavos INTEGER NOT NULL
                           CHECK (typeof(saldo_inicial_centavos) = 'integer'),
    fecha_inicio           TEXT NOT NULL      -- ISO 8601 (fecha)
);

-- Solo metadatos para revisar formatos nuevos. Nunca se guarda el cuerpo.
CREATE TABLE IF NOT EXISTS correos_no_reconocidos (
    gmail_id TEXT PRIMARY KEY,
    fecha    TEXT,
    asunto   TEXT
);
"""

# Tablas que no son de la app y no cuentan al comparar.
_TABLAS_IGNORADAS = {"alembic_version"}


def _sin_comentarios(sql: str) -> str:
    """Quita los comentarios ``-- ...`` (fuera de los textos entre comillas)."""
    salida = []
    en_texto = False
    i = 0
    while i < len(sql):
        c = sql[i]
        if c == "'":
            en_texto = not en_texto
        elif not en_texto and sql.startswith("--", i):
            fin = sql.find("\n", i)
            i = len(sql) if fin == -1 else fin
            continue
        salida.append(c)
        i += 1
    return "".join(salida)


def _normalizar(expresion: str) -> str:
    """Espacios colapsados, sin espacios pegados a los paréntesis."""
    expresion = " ".join(expresion.split())
    expresion = re.sub(r"\(\s+", "(", expresion)
    return re.sub(r"\s+\)", ")", expresion)


def _checks(sql: str | None) -> list[str]:
    """Las expresiones de todos los ``CHECK (...)`` de un ``CREATE TABLE``, normalizadas."""
    if not sql:
        return []
    sql = _sin_comentarios(sql)
    encontrados = []
    for inicio in re.finditer(r"\bCHECK\s*\(", sql, flags=re.IGNORECASE):
        profundidad = 0
        en_texto = False
        for j in range(inicio.end() - 1, len(sql)):
            c = sql[j]
            if c == "'":
                en_texto = not en_texto
            elif not en_texto and c == "(":
                profundidad += 1
            elif not en_texto and c == ")":
                profundidad -= 1
                if profundidad == 0:
                    encontrados.append(_normalizar(sql[inicio.end():j]))
                    break
    return sorted(encontrados)


def _default(valor: Any) -> Any:
    if valor is None:
        return None
    valor = _normalizar(str(valor))
    # "(expr)" y "expr" son el mismo DEFAULT.
    while valor.startswith("(") and valor.endswith(")"):
        valor = valor[1:-1].strip()
    return valor


def describir(conn: sqlite3.Connection) -> dict[str, Any]:
    """Descripción estructural de las tablas de la app en una base SQLite."""
    tablas = {}
    filas = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\' ORDER BY name"
    ).fetchall()
    for nombre, sql in filas:
        if nombre in _TABLAS_IGNORADAS:
            continue
        columnas = [
            (f[1], str(f[2]).upper(), f[3], _default(f[4]), f[5], f[6])
            for f in conn.execute(f'PRAGMA table_xinfo("{nombre}")')
        ]
        indices = []
        for f in conn.execute(f'PRAGMA index_list("{nombre}")'):
            nombre_indice, unico, origen, parcial = f[1], f[2], f[3], f[4]
            columnas_indice = tuple(
                c[2] for c in conn.execute(f'PRAGMA index_info("{nombre_indice}")')
            )
            # Los automáticos (UNIQUE, PRIMARY KEY) se llaman sqlite_autoindex_*:
            # solo cuenta el nombre de los creados con CREATE INDEX.
            indices.append(
                (nombre_indice if origen == "c" else None, unico, origen, parcial, columnas_indice)
            )
        foraneas = sorted(
            (f[2], f[3], f[4], f[5], f[6], f[7])
            for f in conn.execute(f'PRAGMA foreign_key_list("{nombre}")')
        )
        tablas[nombre] = {
            "columnas": columnas,
            "indices": sorted(indices, key=repr),
            "foraneas": foraneas,
            "checks": _checks(sql),
        }
    return tablas


def describir_v1() -> dict[str, Any]:
    """La descripción de una base recién creada con ``ESQUEMA_V1``."""
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(ESQUEMA_V1)
        return describir(conn)
    finally:
        conn.close()


def diferencias_con_v1(conn: sqlite3.Connection) -> list[str]:
    """Qué tablas difieren de la v1 (solo nombres de tablas, nunca datos). Vacía si coincide."""
    actual = describir(conn)
    esperado = describir_v1()
    diferencias = []
    for nombre in sorted(set(actual) | set(esperado)):
        if nombre not in actual:
            diferencias.append(f"falta la tabla {nombre}")
        elif nombre not in esperado:
            diferencias.append(f"tabla inesperada {nombre}")
        elif actual[nombre] != esperado[nombre]:
            partes = [k for k in esperado[nombre] if actual[nombre][k] != esperado[nombre][k]]
            diferencias.append(f"tabla {nombre}: difiere en {', '.join(partes)}")
    # La v1 no tenía vistas ni disparadores.
    for tipo, nombre in conn.execute(
        "SELECT type, name FROM sqlite_master WHERE type IN ('view', 'trigger') ORDER BY name"
    ):
        diferencias.append(f"{'vista' if tipo == 'view' else 'disparador'} inesperado {nombre}")
    return diferencias
