"""Persistencia de respuestas en la conexión prestada; sin commits propios."""
from __future__ import annotations
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy import Connection, text
from finanzas.infraestructura import persistencia as db
from .colaboradores import ColaboradoresImportacion
from . import motor as c
from .contratos import (PreguntaParaResponder, FilaPreguntaPendiente, _Efecto, ErrorConciliacion, MENSAJE_CANDIDATO_USADO, _AvisoRespondido)
from .reportes_sqlite import (_fecha, _columnas, _reservas_descartes, _elecciones_banco,
    leer_estado, _agregar, _confirmar_descarte, _confirmar, _reducir_ajuste)
from .avisos_sqlite import (_vincular_aviso_descartado, _reservar, _guardar_aviso, _reservados,
    AvisosSQLite)
from .avisos_aplicacion import OperarAvisos
from . import preguntas_aplicacion as _politicas_preguntas
from . import elecciones_sqlite as elecciones_banco

def preguntas_pendientes(conn: Connection) -> list[dict]:
    """Las preguntas sin responder, con sus candidatos (para el ítem 30)."""
    preguntas = [dict(f._mapping) for f in conn.execute(text(
        "SELECT id, tipo, fuente, importacion_id, fecha, monto_centavos, descripcion, referencia "
        "FROM preguntas_conciliacion WHERE respuesta IS NULL ORDER BY id"
    ))]
    for p in preguntas:
        p["candidatos"] = [int(f[0]) for f in conn.execute(
            text("SELECT movimiento_id FROM candidatos_pregunta WHERE pregunta_id = :p ORDER BY movimiento_id"),
            {"p": p["id"]},
        )]
    return preguntas


_SQL_AJUSTES = (
    "SELECT id, fecha_hora, monto_centavos FROM movimientos WHERE tipo = 'ajuste' {donde} "
    "ORDER BY fecha_hora DESC, id DESC LIMIT 1"
)

def _ajuste(conn: Connection, ajuste_id: int | None = None):
    """El último ajuste (o el de ``ajuste_id``): ``(AjusteApp, fecha_hora)`` o ``None``."""
    donde, parametros = ("AND id = :id", {"id": ajuste_id}) if ajuste_id is not None else ("", {})
    fila = conn.execute(text(_SQL_AJUSTES.format(donde=donde)), parametros).first()
    if fila is None:
        return None
    return c.AjusteApp(int(fila[0]), _fecha(fila[1]), int(fila[2])), (str(fila[1]), int(fila[0]))


class PreguntasSQLite:
    def __init__(self, conn: Connection, *, colaboradores: ColaboradoresImportacion):
        self._colaboradores = colaboradores
        self._conn = conn

    def pregunta(self, pregunta_id: int) -> PreguntaParaResponder | None:
        p = self._conn.execute(text(
            "SELECT tipo, fuente, importacion_id, fecha, monto_centavos, descripcion, referencia, gmail_id, "
            "tipo_movimiento, categoria_al_leer, ajuste_id, "
            + ("ocurrencia_banco" if "ocurrencia_banco" in _columnas(self._conn, "preguntas_conciliacion") else "NULL AS ocurrencia_banco")
            + " FROM preguntas_conciliacion WHERE id = :id AND respuesta IS NULL"
        ), {"id": pregunta_id}).mappings().first()
        return None if p is None else PreguntaParaResponder(id=pregunta_id, **p)

    def candidatos(self, pregunta_id: int) -> list[tuple[int, int]]:
        return [(int(f[0]), int(f[1])) for f in self._conn.execute(
            text("SELECT movimiento_id, de_aviso FROM candidatos_pregunta WHERE pregunta_id = :p ORDER BY movimiento_id"),
            {"p": pregunta_id})]

    def ajuste(self, ajuste_id: int | None = None):
        return _ajuste(self._conn, ajuste_id)

    def reducir_ajuste(self, importacion_id: int | None, ajuste_id: int, efecto: int) -> None:
        _reducir_ajuste(self._conn, importacion_id, ajuste_id, efecto, colaboradores=self._colaboradores)

    def movimiento_libre(self, ident: int) -> c.MovimientoApp | None:
        m = self._conn.execute(text(
            "SELECT id, fecha_hora, tipo, monto_centavos, descripcion, origen, estado, referencia "
            "FROM movimientos WHERE id = :id AND fecha_banco IS NULL"
            + (" AND borrado_en IS NULL" if "borrado_en" in _columnas(self._conn, "movimientos") else "")
        ), {"id": ident}).first()
        return None if m is None else c.MovimientoApp(int(m.id), _fecha(m.fecha_hora), str(m.tipo), int(m.monto_centavos),
            str(m.descripcion or ""), str(m.origen), m.estado, m.referencia)

    def elecciones(self) -> list[c.EleccionBanco]:
        return _elecciones_banco(self._conn)

    def pendientes_sin_candidatos(self, pregunta: PreguntaParaResponder) -> list[FilaPreguntaPendiente]:
        pendientes = self._conn.execute(text(
            "SELECT p.id,p.fecha,p.monto_centavos,p.descripcion,p.referencia FROM preguntas_conciliacion p "
            "WHERE p.fuente = 'banco' AND p.respuesta IS NULL AND p.fecha = :fecha "
            "AND p.monto_centavos = :monto AND (p.referencia = :ref OR (p.referencia IS NULL AND :ref IS NULL)) "
            "AND NOT EXISTS (SELECT 1 FROM candidatos_pregunta k WHERE k.pregunta_id = p.id) ORDER BY p.id"
        ), {"fecha": pregunta.fecha, "monto": pregunta.monto_centavos, "ref": pregunta.referencia}).mappings()
        return [FilaPreguntaPendiente(**p) for p in pendientes]

    def leer_estado(self, filas: Sequence[c.FilaBanco]):
        return leer_estado(self._conn, filas, colaboradores=self._colaboradores)

    def agregar_candidato(self, pregunta_id: int, movimiento_id: int) -> None:
        self._conn.execute(db.candidatos_pregunta.insert().values(pregunta_id=pregunta_id, movimiento_id=movimiento_id))

    def aplicar_fila(self, importacion_id: int | None, fila: c.FilaBanco, movimiento_id: int | None, de_aviso: bool = False):
        return _politicas_preguntas._aplicar_fila(self, importacion_id, fila, movimiento_id, de_aviso)

    def responder_correo(self, pregunta: PreguntaParaResponder, elegido: int | None) -> bool:
        return _politicas_preguntas._responder_correo(self, pregunta, elegido)

    def registrar_respuesta(self, pregunta_id: int, si: bool) -> None:
        self._conn.execute(text("UPDATE preguntas_conciliacion SET respuesta = :r, respondida_en = :t WHERE id = :id"),
            {"r": "si" if si else "no", "t": datetime.now().isoformat(timespec="seconds"), "id": pregunta_id})

    def guardar_eleccion(self, pregunta_id: int, movimiento_id: int) -> None:
        elecciones_banco.guardar_eleccion_banco(self._conn, pregunta_id, movimiento_id)

    def preguntas_pendientes(self) -> list[dict]:
        return preguntas_pendientes(self._conn)


    def agregar(self, importacion_id, fila):
        return _agregar(self._conn, importacion_id, fila, colaboradores=self._colaboradores)

    def reservas_descartes(self):
        return _reservas_descartes(self._conn, set(), colaboradores=self._colaboradores)

    def confirmar_descarte(self, fila, movimiento_id, importacion_id):
        _confirmar_descarte(self._conn, fila, movimiento_id, importacion_id, colaboradores=self._colaboradores)

    def fila_para_aplicar(self, movimiento_id):
        return self._colaboradores.bancario.fila_para_aplicar(movimiento_id)

    def confirmar(self, importacion_id, fila, movimiento_id, corregir):
        _confirmar(self._conn, importacion_id, fila, movimiento_id, corregir, colaboradores=self._colaboradores)

    def vincular_descartado(self, ident, gmail_id):
        _vincular_aviso_descartado(self._conn, ident, gmail_id, colaboradores=self._colaboradores)

    def vincular_extracto_activo(self, ident, gmail_id):
        return self._colaboradores.bancario.vincular_extracto_activo(ident, gmail_id)

    def preguntas_que_esperan_al_aviso(self, aviso):
        return OperarAvisos(AvisosSQLite(self._conn, colaboradores=self._colaboradores)).preguntas_que_esperan_al_aviso(aviso)

    def reservar(self, preguntas, movimiento_id):
        _reservar(self._conn, preguntas, movimiento_id)

    def guardar_aviso(self, gmail_id, leido):
        return _guardar_aviso(self._conn, gmail_id, leido, colaboradores=self._colaboradores)

    def decidir_aviso(self, aviso, excluir):
        return OperarAvisos(AvisosSQLite(self._conn, colaboradores=self._colaboradores)).decidir(aviso, excluir)

    def quitar_candidato_de_otras_preguntas_de_correo(self, movimiento_id, pregunta_id):
        """Devuelve las preguntas que se quedaron sin candidatos."""
        otras = [int(f[0]) for f in self._conn.execute(text(
            "SELECT k.pregunta_id FROM candidatos_pregunta k JOIN preguntas_conciliacion p ON p.id = k.pregunta_id "
            "WHERE k.movimiento_id = :m AND k.pregunta_id <> :p AND p.fuente = 'correo' AND p.respuesta IS NULL"),
            {"m": movimiento_id, "p": pregunta_id})]
        for otra in otras:
            self._conn.execute(text("DELETE FROM candidatos_pregunta WHERE pregunta_id = :p AND movimiento_id = :m"),
                               {"p": otra, "m": movimiento_id})
        return [otra for otra in otras if not self.candidatos(otra)]

    def reservado_en_pendientes(self, movimiento_id):
        return movimiento_id in _reservados(self._conn)


def _aplicar_fila(conn: Connection, importacion_id, fila, movimiento_id, de_aviso=False, *, colaboradores: ColaboradoresImportacion):
    return _politicas_preguntas._aplicar_fila(PreguntasSQLite(conn, colaboradores=colaboradores), importacion_id, fila, movimiento_id, de_aviso)


def _responder_correo(conn: Connection, pregunta, elegido, *, colaboradores: ColaboradoresImportacion):
    return _politicas_preguntas._responder_correo(PreguntasSQLite(conn, colaboradores=colaboradores), pregunta, elegido)
