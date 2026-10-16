"""Importación interactiva y reversión sin pisar cambios ajenos (ítem 30).

El análisis usa el mismo guardado que la confirmación, dentro de un SAVEPOINT
que siempre revierte. Su huella incluye toda la información que influye en
saldo, categorías, preguntas e idempotencia. Los archivos se desechan después
de analizarlos; solo quedan filas normalizadas en memoria unos minutos.
"""
from __future__ import annotations

from dataclasses import asdict
from contextlib import nullcontext
from datetime import date, datetime, timezone
import json

from sqlalchemy import select, text, update, delete, and_, or_
from sqlalchemy.exc import IntegrityError

from finanzas.infraestructura import persistencia as db
from .colaboradores import ColaboradoresImportacion
from finanzas.compartido import hora
from finanzas.modulos.importaciones.publico import MovimientoExcel
from .contratos import ErrorConciliacion
from .preguntas_sqlite import _ajuste
from .gestion_aplicacion import _rango

from finanzas.modulos.importaciones.contratos import (
    ConflictoImportacion, ImportacionInexistente, Analisis, MENSAJE_CONFLICTO, MENSAJE_REVERSION)
from finanzas.modulos.importaciones.diario_sqlite import (
    TABLAS_DIARIO, TABLAS_HUELLA, TABLAS, _foto, _clave, _where, _coincide, _revertir,
    _hijos_ajenos, huella, tablas_del_diario)
from finanzas.modulos.importaciones.diario import _json
from finanzas.modulos.importaciones import diario as _politica_diario


def diario(antes, despues):
    return _politica_diario.diario(antes, despues, tablas_del_diario())


def _componer(original, nuevo):
    return _politica_diario._componer(original, nuevo, tablas_del_diario())


def _ajustes(conn):
    return [dict(f) for f in conn.execute(select(db.movimientos).where(
        db.movimientos.c.tipo == "ajuste").order_by(db.movimientos.c.id)).mappings()]


def _importaciones_actuales(conn):
    return [dict(f) for f in conn.execute(select(db.importaciones).order_by(db.importaciones.c.id)).mappings()]


def _categorizar_nuevos(conn, importacion_id, *, colaboradores: ColaboradoresImportacion):
    ids = conn.execute(select(db.cambios_importacion.c.movimiento_id).where(
        db.cambios_importacion.c.importacion_id == importacion_id,
        db.cambios_importacion.c.accion == "agregado")).scalars().all()
    for f in colaboradores.bancario.filas_por_ids(ids):
        regla = colaboradores.asignacion.regla_que_coincide( f["tipo"], f["descripcion"], f["monto_centavos"], "extracto", f["referencia"])
        if regla:
            colaboradores.bancario.asignar_categoria_regla(f["id"], regla.categoria_id, regla.id)


def _guardar(conn, filas, reportes, *, colaboradores: ColaboradoresImportacion):
    resultado = reportes.importar(filas, transaccion_externa=True)
    import logging
    logging.getLogger('finanzas.importacion').info('Importación %s guardada', resultado.importacion_id)
    _categorizar_nuevos(conn, resultado.importacion_id, colaboradores=colaboradores)
    return resultado


def _ofrecer_extender_historial(conn, anteriores, desde, *, colaboradores: ColaboradoresImportacion):
    return bool(anteriores > 0 and desde and colaboradores.saldo.puede_extender_historial( desde=date.fromisoformat(desde)))


def pendientes_saldo(conn, *, colaboradores: ColaboradoresImportacion):
    return {"preguntas": _pendientes(conn), "no_en_banco": _no_banco(conn),
        "sin_categoria": colaboradores.catalogo.resumen_pendientes().cuantos}


def _registro(conn, ident):
    f = conn.execute(select(db.importaciones).where(db.importaciones.c.id == ident)).mappings().first()
    if f is None:
        raise ImportacionInexistente("Esa importación no existe.")
    return f


def _reversion(conn, ident):
    return conn.execute(select(db.reversiones_importacion).where(
        db.reversiones_importacion.c.importacion_id == ident)).mappings().first()


def _pendientes(conn):
    return conn.execute(text("SELECT COUNT(*) FROM preguntas_conciliacion WHERE respuesta IS NULL")).scalar_one()


def _no_banco(conn):
    return conn.execute(text("SELECT COUNT(*) FROM movimientos WHERE no_en_banco = 1 AND borrado_en IS NULL AND revisado_no_en_banco = 0")).scalar_one()


def _filas_sin_categoria(conn, ident):
    return conn.execute(select(db.movimientos).where(db.movimientos.c.id.in_(
        select(db.cambios_importacion.c.movimiento_id).where(db.cambios_importacion.c.importacion_id == ident,
            db.cambios_importacion.c.accion.in_(("agregado", "confirmado", "corregido")))),
        db.movimientos.c.categoria_id.is_(None), db.movimientos.c.tipo != "ajuste",
        db.movimientos.c.borrado_en.is_(None))).mappings().all()


def _sin_categoria_importacion(conn, ident):
    return len(_filas_sin_categoria(conn, ident))


def _hora_importacion_colombia(valor):
    # AhoraIso guarda UTC sin zona; el contrato y el recordatorio usan Colombia.
    return hora.a_hora_colombia(datetime.fromisoformat(valor).replace(tzinfo=timezone.utc))


def _simular_respuesta(conn, p, si, movimiento_id, ya_estaba, caso_respuestas, *, colaboradores: ColaboradoresImportacion,
                       ninguno: bool = False):
    punto = conn.begin_nested()
    try:
        antes = colaboradores.saldo.saldo_actual()
        caso_respuestas.responder_pregunta(p["id"], si, movimiento_id, ya_estaba, ninguno=ninguno, transaccion_externa=True)
        return colaboradores.saldo.saldo_actual() - antes
    finally:
        punto.rollback()


def preguntas(conn, caso_respuestas, *, colaboradores: ColaboradoresImportacion):
    # La simulación solo funciona dentro de una lectura consistente; todos
    # los SAVEPOINT se revierten antes de responder y ninguna pregunta se guarda.
    with db.lectura_consistente(conn):
        lista, _ = _preguntas(conn, caso_respuestas, colaboradores=colaboradores)
        return {"preguntas": lista, "total": len(lista),
            "con_sugerencia": sum(p["sugerencia"]["opcion"] is not None for p in lista)}


class GestionSQLite:
    def __init__(self, conn, reportes, tiempo, *, colaboradores: ColaboradoresImportacion):
        self._colaboradores = colaboradores
        self._conn = conn
        self._reportes = reportes
        self._tiempo = tiempo

    def huella(self):
        return huella(self._conn)

    def foto(self):
        return _foto(self._conn)

    def diario(self, antes, despues):
        return diario(antes, despues)

    def saldo_actual(self):
        return self._colaboradores.saldo.saldo_actual()

    def desglose(self):
        return _desglose(self._conn, colaboradores=self._colaboradores)

    def guardar(self, filas):
        return _guardar(self._conn, filas, self._reportes, colaboradores=self._colaboradores)

    def sin_categoria_importacion(self, ident):
        return _sin_categoria_importacion(self._conn, ident)

    def pendientes(self):
        return _pendientes(self._conn)

    def pendientes_saldo(self):
        return pendientes_saldo(self._conn, colaboradores=self._colaboradores)

    def fecha_inicio(self):
        return self._colaboradores.saldo.leer_configuracion().fecha_inicio.isoformat()

    def ofrecer_extender_historial(self, anteriores, desde):
        return _ofrecer_extender_historial(self._conn, anteriores, desde, colaboradores=self._colaboradores)

    def entran_categorizados(self, ident):
        return self._conn.execute(text("SELECT COUNT(*) FROM cambios_importacion c JOIN movimientos m ON m.id=c.movimiento_id WHERE c.importacion_id=:id AND c.accion='agregado' AND m.categoria_id IS NOT NULL"), {"id": ident}).scalar_one()

    def registrar_reversion(self, resultado, cambios):
        self._conn.execute(db.reversiones_importacion.insert().values(
            importacion_id=resultado.importacion_id, diario=_json(cambios),
            conteos=_json({**asdict(resultado.conteos), "_ajustes": _ajustes(self._conn)}), ultimo_movimiento_id=self._conn.execute(
                text("SELECT COALESCE(MAX(id),0) FROM movimientos")).scalar_one()))

    def detalle(self, ident):
        with db.lectura_consistente(self._conn):
            return _consultas_importaciones._detalle(self, ident, self._tiempo)

    def registro(self, ident):
        return dict(_registro(self._conn, ident))

    def deshacible(self, fila):
        return _consultas_importaciones._deshacible(self, fila)

    def reversion(self, ident):
        fila = _reversion(self._conn, ident)
        return None if fila is None else dict(fila)

    def revertir(self, cambios):
        _revertir(self._conn, cambios)

    def marcar_deshecha(self, ident):
        self._conn.execute(update(db.importaciones).where(db.importaciones.c.id == ident).values(
            deshecha_en=hora.ahora_colombia().replace(tzinfo=None).isoformat(timespec="seconds")))

    def ajustes(self):
        return _ajustes(self._conn)

    def importaciones_actuales(self):
        return _importaciones_actuales(self._conn)

    def revisiones(self):
        return [dict(f) for f in self._conn.execute(select(db.reversiones_importacion)).mappings()]

    def pregunta(self, ident):
        return dict(self._conn.execute(select(db.preguntas_conciliacion).where(db.preguntas_conciliacion.c.id == ident)).mappings().one())

    def componer(self, original, nuevo):
        return _componer(original, nuevo)

    def actualizar_revision(self, ident, cambios, conteos):
        self._conn.execute(update(db.reversiones_importacion).where(db.reversiones_importacion.c.importacion_id == ident).values(
            diario=_json(cambios), conteos=_json(conteos)))

    def ultimo_id(self):
        return self._conn.execute(text("SELECT COALESCE(MAX(id),0) FROM movimientos")).scalar_one()

    def pendiente_no_en_banco(self, ident):
        fila = self._conn.execute(select(db.movimientos).where(db.movimientos.c.id == ident,
            db.movimientos.c.no_en_banco == 1, db.movimientos.c.borrado_en.is_(None),
            db.movimientos.c.revisado_no_en_banco == 0)).mappings().first()
        return None if fila is None else dict(fila)

    def tiene_pregunta_pendiente(self, ident):
        return bool(self._conn.execute(select(db.candidatos_pregunta.c.pregunta_id).join(db.preguntas_conciliacion).where(
            db.candidatos_pregunta.c.movimiento_id == ident, db.preguntas_conciliacion.c.respuesta.is_(None))).first())

    def marcar_decision(self, ident, opcion):
        self._colaboradores.bancario.marcar_decision(ident,
            hora.ahora_colombia().isoformat(timespec="seconds") if opcion == "borrar" else None)

    def ajuste_posterior(self, ultimo_id):
        return bool(self._conn.execute(select(db.movimientos.c.id).where(db.movimientos.c.tipo == "ajuste",
            db.movimientos.c.id > ultimo_id)).first())

    def restaurar_revision(self, revision):
        self._conn.execute(update(db.reversiones_importacion).where(
            db.reversiones_importacion.c.importacion_id == revision["importacion_id"]).values(**revision))

    def configuracion(self):
        return self._colaboradores.saldo.leer_configuracion()

    def contar_sin_categorizar(self):
        return self._colaboradores.catalogo.resumen_pendientes().cuantos

    def no_banco(self):
        return _no_banco(self._conn)

    def filas_sin_categoria(self, ident):
        return [dict(f) for f in _filas_sin_categoria(self._conn, ident)]

    def ultima_importacion_activa(self):
        return DiferenciasSQLite(self._conn, None, colaboradores=self._colaboradores).ultima_importacion_activa()

    def ultima_importacion_id(self):
        return self._conn.execute(select(db.importaciones.c.id).order_by(db.importaciones.c.id.desc()).limit(1)).scalar()

    def movimientos_desde(self, ident):
        return self._conn.execute(text("SELECT COUNT(*) FROM movimientos WHERE id > :id AND tipo <> 'ajuste' AND borrado_en IS NULL"), {"id": ident}).scalar_one()

    def importacion_posterior(self, ident):
        return bool(self._conn.execute(select(db.importaciones.c.id).where(db.importaciones.c.id > ident,
            db.importaciones.c.deshecha_en.is_(None))).first())

    def movimiento_posterior(self, ident):
        return bool(self._conn.execute(select(db.movimientos.c.id).where(db.movimientos.c.id > ident)).first())

    def reservas_ajenas(self, ids, propias):
        reservas = self._conn.execute(select(db.descartes_movimientos.c.id).where(
            db.descartes_movimientos.c.movimiento_id.in_(ids))).first() if ids else None
        return reservas is not None and self._conn.execute(select(db.descartes_movimientos.c.id).where(
            db.descartes_movimientos.c.movimiento_id.in_(ids), db.descartes_movimientos.c.id.not_in(propias))).first() is not None

    def coincide(self, cambios):
        return _coincide(self._conn, cambios)

    def hijos_ajenos(self, cambios):
        return _hijos_ajenos(self._conn, cambios)


from .diferencias_aplicacion import _grupos, _dato, _identificaciones
from . import diferencias_aplicacion as _consultas_diferencias


def _preguntas(conn, caso_respuestas, *, colaboradores: ColaboradoresImportacion):
    return _consultas_diferencias._preguntas(DiferenciasSQLite(conn, caso_respuestas, colaboradores=colaboradores))


def no_en_banco(conn, *, colaboradores: ColaboradoresImportacion):
    with db.lectura_consistente(conn):
        return _consultas_diferencias._no_en_banco(DiferenciasSQLite(conn, None, colaboradores=colaboradores))


class DiferenciasSQLite:
    def __init__(self, conn, respuestas, *, colaboradores: ColaboradoresImportacion):
        self._colaboradores = colaboradores
        self._conn = conn
        self._respuestas = respuestas

    def preguntas_pendientes(self):
        return [dict(p) for p in self._conn.execute(select(db.preguntas_conciliacion).where(
            db.preguntas_conciliacion.c.respuesta.is_(None)).order_by(db.preguntas_conciliacion.c.id)).mappings()]

    def candidatos(self, pregunta_id):
        ids = self._conn.execute(select(db.candidatos_pregunta.c.movimiento_id).where(
            db.candidatos_pregunta.c.pregunta_id == pregunta_id)).scalars().all()
        reserva_activa = select(db.descartes_movimientos.c.id).where(
            db.descartes_movimientos.c.movimiento_id == db.movimientos.c.id,
            db.descartes_movimientos.c.restaurado_en.is_(None)).exists()
        candidatos = [dict(f) for f in self._conn.execute(select(db.movimientos,
            reserva_activa.label("reserva_activa")).where(db.movimientos.c.id.in_(ids),
            or_(db.movimientos.c.borrado_en.is_(None), reserva_activa)).order_by(db.movimientos.c.id)).mappings()]
        return candidatos

    def ajuste(self, ajuste_id):
        fila = self._conn.execute(select(db.movimientos).where(db.movimientos.c.id == ajuste_id)).mappings().first()
        return None if fila is None else dict(fila)

    def ultimo_ajuste(self):
        return _ajuste(self._conn)

    def simular_respuesta(self, pregunta, si, movimiento_id, ya_estaba, ninguno=False):
        return _simular_respuesta(self._conn, pregunta, si, movimiento_id, ya_estaba, self._respuestas,
                                  colaboradores=self._colaboradores, ninguno=ninguno)

    def reservas_candidato(self, movimiento_id):
        return self._conn.execute(text("SELECT COUNT(*) FROM candidatos_pregunta c JOIN preguntas_conciliacion p ON p.id=c.pregunta_id WHERE c.movimiento_id=:id AND p.respuesta IS NULL"), {"id": movimiento_id}).scalar_one()

    def ultima_importacion_activa(self):
        ultima_fila = self._conn.execute(select(db.importaciones).where(db.importaciones.c.deshecha_en.is_(None)).order_by(db.importaciones.c.id.desc()).limit(1)).mappings().first()
        return None if ultima_fila is None else dict(ultima_fila)

    def fuera_del_banco(self):
        filas = self._conn.execute(select(db.movimientos).where(db.movimientos.c.no_en_banco == 1,
            db.movimientos.c.borrado_en.is_(None), db.movimientos.c.revisado_no_en_banco == 0)).mappings()
        return [dict(f) for f in filas]

from . import consultas_aplicacion as _consultas_importaciones


def _desglose(conn, *, colaboradores: ColaboradoresImportacion):
    caso = colaboradores.saldo
    if caso.leer_configuracion() is None:
        return None
    partes = caso.desglose_saldo()
    return {**asdict(partes), "saldo_centavos": partes.saldo_centavos}


class HistorialImportacionesSQLite(GestionSQLite):
    def guardar_historial(self, historial, avisos, inicio_anterior):
        resultado = self._reportes.importar(historial.filas, cobertura=historial.cobertura,
            compensar_en_inicial_antes=inicio_anterior, transaccion_externa=True)
        import logging
        logging.getLogger("finanzas.importacion").info("Importación %s guardada", resultado.importacion_id)
        _categorizar_nuevos(self._conn, resultado.importacion_id, colaboradores=self._colaboradores)
        gmail_ids = [a.gmail_id for a in avisos if a.movimiento is not None]
        from .reportes_sqlite import _registrar_cambio
        for ident in self._conn.execute(select(db.movimientos.c.id).where(db.movimientos.c.gmail_id.in_(gmail_ids))).scalars():
            _registrar_cambio(self._conn, resultado.importacion_id, ident, "agregado")
        return resultado

    def registrar_historial(self, resultado, antes, vista):
        self._conn.execute(db.reversiones_importacion.insert().values(
            importacion_id=resultado.importacion_id, diario=_json(diario(antes, self.foto())),
            conteos=_json({**asdict(resultado.conteos), "_ajustes": self.ajustes()}),
            ultimo_movimiento_id=self.ultimo_id(),
            arranque=_json({k: v for k, v in vista.items() if k != "comprobacion_saldo"})))
