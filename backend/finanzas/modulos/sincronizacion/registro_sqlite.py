"""Participante de avisos/estado: conexión prestada, sin depender de flujos."""
from __future__ import annotations
import logging
from datetime import date
from sqlalchemy import RowMapping
from dataclasses import asdict
from contextlib import nullcontext
from sqlalchemy import Connection, select, union, delete, func
from finanzas.infraestructura import persistencia as db
from finanzas.compartido import hora
from finanzas.modulos.movimientos.publico import MovimientoNuevo
from finanzas.modulos.importaciones import publico as importaciones
from finanzas.modulos.sincronizacion.adaptadores.avisos import extractor
from .contratos import ResultadoSincronizacion, EstadoSincronizacion, SincronizacionNoConfigurada
from finanzas.compartido.hora import ZONA_COLOMBIA
from finanzas.modulos.sincronizacion.publico import CorreoGmail
logger = logging.getLogger("finanzas.sincronizacion")

def _ids_registrados(conn: Connection) -> set[str]:
    m, n = db.movimientos.c, db.correos_no_reconocidos.c
    p = db.preguntas_conciliacion.c  # avisos que esperan "¿es el mismo?" (ítem 29)
    filas = conn.execute(
        union(
            select(m.gmail_id).where(m.gmail_id.is_not(None)),
            select(n.gmail_id),
            select(p.gmail_id).where(p.gmail_id.is_not(None)),
        )
    ).all()
    return {fila[0] for fila in filas}


def _columnas_de_categoria(conn: Connection, movimiento: extractor.MovimientoExtraido, *, colaboradores) -> dict:
    """Columnas de categoría con que se guarda un movimiento leído.

    1. Si el aviso implica su categoría (``categoria_al_leer``: un retiro va
       a "Retiro a efectivo", D30) y existe una categoría de gasto con ese
       nombre (comparado como en la app, ``categorizacion.normalizar``: sin
       distinguir mayúsculas ni espacios; si hubiera varias, la de menor
       id), se guarda con ella, ``origen_categoria`` ``NULL`` y sin
       regla. ``NULL`` porque no la puso el dueño ni una regla, y el modelo
       solo admite ``manual``, ``regla`` o vacío (especificación, ítem 14):
       la API la muestra como ``desconocido``, igual que las categorías de
       antes de la 0004. No se añade un valor nuevo al ``CHECK`` para no
       reconstruir ``movimientos`` ni cambiar la interfaz en un arreglo
       urgente. Si el dueño corrige la categoría a mano, pasa a ``manual``
       como cualquier otra. Si la categoría ya no existe (el dueño la borró
       o la renombró), se sigue con el paso 2.
    2. Si el movimiento cumple una regla (su texto y su monto, ítem 17), se
       guarda ya categorizado, con origen ``regla`` y el id de la regla que
       gana (ítem 14); si no, llega sin categoría y queda en la bandeja "Sin
       categorizar". Un retiro con su categoría nunca pasa por las reglas.

    La sincronización y el reproceso (ítem 19) pasan los dos por aquí.
    """
    return asdict(colaboradores.clasificacion.categoria_para_entrada(
        movimiento.tipo, movimiento.descripcion, movimiento.monto_centavos, movimiento.categoria_al_leer))


def _guardar_movimiento(
    conn: Connection,
    gmail_id: str,
    movimiento: extractor.MovimientoExtraido,
    quitar_no_reconocido: bool = False,
    *, transaccion_externa: bool = False, colaboradores,
) -> bool:
    """Inserta el movimiento; ``False`` si ese ``gmail_id`` ya existía.

    Con ``quitar_no_reconocido`` (reproceso, ítem 19) borra además la fila de
    ``correos_no_reconocidos`` en la misma transacción: el id nunca queda sin
    registrar (ni en dos sitios) a medias, así una sincronización simultánea
    no lo vuelve a descargar.

    La categoría se calcula dentro de la misma transacción del INSERT, abierta
    con ``BEGIN IMMEDIATE`` (``db.transaccion(..., inmediata=True)``, reserva la escritura antes de leer las reglas).
    Así, una regla que la web guarde al mismo tiempo queda antes o después,
    nunca en medio: si ya existía al insertar, el movimiento llega
    categorizado; si llega después, "Recordar" lo categoriza al aplicarse a
    los pendientes. La otra conexión solo espera unos milisegundos.
    """
    with nullcontext() if transaccion_externa else db.transaccion(conn, inmediata=True):
        # Ítem 29 (D45): si ya entró del banco sin aviso, se confirma ese
        # movimiento (o se pregunta) en vez de crear otro.
        aviso = colaboradores.incorporacion.incorporar_aviso(gmail_id, movimiento)
        if aviso != importaciones.AVISO_NUEVO:
            if quitar_no_reconocido:
                n = db.correos_no_reconocidos.c
                conn.execute(delete(db.correos_no_reconocidos).where(n.gmail_id == gmail_id))
            return aviso != importaciones.AVISO_YA_ESTABA
        categoria = _columnas_de_categoria(conn, movimiento, colaboradores=colaboradores)
        resultado = colaboradores.normalizado.registrar_correo_si_nuevo(MovimientoNuevo(
            fecha_hora=movimiento.fecha_hora.isoformat(timespec="seconds"),
            monto_centavos=movimiento.monto_centavos, tipo=movimiento.tipo, descripcion=movimiento.descripcion,
            **categoria, origen="gmail", gmail_id=gmail_id,
        ))
        if quitar_no_reconocido:
            n = db.correos_no_reconocidos.c
            conn.execute(delete(db.correos_no_reconocidos).where(n.gmail_id == gmail_id))
    return resultado


def guardar_estado(
    conn: Connection,
    origen: str,
    resultado: ResultadoSincronizacion | None = None,
    codigo_error: str | None = None,
    *, transaccion_externa: bool = False,
) -> EstadoSincronizacion:
    """Reemplaza la fila del estado y devuelve lo guardado.

    ``ultima_correcta_en``: si esta sincronización no quedó ``"fallida"``,
    pasa a ser su ``terminada_en``; si falló, se conserva la que había (la
    primera vez, ``None``). Lo devuelto trae el valor que quedó en la base:
    si no se pudo escribir, el que ya había (o ``None`` si tampoco se puede
    leer), nunca uno que no se guardó.

    No lanza por la base: si está ocupada o algo falla al escribir, la
    sincronización ya ocurrió y no debe darse por fallida solo por no poder
    anotar su estado (se registra el tipo de error, sin datos, y se devuelve
    el estado igualmente). Guarda solo contadores y un código de error de la
    lista cerrada ``db.CODIGOS_ERROR_SINCRONIZACION``.
    """
    if origen not in db.ORIGENES_SINCRONIZACION:
        raise ValueError("origen de sincronización desconocido")
    if (resultado is None) == (codigo_error is None):
        raise ValueError("se guarda un resultado o un código de error, no ambos")
    if codigo_error is not None and codigo_error not in db.CODIGOS_ERROR_SINCRONIZACION:
        raise ValueError("código de error de sincronización desconocido")
    if resultado is None:
        estado = "fallida"
    else:
        estado = "con_errores" if resultado.errores else "ok"
    terminada_en = hora.ahora_colombia().isoformat(timespec="seconds")
    correcta = estado != "fallida"
    valores: dict[str, object] = {
        "id": 1,
        "terminada_en": terminada_en,
        "estado": estado,
        "origen": origen,
        "codigo_error": codigo_error,
        "ultima_correcta_en": terminada_en if correcta else None,
    }
    for nombre in db.CONTADORES_SINCRONIZACION:
        valores[nombre] = None if resultado is None else int(getattr(resultado, nombre))
    # Al actualizar la fila, una fallida no toca ultima_correcta_en.
    actualizar = {
        k: v for k, v in valores.items()
        if k != "id" and (correcta or k != "ultima_correcta_en")
    }
    ultima_correcta_en: str | None = terminada_en if correcta else None
    try:
        with nullcontext() if transaccion_externa else db.transaccion(conn):
            insercion = db.insertar(conn, db.estado_sincronizacion).values(**valores)
            conn.execute(insercion.on_conflict_do_update(index_elements=["id"], set_=actualizar))
            if not correcta:
                ultima_correcta_en = _leer_ultima_correcta(conn)
    except Exception as error:
        if transaccion_externa:
            # El arranque31 necesita todo o nada: el llamador revierte la
            # operación completa y no podemos consumir ese error aquí.
            raise
        logger.warning("No se pudo guardar el estado de la sincronización (%s)", type(error).__name__)
        # No se guardó: se devuelve lo que sigue en la base, no la hora de esta.
        try:
            conn.rollback()
            ultima_correcta_en = _leer_ultima_correcta(conn)
            conn.rollback()  # cierra la lectura (autobegin) sin dejar la conexión en transacción
        except Exception:
            ultima_correcta_en = None
    return EstadoSincronizacion(
        terminada_en=terminada_en,
        estado=estado,
        origen=origen,
        resultado=resultado,
        codigo_error=codigo_error,
        ultima_correcta_en=ultima_correcta_en,
    )


def _leer_ultima_correcta(conn: Connection) -> str | None:
    t = db.estado_sincronizacion.c
    valor = conn.execute(select(t.ultima_correcta_en).where(t.id == 1)).scalar_one_or_none()
    return None if valor is None else str(valor)


def leer_estado(conn: Connection) -> EstadoSincronizacion | None:
    """El estado de la última sincronización, o ``None`` si nunca se ha sincronizado."""
    t = db.estado_sincronizacion.c
    fila = conn.execute(select(db.estado_sincronizacion).where(t.id == 1)).mappings().first()
    if fila is None:
        return None
    resultado = None
    if fila["estado"] != "fallida":
        resultado = ResultadoSincronizacion(
            **{nombre: int(fila[nombre]) for nombre in db.CONTADORES_SINCRONIZACION}
        )
    return EstadoSincronizacion(
        terminada_en=str(fila["terminada_en"]),
        estado=str(fila["estado"]),
        origen=str(fila["origen"]),
        resultado=resultado,
        codigo_error=fila["codigo_error"],
        ultima_correcta_en=(
            None if fila["ultima_correcta_en"] is None else str(fila["ultima_correcta_en"])
        ),
    )


def contar_no_reconocidos(conn: Connection) -> int:
    """Cuenta la misma lista vigente; los resueltos ya no están en ella."""
    return conn.execute(select(func.count()).select_from(db.correos_no_reconocidos)).scalar_one()


class AvisosRegistradosSQLite:
    def __init__(self, conn, *, colaboradores):
        self._conn = conn
        self._colaboradores = colaboradores

    def ids_registrados(self):
        return _ids_registrados(self._conn)

    def guardar_movimiento(self, gmail_id, movimiento):
        return _guardar_movimiento(self._conn, gmail_id, movimiento, transaccion_externa=True, colaboradores=self._colaboradores)

    def guardar_no_reconocido(self, aviso):
        return self._conn.execute(db.insertar(self._conn, db.correos_no_reconocidos).values(
            gmail_id=aviso.gmail_id, fecha=aviso.fecha, asunto=aviso.asunto
        ).on_conflict_do_nothing(index_elements=["gmail_id"])).rowcount

    def guardar_estado(self, resultado):
        return guardar_estado(self._conn, "web", resultado=resultado, transaccion_externa=True)

    def leer_estado(self):
        return leer_estado(self._conn)

    def contar_no_reconocidos(self):
        return contar_no_reconocidos(self._conn)


def _guardar_no_reconocido(conn: Connection, correo: CorreoGmail) -> bool:
    """Guarda solo id, fecha y asunto. ``False`` si ya estaba."""
    fecha = correo.fecha.astimezone(ZONA_COLOMBIA).replace(tzinfo=None)
    with db.transaccion(conn):
        resultado = conn.execute(
            db.insertar(conn, db.correos_no_reconocidos)
            .values(
                gmail_id=correo.gmail_id,
                fecha=fecha.isoformat(timespec="seconds"),
                asunto=correo.asunto,
            )
            .on_conflict_do_nothing(index_elements=["gmail_id"])
        )
    return resultado.rowcount == 1

def es_no_reconocido(conn: Connection, gmail_id: str) -> bool:
    """``True`` si ese id está en la lista de no reconocidos."""
    t = db.correos_no_reconocidos.c
    return conn.execute(select(t.gmail_id).where(t.gmail_id == gmail_id)).first() is not None

def fecha_configurada(conn: Connection) -> bool:
    """``True`` si hay fecha de inicio (sin ella, sincronizar falla con ``sin_fecha_inicio``)."""
    try:
        leer_fecha_inicio(conn)
    except SincronizacionNoConfigurada:
        return False
    return True

def leer_fecha_inicio(conn: Connection) -> date:
    """Fecha de inicio configurada; ``SincronizacionNoConfigurada`` si falta."""
    c = db.configuracion_saldo.c
    fila = conn.execute(select(c.fecha_inicio).where(c.id == 1)).first()
    if fila is None:
        raise SincronizacionNoConfigurada(
            "Todavía no se ha configurado el saldo inicial ni la fecha de inicio. "
            "Configúralos antes de sincronizar: solo se leen los correos desde esa fecha."
        )
    try:
        return date.fromisoformat(str(fila[0])[:10])
    except ValueError:
        raise SincronizacionNoConfigurada(
            "La fecha de inicio guardada no es válida. Vuelve a configurarla."
        ) from None

def listar_no_reconocidos(conn: Connection) -> list[RowMapping]:
    """Correos no reconocidos (id de Gmail, fecha y asunto), del más reciente al más antiguo."""
    t = db.correos_no_reconocidos.c
    return list(
        conn.execute(
            select(t.gmail_id, t.fecha, t.asunto).order_by(t.fecha.desc(), t.gmail_id)
        ).mappings()
    )


class RegistroSincronizacionSQLite(AvisosRegistradosSQLite):
    def leer_fecha_inicio(self):
        return leer_fecha_inicio(self._conn)

    def fecha_configurada(self):
        return fecha_configurada(self._conn)

    def listar_no_reconocidos(self):
        return listar_no_reconocidos(self._conn)

    def es_no_reconocido(self, gmail_id):
        return es_no_reconocido(self._conn, gmail_id)

    def guardar_correo_no_reconocido(self, correo):
        return _guardar_no_reconocido(self._conn, correo)

    def guardar_movimiento(self, gmail_id, movimiento, quitar_no_reconocido=False):
        return _guardar_movimiento(self._conn, gmail_id, movimiento, quitar_no_reconocido=quitar_no_reconocido,
                                  colaboradores=self._colaboradores)

    def guardar_estado_sincronizacion(self, origen, resultado=None, codigo_error=None):
        return guardar_estado(self._conn, origen, resultado, codigo_error)

    def en_transaccion(self):
        return self._conn.in_transaction()

    def cerrar_lectura(self):
        self._conn.rollback()
