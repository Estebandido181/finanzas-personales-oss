"""Respuestas del dueño y reglas D45, sin SQL ni composición de infraestructura."""
from __future__ import annotations
from collections.abc import Sequence
from contextlib import nullcontext
from datetime import date, datetime, timedelta
from . import motor as c
from .contratos import (PersistenciaPreguntas, UnidadPreguntas, ErrorConciliacion, _Efecto, _AvisoRespondido,
    MENSAJE_CANDIDATO, MENSAJE_CANDIDATO_USADO, MENSAJE_FALTA_AJUSTE, MENSAJE_PREGUNTA_NO_EXISTE)


def _fecha(valor: object) -> date:
    return date.fromisoformat(str(valor)[:10])


def _elegir(candidatos: Sequence[int], movimiento_id: int | None) -> int:
    if movimiento_id is None and len(candidatos) == 1:
        return candidatos[0]
    if movimiento_id not in candidatos:
        raise ErrorConciliacion(MENSAJE_CANDIDATO)
    return movimiento_id


def _efecto_con_ajuste(registro: PersistenciaPreguntas, importacion_id: int | None, fila: c.FilaBanco, efecto: _Efecto,
                       ya_estaba: bool | None) -> None:
    """Regla del último ajuste (D45) al aplicar una respuesta."""
    ultimo = registro.ajuste()
    if ultimo is None or not efecto.para(ultimo[0].id) or fila.fecha > ultimo[0].fecha:
        return
    if fila.fecha == ultimo[0].fecha:
        if ya_estaba is None:
            raise ErrorConciliacion(MENSAJE_FALTA_AJUSTE)
        if not ya_estaba:
            return
    registro.reducir_ajuste(importacion_id, ultimo[0].id, efecto.para(ultimo[0].id))


def _efecto_ya_estaba(registro: PersistenciaPreguntas, importacion_id: int | None, fila: c.FilaBanco, efecto: _Efecto,
                      ya_estaba: bool, ajuste_id: int | None) -> None:
    """Respuesta a "¿ya estaba en el saldo que ajustaste?".

    Normalmente se aplica sobre el ajuste de la pregunta. Si el dueño hizo un
    ajuste más nuevo antes de responder, ese es ahora el último y manda la
    regla de siempre contra él (lo anterior a su día lo reduce; lo del mismo
    día, según la respuesta).
    """
    fijo, ultimo = registro.ajuste(ajuste_id) if ajuste_id is not None else None, registro.ajuste()
    if ultimo is not None and (fijo is None or ultimo[1] > fijo[1]):
        _efecto_con_ajuste(registro, importacion_id, fila, efecto, ya_estaba)
    elif ya_estaba and fijo is not None:
        registro.reducir_ajuste(importacion_id, fijo[0].id, efecto.para(fijo[0].id))


def _candidato_automatico(registro: PersistenciaPreguntas, fila: c.FilaBanco, candidatos: Sequence[int],
                          *, dudoso_es_ninguno: bool = False) -> int | None:
    """Reevalúa candidatos libres sin convertir la respuesta al ajuste en un sí a una coincidencia.

    Exactos primero; un parecido solo con apoyo y sin ambigüedad (D38/D45).
    Los avisos ya confirmados con otra fila no se vuelven a usar.

    Si la coincidencia es dudosa, exige una elección explícita, salvo con
    ``dudoso_es_ninguno``: el dueño ya dijo que ninguno de los candidatos es
    esta fila (respondió "no" a "¿es el mismo?"), así que un aviso dudoso no
    se le asigna y la fila entra sin aviso.
    """
    libres = []
    for ident in candidatos:
        m = registro.movimiento_libre(ident)
        if m is not None:
            libres.append(m)
    plan = c.conciliar([fila], libres, fila.fecha - timedelta(days=1))
    if plan.preguntas:
        if dudoso_es_ninguno:
            return None
        raise ErrorConciliacion(MENSAJE_CANDIDATO)
    coincidencias = plan.confirmar + plan.corregir
    return coincidencias[0].movimiento_id if coincidencias else None


def _validar_ocurrencia_elegida(registro: PersistenciaPreguntas, pregunta, movimiento_id: int | None) -> None:
    """Dos ordinales de la misma identidad no pueden usar la misma fila."""
    if movimiento_id is None or pregunta.ocurrencia_banco is None:
        return
    for d in registro.elecciones():
        if (d.movimiento_id == movimiento_id and d.fecha == _fecha(pregunta.fecha)
                and d.monto_centavos == pregunta.monto_centavos and d.referencia == pregunta.referencia
                and d.ocurrencia_banco != pregunta.ocurrencia_banco):
            raise ErrorConciliacion(MENSAJE_CANDIDATO_USADO)


def _actualizar_preguntas_sin_candidatos(registro: PersistenciaPreguntas, pregunta) -> None:
    """La respuesta libera candidatos para las otras ocurrencias del grupo.

    Conserva pregunta/ordinal y sólo propone IDs. Cada lectura ve las reservas
    añadidas en esta misma transacción, sin ofrecer un ID a dos preguntas.
    """
    pendientes = registro.pendientes_sin_candidatos(pregunta)
    for p in pendientes:
        fila = c.FilaBanco(_fecha(p.fecha), p.monto_centavos, p.descripcion or "", p.referencia)
        estado = registro.leer_estado([fila])
        disponibles = [m for m in estado.movimientos if m.fecha >= estado.fecha_inicio]
        disponibles.extend(r.movimiento for r in estado.descartes if r.movimiento.fecha >= estado.fecha_inicio)
        elegidos = {e.movimiento_id for e in estado.elecciones if e.fecha == fila.fecha
                    and e.monto_centavos == fila.monto_centavos and e.referencia == fila.referencia}
        disponibles = [m for m in disponibles if m.id not in elegidos]
        for ident in c.candidatos_para_pregunta(fila, disponibles):
            registro.agregar_candidato(p.id, ident)


def _reubicar_avisos_sobrantes(registro: PersistenciaPreguntas, avisos: Sequence[int], usado: int | None) -> None:
    """Un aviso reservado en la pregunta recién respondida que no se usó vuelve a buscar su fila.

    Pasa cuando el dueño elige para la fila otro aviso de la misma identidad
    (dos cobros iguales del mismo día y sus dos avisos): el que sobra era de la
    otra fila. Si ya no espera en ninguna pregunta, se reserva en las que lo
    pueden ser, como si llegara ahora (D45), para que esa fila no se agregue
    aparte y el aviso quede contado dos veces.
    """
    for ident in sorted(set(avisos) - {usado}):
        m = registro.movimiento_libre(ident)
        if m is None or m.origen != c.ORIGEN_GMAIL or registro.reservado_en_pendientes(ident):
            continue
        preguntas = registro.preguntas_que_esperan_al_aviso(c.AvisoNuevo(m.fecha, m.tipo, m.monto_centavos, m.descripcion))
        if preguntas:
            registro.reservar(preguntas, ident)


class OperarPreguntas:
    def __init__(self, unidad: UnidadPreguntas):
        self._unidad = unidad

    def preguntas_pendientes(self) -> list[dict]:
        return self._unidad.preguntas.preguntas_pendientes()

    def responder_pregunta(
        self,
        pregunta_id: int,
        si: bool,
        movimiento_id: int | None = None,
        ya_estaba_en_ajuste: bool | None = None,
        *, ninguno: bool = False, transaccion_externa: bool = False,
    ) -> None:
        """Aplica la respuesta del dueño, en una sola transacción.

        * "¿es el mismo?" de una fila del banco: ``si`` -> el candidato
          (``movimiento_id``, obligatorio si hay varios) se confirma con el monto
          del banco; ``no`` -> si un aviso del correo llegó después y quedó
          reservado para esta fila y es ella sin duda (exacto, o parecido único
          con apoyo), se confirma con él; si no, la fila entra sin aviso. Si
          eso cambia el saldo en una fecha anterior al último ajuste, lo reduce;
          si es del mismo día, hace falta ``ya_estaba_en_ajuste``.
        * "¿es el mismo?" de un aviso del correo: ``si`` -> el movimiento del banco
          elegido queda confirmado con ese aviso; ``no`` -> el aviso se guarda como
          movimiento del correo.
        * "¿ya estaba en el saldo que ajustaste?": se aplica (corrige el candidato
          que elija el dueño con ``movimiento_id`` o, si no elige, el aviso tardío
          del monto exacto o un parecido único con apoyo; si la coincidencia es
          dudosa, exige elección explícita; si no hay candidatos libres, agrega
          la fila) y ``si`` reduce el ajuste. Con ``ninguno`` ("ninguno de
          estos", D50) la fila entra sola y los avisos siguen esperando.
        """
        registro = self._unidad.preguntas
        with nullcontext() if transaccion_externa else self._unidad.escritura(inmediata=True):
            p = registro.pregunta(pregunta_id)
            if p is None:
                raise ErrorConciliacion(MENSAJE_PREGUNTA_NO_EXISTE)
            candidatos = registro.candidatos(pregunta_id)
            ids = [mid for mid, _ in candidatos]
            avisos = {mid for mid, de_aviso in candidatos if de_aviso}
            importacion_id = p.importacion_id
            if ninguno and p.tipo != c.PREGUNTA_YA_ESTABA:
                raise ErrorConciliacion(MENSAJE_CANDIDATO)

            if p.fuente == "correo":
                if not registro.responder_correo(p, _elegir(ids, movimiento_id) if si else None):
                    return  # vuelve a preguntar, con otros candidatos
            else:
                fila = c.FilaBanco(_fecha(p.fecha), int(p.monto_centavos), str(p.descripcion), p.referencia)
                if p.tipo == c.PREGUNTA_YA_ESTABA:
                    # Un aviso tardío del monto exacto gana sobre la corrección de un
                    # parecido que había propuesto el motor (D38: exacto antes que
                    # parecido); ese parecido queda libre y, si el banco no lo trae,
                    # la próxima importación lo marca "no está en el banco".
                    if ninguno:  # "ninguno de estos": nunca se elige solo un aviso dudoso
                        if movimiento_id is not None:
                            raise ErrorConciliacion(MENSAJE_CANDIDATO)
                        objetivo = None
                    elif movimiento_id is not None:  # el dueño eligió cuál es
                        objetivo = _elegir(ids, movimiento_id)
                    else:
                        objetivo = _candidato_automatico(registro, fila, ids)
                    _validar_ocurrencia_elegida(registro, p, objetivo)
                    efecto = registro.aplicar_fila(importacion_id, fila, objetivo, objetivo in avisos)
                    _efecto_ya_estaba(registro, importacion_id, fila, efecto, si, p.ajuste_id)
                else:
                    if si:
                        objetivo = _elegir(ids, movimiento_id)
                    elif movimiento_id is not None:
                        objetivo = _elegir(sorted(avisos), movimiento_id)
                    else:
                        # "No" a "¿es el mismo?": solo un aviso reservado que es esta fila
                        # sin duda (exacto, o parecido único con apoyo) la confirma. Un aviso
                        # que se reservó aquí por ser parecido, sin apoyo, a esta fila y a
                        # la suya (preguntas_que_esperan_al_aviso) sigue esperando a la suya.
                        objetivo = _candidato_automatico(registro, fila, sorted(avisos), dudoso_es_ninguno=True)
                    _validar_ocurrencia_elegida(registro, p, objetivo)
                    efecto = registro.aplicar_fila(importacion_id, fila, objetivo, objetivo in avisos)
                    _efecto_con_ajuste(registro, importacion_id, fila, efecto, ya_estaba_en_ajuste)
            registro.registrar_respuesta(pregunta_id, si)
            if p.fuente == "banco" and p.ocurrencia_banco is not None:
                registro.guardar_eleccion(pregunta_id, efecto.movimiento_id)
            if p.fuente == "banco":
                _actualizar_preguntas_sin_candidatos(registro, p)
                _reubicar_avisos_sobrantes(registro, sorted(avisos), efecto.movimiento_id)


def _aplicar_fila(registro: PersistenciaPreguntas, importacion_id: int | None, fila: c.FilaBanco,
                  movimiento_id: int | None, de_aviso: bool = False) -> _Efecto:
    """Confirma con el monto del banco (si hay movimiento) o agrega la fila. Devuelve el efecto en el saldo."""
    if movimiento_id is None:
        nuevo = registro.agregar(importacion_id, fila)
        return _Efecto(fila.monto_centavos, movimiento_id=nuevo)
    if any(r.movimiento.id == movimiento_id for r in registro.reservas_descartes()):
        registro.confirmar_descarte(fila, movimiento_id, importacion_id)
        return _Efecto(0, movimiento_id=movimiento_id)
    actual = registro.fila_para_aplicar(movimiento_id)
    if actual is None or actual["borrado_en"] is not None:
        raise ErrorConciliacion(MENSAJE_CANDIDATO_USADO)
    if actual["fecha_banco"] is not None:
        # Las dudas de cobertura pueden ofrecer un respaldo activo conocido.
        if (_fecha(actual["fecha_banco"]) != fila.fecha or c.signo(actual["tipo"]) * actual["monto_centavos"] != fila.monto_centavos
                or actual["referencia"] and fila.referencia and actual["referencia"] != fila.referencia):
            raise ErrorConciliacion(MENSAJE_CANDIDATO_USADO)
        return _Efecto(0, movimiento_id=movimiento_id)
    diferencia = abs(fila.monto_centavos) - int(actual["monto_centavos"])
    registro.confirmar(importacion_id, fila, movimiento_id, corregir=diferencia != 0)
    signo = c.signo(actual["tipo"])
    if de_aviso:
        return _Efecto(signo * diferencia, movimiento_id, signo * int(actual["monto_centavos"]), movimiento_id)
    return _Efecto(signo * diferencia, movimiento_id=movimiento_id)


def _leido(p) -> _AvisoRespondido:
    return _AvisoRespondido(p.tipo_movimiento, int(p.monto_centavos), datetime.fromisoformat(str(p.fecha)),
                            str(p.descripcion), p.categoria_al_leer)


def _aviso(leido: _AvisoRespondido) -> c.AvisoNuevo:
    return c.AvisoNuevo(leido.fecha_hora.date(), leido.tipo, leido.monto_centavos, leido.descripcion)


def _recalcular_candidatos_de_correo(registro: PersistenciaPreguntas, pregunta_id: int, excluir: frozenset[int]) -> None:
    p = registro.pregunta(pregunta_id)
    if p is None:
        return
    accion, ids = registro.decidir_aviso(_aviso(_leido(p)), excluir)
    if accion in ("preguntar", "confirmar", "descartado"):
        for ident in ids:
            registro.agregar_candidato(pregunta_id, ident)


def _responder_correo(registro: PersistenciaPreguntas, p, elegido: int | None) -> bool:
    """Aplica la respuesta a "¿es el mismo?" de un aviso. Devuelve False si se vuelve a preguntar."""
    if elegido is not None:
        if any(r.movimiento.id == elegido for r in registro.reservas_descartes()):
            registro.vincular_descartado(elegido, p.gmail_id)
        elif not registro.vincular_extracto_activo(elegido, p.gmail_id):
            raise ErrorConciliacion(MENSAJE_CANDIDATO_USADO)
        # Si esa fila también se ofrecía en la pregunta de otro aviso (D50, caso
        # C), allí deja de ofrecerse: una fila nunca queda con dos avisos. Si esa
        # pregunta se queda sin candidatos, se recalculan con las reglas de
        # llegada (solo se proponen; nunca se empareja sin el dueño).
        for otra in registro.quitar_candidato_de_otras_preguntas_de_correo(elegido, p.id):
            _recalcular_candidatos_de_correo(registro, otra, frozenset({elegido}))
        return True
    # No es el mismo. Antes de guardarlo, las mismas reglas que al llegar (D45),
    # sin los candidatos que el dueño descartó y respetando los descartes:
    # * si mientras esperaba entró del banco la fila que sí es este aviso (por
    #   ejemplo, al responder "no" a la pregunta de esa fila), la confirma;
    # * si queda otro candidato dudoso que no se le había mostrado, se vuelve a
    #   preguntar (D50, caso D). Los candidatos ya rechazados se conservan en la
    #   pregunta: son el historial de lo que el dueño dijo que no es, y nunca se
    #   vuelven a emparejar solos. Cada vuelta agrega algo nuevo, así termina;
    # * si no, se guarda como cualquier otro, con sus reglas, y si es de una fila
    #   del banco que espera respuesta queda reservado para ella. La pregunta
    #   conserva el gmail_id (único en su tabla) como constancia.
    leido = _leido(p)
    aviso = _aviso(leido)
    rechazados = frozenset(mid for mid, _ in registro.candidatos(p.id))
    accion, ids = registro.decidir_aviso(aviso, rechazados)
    if accion == "descartado":
        registro.vincular_descartado(ids[0], p.gmail_id)
        return True
    if accion == "confirmar" and registro.vincular_extracto_activo(ids[0], p.gmail_id):
        return True
    if accion == "preguntar":
        nuevos = [i for i in ids if i not in rechazados]
        if nuevos:
            for ident in nuevos:
                registro.agregar_candidato(p.id, ident)
            return False
    preguntas = ids if accion == "en_pregunta" else registro.preguntas_que_esperan_al_aviso(aviso)
    registro.reservar(preguntas, registro.guardar_aviso(p.gmail_id, leido))
    return True
