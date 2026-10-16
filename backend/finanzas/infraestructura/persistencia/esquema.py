"""Descripción única del esquema; revisiones aplicadas no se modifican."""
from sqlalchemy import (CheckConstraint, Column, ForeignKey, Index, Integer,
    MetaData, Table, Text, UniqueConstraint, text)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement

# Las 8 categorías fijas de la v1 (todas de gasto), con sus ids de entonces (1 a 8).
CATEGORIAS_FIJAS = (
    "Mercado",
    "Restaurantes",
    "Transporte",
    "Vivienda y servicios",
    "Salud",
    "Entretenimiento",
    "Compras",
    "Otros",
)

# Ítem 15: las clases de categoría y las categorías con que arranca la app
# (migraciones 0005 y 0006): las 8 de la v1 más "Antojos", "Sueldo", "Préstamos",
# "Otros ingresos", "Retiro a efectivo" y "Pago de tarjeta". (nombre, clase,
# color, ícono): ``color`` es la clave de un
# token de ``frontend/diseno/tokens.css`` (``cat-mercado`` es ``--cat-mercado``)
# e ``icono`` el nombre de un ícono de Lucide (SISTEMA.md, "Categorías: color
# e ícono"). Desde aquí el dueño las crea, renombra y borra.
CLASE_GASTO = "gasto"
CLASE_INGRESO = "ingreso"
CLASES_CATEGORIA = (CLASE_GASTO, CLASE_INGRESO)
CATEGORIAS_INICIALES = (
    ("Mercado", CLASE_GASTO, "cat-mercado", "shopping-basket"),
    ("Restaurantes", CLASE_GASTO, "cat-restaurantes", "utensils"),
    ("Transporte", CLASE_GASTO, "cat-transporte", "bus"),
    ("Vivienda y servicios", CLASE_GASTO, "cat-vivienda", "house"),
    ("Salud", CLASE_GASTO, "cat-salud", "heart-pulse"),
    ("Entretenimiento", CLASE_GASTO, "cat-entretenimiento", "ticket"),
    ("Compras", CLASE_GASTO, "cat-compras", "shopping-bag"),
    ("Antojos", CLASE_GASTO, "cat-antojos", "ice-cream-cone"),
    ("Otros", CLASE_GASTO, "cat-otros", "shapes"),
    # Ítem 27 (D30), migración 0006.
    ("Retiro a efectivo", CLASE_GASTO, "cat-vivienda", "coins"),
    ("Pago de tarjeta", CLASE_GASTO, "cat-prestamos", "coins"),
    ("Sueldo", CLASE_INGRESO, "cat-sueldo", "briefcase"),
    ("Préstamos", CLASE_INGRESO, "cat-prestamos", "handshake"),
    ("Otros ingresos", CLASE_INGRESO, "cat-otros-ingresos", "coins"),
)

# --- Estructura -------------------------------------------------------------------

class AhoraIso(FunctionElement):
    """Fecha y hora actual en UTC como texto ISO 8601 (``2026-08-07T16:42:00``)."""

    type = Text()
    inherit_cache = True


@compiles(AhoraIso, "sqlite")
def _ahora_iso_sqlite(elemento, compilador, **kw) -> str:
    return "strftime('%Y-%m-%dT%H:%M:%S', 'now')"


@compiles(AhoraIso, "postgresql")
def _ahora_iso_postgresql(elemento, compilador, **kw) -> str:
    return "to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS')"


def _solo_sqlite(restriccion: CheckConstraint) -> CheckConstraint:
    return restriccion.ddl_if(dialect="sqlite")


# Migración 0008: un destino es "*" + exactamente 4 dígitos (D37), nunca un
# número completo; las fechas del banco, AAAA-MM-DD. GLOB es de SQLite.
REFERENCIA_VALIDA = "referencia IS NULL OR referencia GLOB '[*][0-9][0-9][0-9][0-9]'"


def _fecha_valida(columna: str) -> str:
    return f"{columna} IS NULL OR {columna} GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'"


def _entero_no_negativo(nombre: str) -> Column:
    return Column(
        nombre,
        Integer,
        _solo_sqlite(CheckConstraint(f"typeof({nombre}) = 'integer'")),
        CheckConstraint(f"{nombre} >= 0"),
        nullable=False,
        server_default="0",
    )


# Notas sobre la estructura (igual que en la v1):
# - ``id`` con ``nullable=True``: así SQLite recibe ``id INTEGER`` + ``PRIMARY
#   KEY (id)`` sin NOT NULL, exactamente como el ``INTEGER PRIMARY KEY`` de la
#   v1 (en SQLite es el alias del ``rowid`` y nunca es NULL).
# - CHECK de ``movimientos.monto_centavos``: compra, transferencia e ingreso
#   guardan el monto en positivo (> 0); el signo lo da el tipo al calcular el
#   saldo. Ajuste guarda la diferencia con signo (saldo real - saldo
#   calculado, D9) y nunca 0.
# - ``typeof(...) = 'integer'``: con la afinidad INTEGER de SQLite, '100' o
#   12.0 se convierten a entero, pero 12.5 o 'abc' se guardarían tal cual; el
#   CHECK los rechaza.
# - ``origen`` y ``gmail_id``: los de Gmail siempre llevan id (el UNIQUE evita
#   duplicados; dos NULL no chocan en un UNIQUE) y los manuales nunca.
metadata = MetaData()

# Migración 0005 (ítem 15): clase, color e ícono; el nombre es único por clase.
categorias = Table(
    "categorias",
    metadata,
    Column("id", Integer, primary_key=True, nullable=True),
    Column("nombre", Text, CheckConstraint("nombre <> ''"), nullable=False),
    Column("clase", Text, CheckConstraint("clase IN ('gasto', 'ingreso')"), nullable=False),
    Column("color", Text, CheckConstraint("color <> ''"), nullable=False),  # clave de token
    Column("icono", Text, CheckConstraint("icono <> ''"), nullable=False),  # ícono de Lucide
    UniqueConstraint("nombre", "clase"),
)

movimientos = Table(
    "movimientos",
    metadata,
    Column("id", Integer, primary_key=True, nullable=True),
    Column("fecha_hora", Text, nullable=False),  # ISO 8601, p. ej. 2026-08-07T16:42:00
    Column(
        "monto_centavos",
        Integer,
        _solo_sqlite(CheckConstraint("typeof(monto_centavos) = 'integer'")),
        nullable=False,
    ),
    Column(
        "tipo",
        Text,
        CheckConstraint("tipo IN ('compra', 'transferencia', 'ingreso', 'ajuste')"),
        nullable=False,
    ),
    Column("descripcion", Text, nullable=False, server_default=""),  # comercio o cuenta destino
    Column("categoria_id", Integer, ForeignKey("categorias.id")),
    Column(
        "origen", Text, CheckConstraint("origen IN ('gmail', 'manual', 'extracto')"), nullable=False
    ),
    # NULL en los manuales; en los del banco (``extracto``), el del aviso que
    # llegó después, si llegó (D45).
    Column("gmail_id", Text, unique=True),
    Column("registrado_en", Text, nullable=False, server_default=AhoraIso()),
    # Migración 0004 (ítem 14): cómo se categorizó. "manual", "regla" o NULL
    # (sin categoría o, si tiene, "desconocido": categorizado antes de la
    # 0004). ``regla_id``: la regla que lo categorizó; al borrarla,
    # ``categorizacion.borrar_regla`` lo deja en NULL y el origen sigue siendo
    # "regla" (la clave foránea impide borrar una regla sin hacerlo). Van al
    # final, como las añade ADD COLUMN.
    Column("origen_categoria", Text, CheckConstraint("origen_categoria IN ('manual', 'regla')")),
    Column("regla_id", Integer, ForeignKey("reglas.id")),
    # Migración 0008 (ítem 29, conciliación con el banco; ver
    # ``finanzas.conciliacion``):
    # - ``estado``: "confirmado" (lo respalda el banco), "provisional"
    #   (ingreso manual sin respaldo, D39) o "sin_aviso" (vino del banco y no
    #   del correo). NULL: lo del correo aún sin conciliar y los ajustes (D45);
    # - ``referencia``: destino que trajo el banco, solo "*" + 4 dígitos (D37);
    # - ``fecha_banco``: día de la fila del banco que lo respalda;
    # - ``no_en_banco``: 1 si es del correo y el banco no lo trajo (D38).
    Column("estado", Text, CheckConstraint("estado IN ('confirmado', 'provisional', 'sin_aviso')")),
    Column("referencia", Text, _solo_sqlite(CheckConstraint(REFERENCIA_VALIDA))),
    Column("fecha_banco", Text, _solo_sqlite(CheckConstraint(_fecha_valida("fecha_banco")))),
    Column(
        "no_en_banco",
        Integer,
        CheckConstraint("no_en_banco IN (0, 1)"),
        nullable=False,
        server_default="0",
    ),
    # Compra, transferencia e ingreso, siempre > 0. Un ajuste puede quedar en
    # 0 cuando lo importado del banco lo reduce del todo (D45).
    CheckConstraint("tipo = 'ajuste' OR monto_centavos > 0"),
    CheckConstraint(
        "(origen = 'gmail' AND gmail_id IS NOT NULL) OR (origen = 'manual' AND gmail_id IS NULL) "
        "OR origen = 'extracto'"
    ),
    CheckConstraint("regla_id IS NULL OR COALESCE(origen_categoria, '') = 'regla'"),
    CheckConstraint(
        "CASE origen "
        "WHEN 'extracto' THEN COALESCE(estado, '') IN ('confirmado', 'sin_aviso') "
        "WHEN 'manual' THEN (tipo = 'ajuste' AND estado IS NULL) "
        "OR (tipo <> 'ajuste' AND COALESCE(estado, 'provisional') IN ('provisional', 'confirmado')) "
        "ELSE estado IS NULL OR estado = 'confirmado' END"
    ),
    CheckConstraint("(fecha_banco IS NOT NULL) = (COALESCE(estado, '') IN ('confirmado', 'sin_aviso'))"),
    Column("borrado_en", Text),
    Column("revisado_no_en_banco", Integer, CheckConstraint("revisado_no_en_banco IN (0, 1)"), nullable=False, server_default="0"),
    CheckConstraint("no_en_banco = 0 OR (origen = 'gmail' AND estado IS NULL)"),
    CheckConstraint("referencia IS NULL OR fecha_banco IS NOT NULL"),
)
Index("idx_movimientos_fecha_hora", movimientos.c.fecha_hora)

reglas = Table(
    "reglas",
    metadata,
    Column("id", Integer, primary_key=True, nullable=True),
    Column(
        "campo",
        Text,
        # quien_envia: reglas de ingresos (migración 0005, ítem 15).
        CheckConstraint("campo IN ('comercio', 'cuenta_destino', 'quien_envia')"),
        nullable=False,
    ),
    # Migración 0006 (ítem 17): condiciones combinables. ``texto`` (comercio,
    # cuenta destino o quien envía) y ``monto_centavos`` (monto exacto) son
    # opcionales, pero siempre hay al menos uno además del tipo (``campo``).
    Column("texto", Text, CheckConstraint("texto IS NULL OR texto <> ''")),
    Column("categoria_id", Integer, ForeignKey("categorias.id"), nullable=False),
    Column(
        "monto_centavos",
        Integer,
        _solo_sqlite(CheckConstraint("monto_centavos IS NULL OR typeof(monto_centavos) = 'integer'")),
        CheckConstraint("monto_centavos IS NULL OR monto_centavos > 0"),
    ),
    CheckConstraint("texto IS NOT NULL OR monto_centavos IS NOT NULL"),
    Column("modo_texto", Text, CheckConstraint("modo_texto IN ('exacta', 'contiene', 'empieza_por')"), nullable=False, server_default="exacta"),
    Column("origen_regla", Text, CheckConstraint("origen_regla IN ('todos', 'extracto')"), nullable=False, server_default="todos"),
    Column("texto_visible", Text),  # Solo presentación; texto sigue normalizado para comparar.
)
# Una sola regla por combinación de condiciones. Con ``COALESCE`` porque en un
# UNIQUE dos NULL no chocan ("transferencia + $3.200" podría repetirse). ``''``
# y ``0`` no son valores posibles (los CHECK los rechazan).
Index(
    "ux_reglas_condiciones",
    reglas.c.campo,
    text("COALESCE(texto, '')"),
    text("COALESCE(monto_centavos, 0)"),
    reglas.c.modo_texto,
    reglas.c.origen_regla,
    unique=True,
)

configuracion_saldo = Table(
    "configuracion_saldo",
    metadata,
    Column("id", Integer, CheckConstraint("id = 1"), primary_key=True, nullable=True),
    Column(
        "saldo_inicial_centavos",
        Integer,
        _solo_sqlite(CheckConstraint("typeof(saldo_inicial_centavos) = 'integer'")),
        nullable=False,
    ),
    Column("fecha_inicio", Text, nullable=False),  # ISO 8601 (fecha)
)

# Solo metadatos para revisar formatos nuevos. Nunca se guarda el cuerpo.
correos_no_reconocidos = Table(
    "correos_no_reconocidos",
    metadata,
    Column("gmail_id", Text, primary_key=True, nullable=True),
    Column("fecha", Text),
    Column("asunto", Text),
)

# Resultado de la última sincronización (migración 0002, ítem 10). Una sola
# fila (id = 1) que se reemplaza en cada sincronización, lanzada desde el
# botón o desde el temporizador. Sin datos de correos: solo la hora, el
# estado, los contadores y un código de error de una lista cerrada.
ESTADOS_SINCRONIZACION = ("ok", "con_errores", "fallida")
ORIGENES_SINCRONIZACION = ("web", "comando")
CODIGOS_ERROR_SINCRONIZACION = (
    "sin_fecha_inicio",
    "gmail_no_configurado",
    "autorizacion_gmail",
    "error_inesperado",
)
CONTADORES_SINCRONIZACION = (
    "nuevos",
    "duplicados",
    "no_reconocidos",
    "errores",
    "rechazados_autenticacion",
)


def _contador(nombre: str) -> Column:
    # NULL cuando la sincronización falló antes de terminar (no hay contadores).
    return Column(
        nombre,
        Integer,
        _solo_sqlite(CheckConstraint(f"{nombre} IS NULL OR typeof({nombre}) = 'integer'")),
        CheckConstraint(f"{nombre} IS NULL OR {nombre} >= 0"),
    )


estado_sincronizacion = Table(
    "estado_sincronizacion",
    metadata,
    Column("id", Integer, CheckConstraint("id = 1"), primary_key=True, nullable=True),
    Column("terminada_en", Text, nullable=False),  # hora de Colombia, ISO 8601 sin zona
    Column(
        "estado",
        Text,
        CheckConstraint("estado IN ('ok', 'con_errores', 'fallida')"),
        nullable=False,
    ),
    Column("origen", Text, CheckConstraint("origen IN ('web', 'comando')"), nullable=False),
    *[_contador(nombre) for nombre in CONTADORES_SINCRONIZACION],
    Column(
        "codigo_error",
        Text,
        CheckConstraint(
            "codigo_error IS NULL OR codigo_error IN "
            "('sin_fecha_inicio', 'gmail_no_configurado', 'autorizacion_gmail', 'error_inesperado')"
        ),
    ),
    # Migración 0003: hora (como terminada_en) de la última que no quedó
    # "fallida"; NULL si nunca hubo una. Va al final, como la añade ADD COLUMN.
    Column("ultima_correcta_en", Text),
    # Fallida <=> con código de error y sin contadores.
    CheckConstraint("(estado = 'fallida') = (codigo_error IS NOT NULL)"),
    CheckConstraint("(estado = 'fallida') = (nuevos IS NULL)"),
)


# --- Conciliación con el banco (migración 0008, ítem 29) ------------------------------
# Una fila por importación del reporte del banco: fechas y conteos, nunca el
# archivo. ``cambios_importacion`` guarda qué movimiento entró o cambió y sus
# valores anteriores (para el "deshacer" del ítem 30).
importaciones = Table(
    "importaciones",
    metadata,
    Column("id", Integer, primary_key=True, nullable=True),
    Column("hecha_en", Text, nullable=False, server_default=AhoraIso()),
    Column("desde", Text, _solo_sqlite(CheckConstraint(_fecha_valida("desde")))),
    Column("hasta", Text, _solo_sqlite(CheckConstraint(_fecha_valida("hasta")))),
    *[
        _entero_no_negativo(nombre)
        for nombre in (
            "filas", "ya_estaban", "agregados", "confirmados", "corregidos",
            "preguntas", "no_en_banco", "anteriores", "sin_formato",
        )
    ],
    Column("deshecha_en", Text),
)

ACCIONES_IMPORTACION = ("agregado", "confirmado", "corregido", "marcado", "ajuste_reducido")
cambios_importacion = Table(
    "cambios_importacion",
    metadata,
    Column("id", Integer, primary_key=True, nullable=True),
    Column("importacion_id", Integer, ForeignKey("importaciones.id"), nullable=False),
    Column("movimiento_id", Integer, ForeignKey("movimientos.id"), nullable=False),
    Column(
        "accion",
        Text,
        CheckConstraint(
            "accion IN ('agregado', 'confirmado', 'corregido', 'marcado', 'ajuste_reducido')"
        ),
        nullable=False,
    ),
    Column("monto_anterior", Integer),
    Column("estado_anterior", Text),
    Column("no_en_banco_anterior", Integer),
    Column("fecha_banco_anterior", Text),
    Column(
        "referencia_anterior",
        Text,
        _solo_sqlite(CheckConstraint(
            "referencia_anterior IS NULL OR referencia_anterior GLOB '[*][0-9][0-9][0-9][0-9]'"
        )),
    ),
    UniqueConstraint("importacion_id", "movimiento_id", "accion"),
)

# Lo que decide el dueño (D38, D45): "¿es el mismo?" y "¿ya estaba en el saldo
# que ajustaste?". Lo que espera (una fila del banco o un aviso del correo)
# vive aquí y no mueve el saldo hasta la respuesta.
preguntas_conciliacion = Table(
    "preguntas_conciliacion",
    metadata,
    Column("id", Integer, primary_key=True, nullable=True),
    Column("tipo", Text, CheckConstraint("tipo IN ('es_el_mismo', 'ya_estaba_en_ajuste')"), nullable=False),
    Column("fuente", Text, CheckConstraint("fuente IN ('banco', 'correo')"), nullable=False),
    Column("importacion_id", Integer, ForeignKey("importaciones.id")),
    Column("creada_en", Text, nullable=False, server_default=AhoraIso()),
    Column("fecha", Text, nullable=False),
    Column(
        "monto_centavos",
        Integer,
        _solo_sqlite(CheckConstraint("typeof(monto_centavos) = 'integer'")),
        CheckConstraint("monto_centavos <> 0"),
        nullable=False,
    ),
    Column("descripcion", Text, nullable=False, server_default=""),
    Column("referencia", Text, _solo_sqlite(CheckConstraint(REFERENCIA_VALIDA))),
    Column("gmail_id", Text, unique=True),
    Column(
        "tipo_movimiento",
        Text,
        CheckConstraint("tipo_movimiento IN ('compra', 'transferencia', 'ingreso')"),
    ),
    Column("categoria_al_leer", Text),
    Column("ajuste_id", Integer, ForeignKey("movimientos.id")),
    Column("respondida_en", Text),
    Column("respuesta", Text, CheckConstraint("respuesta IN ('si', 'no')")),
    Column("ocurrencia_banco", Integer),
    Column("movimiento_elegido_id", Integer, ForeignKey("movimientos.id", name="fk_pregunta_movimiento_elegido")),
    CheckConstraint("ocurrencia_banco IS NULL OR ocurrencia_banco > 0"),
    _solo_sqlite(CheckConstraint("ocurrencia_banco IS NULL OR typeof(ocurrencia_banco) = 'integer'")),
    CheckConstraint("movimiento_elegido_id IS NULL OR (fuente = 'banco' AND respuesta IS NOT NULL AND ocurrencia_banco IS NOT NULL)"),
    CheckConstraint("(fuente = 'correo') = (gmail_id IS NOT NULL)"),
    CheckConstraint("(fuente = 'correo') = (tipo_movimiento IS NOT NULL)"),
    CheckConstraint("fuente = 'banco' OR monto_centavos > 0"),
    CheckConstraint("(respuesta IS NULL) = (respondida_en IS NULL)"),
)

candidatos_pregunta = Table(
    "candidatos_pregunta",
    metadata,
    Column("pregunta_id", Integer, ForeignKey("preguntas_conciliacion.id"), primary_key=True),
    Column("movimiento_id", Integer, ForeignKey("movimientos.id"), primary_key=True),
    # 1 si el candidato es un aviso del correo que llegó después de importar y
    # se reservó para esta pregunta (D45): al responder se confirma con él en
    # vez de agregar la fila otra vez.
    Column("de_aviso", Integer, CheckConstraint("de_aviso IN (0, 1)"), nullable=False, server_default="0"),
)

# Ítem 30: solo filas normalizadas del diario de reversión, nunca bytes Excel.
reversiones_importacion = Table(
    "reversiones_importacion", metadata,
    Column("importacion_id", Integer, ForeignKey("importaciones.id"), primary_key=True),
    Column("diario", Text, nullable=False),
    Column("conteos", Text, nullable=False),
    Column("ultimo_movimiento_id", Integer, nullable=False),
    Column("arranque", Text),  # 0011: resumen normalizado; nunca archivos/cuerpos.
)


# --- Conexiones -------------------------------------------------------------------

# 0012: ciclos reversibles; una reserva por movimiento, no por día/monto.
descartes_movimientos = Table(
    "descartes_movimientos", metadata,
    Column("id", Integer, primary_key=True, nullable=True),
    Column("movimiento_id", Integer, ForeignKey("movimientos.id"), nullable=False),
    Column("descartado_en", Text, nullable=False),
    Column("restaurado_en", Text),
    Column("fecha", Text, nullable=False),
    Column("monto_centavos", Integer, nullable=False),  # con signo
    Column("referencia", Text),
    Column("fecha_banco", Text),
    Column("monto_banco_centavos", Integer),
    Column("referencia_banco", Text),
    Column("huella_movimiento", Text, nullable=False),
    Column("huella_contexto", Text, nullable=False),
    _solo_sqlite(CheckConstraint(REFERENCIA_VALIDA)),
    _solo_sqlite(CheckConstraint(REFERENCIA_VALIDA.replace("referencia", "referencia_banco"))),
    _solo_sqlite(CheckConstraint("typeof(monto_centavos) = 'integer'")),
    CheckConstraint("monto_centavos <> 0"),
    _solo_sqlite(CheckConstraint("monto_banco_centavos IS NULL OR typeof(monto_banco_centavos) = 'integer'")),
    CheckConstraint("monto_banco_centavos IS NULL OR monto_banco_centavos <> 0"),
    CheckConstraint("(fecha_banco IS NULL) = (monto_banco_centavos IS NULL)"),
    CheckConstraint("fecha_banco IS NOT NULL OR referencia_banco IS NULL"),
)
Index("un_descarte_activo_por_movimiento", descartes_movimientos.c.movimiento_id,
      unique=True, sqlite_where=descartes_movimientos.c.restaurado_en.is_(None),
      postgresql_where=descartes_movimientos.c.restaurado_en.is_(None))
