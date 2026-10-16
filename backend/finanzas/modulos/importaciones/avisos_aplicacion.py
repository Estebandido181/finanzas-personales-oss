"""Incorporación de avisos: decisiones por motor puro y persistencia por puerto.

Participante de la transacción de Sincronización o del flujo de respuestas;
nunca abre ni confirma una transacción propia.
"""
from __future__ import annotations
from dataclasses import replace
from . import motor as c
from .contratos import (AvisoNormalizado, PersistenciaAvisos, AVISO_NUEVO, AVISO_CONFIRMO,
    AVISO_DESCARTADO, AVISO_YA_ESTABA, AVISO_PREGUNTA, AVISO_EN_PREGUNTA)

def _ids(decision: c.DecisionAviso) -> tuple[int, ...]:
    return (decision.movimiento_id,) if decision.accion == "confirmar" else decision.candidatos



class OperarAvisos:
    def __init__(self, registro: PersistenciaAvisos):
        self._registro = registro

    def preguntas_que_esperan_al_aviso(self, aviso: c.AvisoNuevo) -> tuple[int, ...]:
        """Ids de las preguntas del banco sin responder cuya fila puede ser este aviso.

        Primero las filas que todavía no tienen un aviso reservado: con dos filas
        iguales y sus dos avisos, cada aviso queda con una (repeticiones, D38).
        Si entre ellas no hay una segura, se reserva en todas las que pueden ser,
        también las que ya tienen otro aviso (D50, caso C): esconder una deja
        al dueño sin la opción correcta.
        """
        con_aviso = self._registro.preguntas_con_aviso()
        filas = [replace(f, reservado=f.id in con_aviso) for f in self._registro.filas_que_esperan(aviso.fecha)]
        decision = c.emparejar_aviso(aviso, filas)
        if decision.accion == "confirmar":
            return _ids(decision)
        todas = c.emparejar_aviso(aviso, [replace(f, reservado=False) for f in filas])
        ids = set() if decision.accion == "nuevo" else set(_ids(decision))
        if todas.accion != "nuevo":
            ids |= set(_ids(todas))
        return tuple(sorted(ids))

    def incorporar_aviso(self, gmail_id: str, movimiento: AvisoNormalizado) -> str:
        """Antes de guardar un aviso: ¿ya entró, o espera, del banco? (D45).

        Se llama dentro de la transacción de la sincronización. Mismas reglas de
        emparejamiento que la importación (día ±1, monto, destino, repeticiones).
        Devuelve:

        * ``"confirmado"``: lo que entró del banco sin aviso queda confirmado con
          este ``gmail_id`` (no se crea otro movimiento);
        * ``"pregunta"``: hay duda (monto parecido sin apoyo, varios candidatos, o
          el único candidato ya está en otra pregunta); el aviso espera en una
          pregunta "¿es el mismo?" sin mover el saldo;
        * ``"en_pregunta"``: coincide con una fila del banco que espera respuesta;
          el aviso se guarda (es real) y queda como candidato reservado de esa
          pregunta, así al responder se confirma con él en vez de agregar la fila
          otra vez;
        * ``"ya_estaba"``: este ``gmail_id`` ya está registrado o espera en una
          pregunta;
        * ``"nuevo"``: no hay nada del banco que sea este aviso; se guarda como
          siempre (lo hace quien llama).
        """
        if not self._registro.admite_conciliacion():  # base sin la 0008
            return AVISO_NUEVO
        if self._registro.ya_registrado(gmail_id):
            return AVISO_YA_ESTABA
        fecha = movimiento.fecha_hora.date()
        aviso = c.AvisoNuevo(fecha, movimiento.tipo, movimiento.monto_centavos, movimiento.descripcion)
        accion, ids = self.decidir(aviso)
        if accion == "descartado":
            self._registro.vincular_descarte(ids[0], gmail_id)
            return AVISO_DESCARTADO
        if accion == "confirmar":
            self._registro.confirmar(ids[0], gmail_id)
            return AVISO_CONFIRMO
        if accion == "preguntar":
            self._registro.preguntar(gmail_id, movimiento, ids)
            return AVISO_PREGUNTA
        if accion == "en_pregunta":
            self._registro.reservar(ids, self._registro.guardar(gmail_id, movimiento))
            return AVISO_EN_PREGUNTA
        return AVISO_NUEVO

    def decidir(self, aviso: c.AvisoNuevo, excluir: frozenset[int] = frozenset()) -> tuple[str, tuple[int, ...]]:
        """Qué hacer con un aviso, sin escribir nada (D45, D50).

        ``excluir``: movimientos que el dueño ya dijo que no son este aviso.
        Devuelve ``(acción, ids)``: ``descartado``/``confirmar`` con el
        movimiento; ``preguntar`` con los candidatos; ``en_pregunta`` con las
        preguntas del banco donde reservarlo; ``nuevo`` sin ids.
        """
        reservados = self._registro.reservados()
        cercanos = [m for m in self._registro.cercanos(aviso.fecha, reservados) if m.id not in excluir]
        reservas = [r for r in self._registro.reservas(reservados) if r.movimiento.id not in excluir]

        def puede_ser(m: c.MovimientoApp) -> bool:
            return c.emparejar_aviso(aviso, [replace(m, reservado=False)]).accion != "nuevo"

        # Lo que podría ser pero está reservado por otra pregunta (D50, caso C):
        # se muestra junto con lo libre, en vez de esconderlo.
        reservados_posibles = tuple(
            m.id for m in cercanos + [r.movimiento for r in reservas if r.gmail_id is None and r.banco is not None]
            if m.reservado and puede_ser(m)
        )

        # 1. Lo que entró del banco sin aviso y está libre.
        decision = c.emparejar_aviso(aviso, cercanos, reservas)
        if decision.accion == "descartado":
            return "descartado", (decision.movimiento_id,)
        if decision.accion == "confirmar":
            elegido = next((m for m in cercanos if m.id == decision.movimiento_id), None)
            exacto = elegido is None or elegido.monto_centavos == aviso.monto_centavos
            if exacto or not reservados_posibles:
                return "confirmar", (decision.movimiento_id,)
            # Un parecido libre no gana sola a otra fila posible que está reservada.
            return "preguntar", tuple(sorted({decision.movimiento_id, *reservados_posibles}))
        if decision.accion == "preguntar":
            return "preguntar", tuple(sorted(set(decision.candidatos) | set(reservados_posibles)))

        # Una sombra reservada no se convierte en un aviso nuevo mientras espera.
        # Preguntar antes del camino que añade candidatos evita mover el saldo.
        sombras_reservadas = [r.movimiento for r in reservas if r.movimiento.reservado
                             and r.gmail_id is None and r.banco is not None]
        posibles_sombras = tuple(m.id for m in sombras_reservadas if puede_ser(m))
        if posibles_sombras:
            otros = tuple(m.id for m in cercanos if m.reservado and puede_ser(m))
            return "preguntar", tuple(sorted(posibles_sombras + otros))

        # Una fila que entró sin aviso, del monto exacto, reservada por otra
        # pregunta: se pregunta con ella (y las demás reservadas posibles) antes
        # de reservar el aviso en una fila que espera. Si no es ninguna, el "no"
        # vuelve a aplicar estas reglas (caso D) y llega a la fila que espera;
        # reservado en esa fila, en cambio, ya no podría volver a la que entró.
        cercanos_reservados = {m.id: m for m in cercanos if m.reservado}
        if any(i in cercanos_reservados and cercanos_reservados[i].monto_centavos == aviso.monto_centavos
               for i in reservados_posibles):
            return "preguntar", reservados_posibles

        # 2. Filas del banco que esperan respuesta: el aviso se guarda y se reserva.
        preguntas = self.preguntas_que_esperan_al_aviso(aviso)
        if preguntas:
            return "en_pregunta", preguntas

        # 3. Lo que podría ser ya está reservado por otra pregunta: se pregunta,
        #    ofreciendo TODOS los que podrían ser (no solo el mejor), para que el
        #    dueño pueda elegir el que quede libre.
        if reservados_posibles:
            return "preguntar", reservados_posibles
        return "nuevo", ()
