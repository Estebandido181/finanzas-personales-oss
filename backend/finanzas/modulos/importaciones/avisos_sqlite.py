"""Persistencia de incorporación tardía, bajo la transacción de quien llama."""
from __future__ import annotations
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date, timedelta
from sqlalchemy import Connection, text
from finanzas.infraestructura import persistencia as db
from .colaboradores import ColaboradoresImportacion
from finanzas.modulos.movimientos.publico import MovimientoNuevo
from . import motor as c
from .contratos import AvisoNormalizado, ErrorConciliacion, MENSAJE_CANDIDATO_USADO
from .reportes_sqlite import _fecha, _columnas, _reservas_descartes

_SQL_RESERVADOS = text(
    "SELECT k.movimiento_id FROM candidatos_pregunta k "
    "JOIN preguntas_conciliacion p ON p.id = k.pregunta_id WHERE p.respuesta IS NULL"
)

def _vincular_aviso_descartado(conn: Connection, ident: int, gmail_id: str, *, colaboradores: ColaboradoresImportacion) -> None:
    reserva = next((r for r in _reservas_descartes(conn, set(), colaboradores=colaboradores) if r.movimiento.id == ident), None)
    if reserva is None or reserva.banco is None or reserva.gmail_id is not None:
        raise ErrorConciliacion(MENSAJE_CANDIDATO_USADO)
    if not colaboradores.bancario.vincular_descartado(ident, gmail_id):
        raise ErrorConciliacion(MENSAJE_CANDIDATO_USADO)
    colaboradores.descartes.actualizar_respaldo_banco( ident, fecha=reserva.banco.fecha,
        monto_centavos=reserva.banco.monto_centavos, referencia=reserva.movimiento.referencia)


def _reservados(conn: Connection) -> set[int]:
    """Movimientos que son candidatos de una pregunta sin responder."""
    return {int(f[0]) for f in conn.execute(_SQL_RESERVADOS)}


def _sin_aviso_cercanos(conn: Connection, fecha: date, reservados: set[int]) -> list[c.MovimientoApp]:
    """Lo que entró del banco sin aviso, del día ±1 (con su marca de reservado)."""
    return [
        c.MovimientoApp(
            id=int(f[0]), fecha=_fecha(f[1]), tipo=str(f[2]), monto_centavos=int(f[3]),
            descripcion=str(f[4] or ""), origen=str(f[5]), estado=f[6], referencia=f[7],
            fecha_banco=_fecha(f[8]), reservado=int(f[0]) in reservados,
        )
        for f in conn.execute(
            text(
                "SELECT id, fecha_hora, tipo, monto_centavos, descripcion, origen, estado, referencia, "
                "fecha_banco FROM movimientos WHERE origen = 'extracto' AND estado = 'sin_aviso' "
                "AND gmail_id IS NULL "
                + ("AND borrado_en IS NULL " if "borrado_en" in _columnas(conn, "movimientos") else "")
                + "AND substr(fecha_hora, 1, 10) BETWEEN :desde AND :hasta ORDER BY id"
            ),
            {"desde": (fecha - timedelta(days=1)).isoformat(), "hasta": (fecha + timedelta(days=1)).isoformat()},
        )
    ]


def _filas_que_esperan(conn: Connection, fecha: date) -> list[c.MovimientoApp]:
    """Las filas del banco que esperan respuesta (día ±1), como si ya hubieran entrado.

    El ``id`` de cada una es el de su pregunta: así el motor las compara con
    las mismas reglas que lo que entró sin aviso.
    """
    salida = []
    for f in conn.execute(
        text(
            "SELECT id, fecha, monto_centavos, descripcion, referencia FROM preguntas_conciliacion "
            "WHERE fuente = 'banco' AND respuesta IS NULL AND fecha BETWEEN :desde AND :hasta ORDER BY id"
        ),
        {"desde": (fecha - timedelta(days=1)).isoformat(), "hasta": (fecha + timedelta(days=1)).isoformat()},
    ):
        fila = c.FilaBanco(_fecha(f[1]), int(f[2]), str(f[3] or ""), f[4])
        salida.append(c.MovimientoApp(
            id=int(f[0]), fecha=fila.fecha, tipo=c.tipo_de_fila(fila), monto_centavos=abs(fila.monto_centavos),
            descripcion=fila.descripcion, origen=c.ORIGEN_EXTRACTO, estado=c.ESTADO_SIN_AVISO,
            referencia=fila.referencia, fecha_banco=fila.fecha,
        ))
    return salida


def _guardar_aviso(conn: Connection, gmail_id: str, movimiento, *, colaboradores: ColaboradoresImportacion) -> int:
    """Guarda el aviso como un movimiento del correo, con sus reglas de categoría."""
    categoria = asdict(colaboradores.clasificacion.categoria_para_entrada(
        movimiento.tipo, movimiento.descripcion, movimiento.monto_centavos, movimiento.categoria_al_leer))
    return colaboradores.normalizado.registrar(MovimientoNuevo(
        fecha_hora=movimiento.fecha_hora.isoformat(timespec="seconds"),
        monto_centavos=movimiento.monto_centavos, tipo=movimiento.tipo, descripcion=movimiento.descripcion,
        origen=c.ORIGEN_GMAIL, gmail_id=gmail_id, **categoria,
    ))


def _pregunta_de_correo(conn: Connection, gmail_id: str, movimiento, candidatos: Sequence[int]) -> None:
    # El extractor entrega los destinos numéricos ya recortados a *dddd (41).
    resultado = conn.execute(db.preguntas_conciliacion.insert().values(
        tipo=c.PREGUNTA_ES_EL_MISMO, fuente="correo",
        fecha=movimiento.fecha_hora.isoformat(timespec="seconds"),
        monto_centavos=movimiento.monto_centavos, descripcion=movimiento.descripcion,
        gmail_id=gmail_id, tipo_movimiento=movimiento.tipo,
        categoria_al_leer=getattr(movimiento, "categoria_al_leer", None),
    ))
    pregunta_id = int(resultado.inserted_primary_key[0])
    for movimiento_id in candidatos:
        conn.execute(db.candidatos_pregunta.insert().values(pregunta_id=pregunta_id, movimiento_id=movimiento_id))


def _reservar(conn: Connection, preguntas: Sequence[int], movimiento_id: int) -> None:
    for pregunta_id in preguntas:
        conn.execute(db.candidatos_pregunta.insert().values(
            pregunta_id=pregunta_id, movimiento_id=movimiento_id, de_aviso=1))



class AvisosSQLite:
    def __init__(self, conn: Connection, *, colaboradores: ColaboradoresImportacion):
        self._colaboradores = colaboradores
        self._conn = conn

    def admite_conciliacion(self) -> bool:
        return "estado" in _columnas(self._conn, "movimientos")

    def ya_registrado(self, gmail_id: str) -> bool:
        return bool(self._conn.execute(text("SELECT 1 FROM preguntas_conciliacion WHERE gmail_id = :g "
                         "UNION ALL SELECT 1 FROM movimientos WHERE gmail_id = :g"), {"g": gmail_id}).first())

    def reservados(self) -> set[int]:
        return _reservados(self._conn)

    def cercanos(self, fecha: date, reservados: set[int]) -> list[c.MovimientoApp]:
        return _sin_aviso_cercanos(self._conn, fecha, reservados)

    def reservas(self, reservados: set[int]) -> list[c.ReservaDescarte]:
        return _reservas_descartes(self._conn, reservados, colaboradores=self._colaboradores)

    def vincular_descarte(self, movimiento_id: int, gmail_id: str) -> None:
        _vincular_aviso_descartado(self._conn, movimiento_id, gmail_id, colaboradores=self._colaboradores)

    def confirmar(self, movimiento_id: int, gmail_id: str) -> None:
        self._colaboradores.bancario.vincular_si_libre(movimiento_id, gmail_id)

    def preguntar(self, gmail_id: str, movimiento: AvisoNormalizado, candidatos: Sequence[int]) -> None:
        _pregunta_de_correo(self._conn, gmail_id, movimiento, candidatos)

    def preguntas_con_aviso(self) -> set[int]:
        return {int(f[0]) for f in self._conn.execute(text(
            "SELECT DISTINCT pregunta_id FROM candidatos_pregunta WHERE de_aviso = 1"))}

    def filas_que_esperan(self, fecha: date) -> list[c.MovimientoApp]:
        return _filas_que_esperan(self._conn, fecha)

    def guardar(self, gmail_id: str, movimiento: AvisoNormalizado) -> int:
        return _guardar_aviso(self._conn, gmail_id, movimiento, colaboradores=self._colaboradores)

    def reservar(self, preguntas: Sequence[int], movimiento_id: int) -> None:
        _reservar(self._conn, preguntas, movimiento_id)
