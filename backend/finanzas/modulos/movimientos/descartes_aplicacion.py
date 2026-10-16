"""Descarte reversible sobre puertos; no decide identidad ni emparejamientos."""
from datetime import date
import re
from typing import Callable

from finanzas.modulos.movimientos.descartes_contratos import (
    ContextoSaldoDescartes, DescarteNoPermitido, RepositorioDescartes, TransaccionDescartes,
)
from finanzas.modulos.movimientos.descartes_politica import _firmado, _huella, _huella_contexto


class OperarDescartes:
    def __init__(self, registro: RepositorioDescartes, saldo: ContextoSaldoDescartes,
                 unidad: TransaccionDescartes, ahora: Callable[[], str]):
        self._registro, self._saldo, self._unidad, self._ahora = registro, saldo, unidad, ahora

    def motivo_base(self, fila: dict) -> str | None:
        if fila["origen"] not in ("gmail", "extracto") or fila["tipo"] not in ("ingreso", "compra", "transferencia"):
            return "Solo se pueden descartar o restaurar movimientos automáticos."
        inicio = self._saldo.fecha_inicio()
        if inicio is None:
            return "Configura el saldo y la fecha de inicio antes de revisar este movimiento."
        if fila["fecha_hora"][:10] < inicio.isoformat():
            return "El movimiento es anterior a la fecha de inicio."
        if self._registro.ajuste_posterior(fila["id"]):
            return "Hay un ajuste posterior que protege este movimiento."
        if self._registro.pregunta_pendiente(fila["id"]):
            return "Responde primero la pregunta pendiente de este movimiento."
        return None

    def estado(self, fila: dict) -> dict:
        activo = self._registro.activo(fila["id"])
        base = self.motivo_base(fila)
        descarte = base or ("El movimiento ya está descartado." if activo else
            "Este movimiento ya fue borrado por otra acción." if fila["borrado_en"] else None)
        restaurar = base or ("El movimiento no está descartado." if not activo else
            "El movimiento cambió después del descarte." if _huella(fila) != activo["huella_movimiento"] else None)
        return dict(descartado=activo is not None, puede_descartar=descarte is None,
                    motivo_no_descartar=descarte, puede_restaurar=restaurar is None, motivo_no_restaurar=restaurar)

    def elegibilidad(self, ident: int) -> dict:
        return self.estado(self._registro.movimiento(ident))

    def cambiar(self, ident: int, *, restaurar: bool = False) -> dict:
        with self._unidad.escritura(inmediata=True):
            fila, activo = self._registro.movimiento(ident), self._registro.activo(ident)
            antes = self._saldo.saldo_actual() if self._saldo.fecha_inicio() is not None else None
            estado = self.estado(fila)
            hubo = self._registro.hubo(ident)
            repetido = (not restaurar and activo is not None) or (
                restaurar and activo is None and hubo and fila["borrado_en"] is None)
            if not repetido:
                motivo = estado["motivo_no_restaurar" if restaurar else "motivo_no_descartar"]
                if motivo:
                    raise DescarteNoPermitido(motivo)
                ahora = self._ahora()
                self._registro.marcar_borrado(ident, None if restaurar else ahora)
                if restaurar:
                    self._registro.marcar_restaurado(activo["id"], ahora)
                else:
                    fila = self._registro.movimiento(ident)
                    self._registro.guardar_reserva(dict(
                        movimiento_id=ident, descartado_en=ahora, fecha=fila["fecha_hora"][:10],
                        monto_centavos=_firmado(fila), referencia=fila["referencia"], fecha_banco=fila["fecha_banco"],
                        monto_banco_centavos=_firmado(fila) if fila["fecha_banco"] else None,
                        referencia_banco=fila["referencia"] if fila["fecha_banco"] else None,
                        huella_movimiento=_huella(fila), huella_contexto=_huella_contexto(fila)))
            fila = self._registro.movimiento(ident)
            return dict(movimiento_id=ident, saldo_antes_centavos=antes,
                        saldo_despues_centavos=self._saldo.saldo_actual() if antes is not None else None,
                        monto_centavos=fila["monto_centavos"], **self.estado(fila))

    def listar(self) -> dict:
        with self._unidad.lectura():
            return {"movimientos": [dict(id=f["id"], descarte_id=f["descarte_id"],
                fecha_hora=f["fecha_hora"], tipo=f["tipo"], descripcion=f["descripcion"],
                monto_centavos=f["monto_centavos"], origen=f["origen"], referencia=f["referencia"],
                descartado_en=f["descartado_en"], **self.estado(self._registro.movimiento(f["id"])))
                for f in self._registro.movimientos_descartados()]}

    def listar_reservas(self) -> list[dict]:
        reservas = []
        for f in self._registro.reservas_activas():
            movimiento = self._registro.movimiento(f["movimiento_id"])
            banco = None if f["fecha_banco"] is None else dict(fecha=f["fecha_banco"],
                monto_centavos=f["monto_banco_centavos"], referencia=f["referencia_banco"])
            reservas.append(dict(movimiento=movimiento, banco=banco, gmail_id=movimiento["gmail_id"]))
        return reservas

    def actualizar_respaldo_banco(self, ident: int, *, fecha: date, monto_centavos: int, referencia: str | None) -> None:
        if not self._unidad.en_transaccion():
            raise ValueError("El respaldo requiere la transacción de confirmación.")
        if type(monto_centavos) is not int or not 0 < abs(monto_centavos) <= self._saldo.maximo_centavos:
            raise ValueError("Monto de respaldo inválido.")
        if type(fecha) is not date or (referencia is not None and not re.fullmatch(r"\*[0-9]{4}", referencia)):
            raise ValueError("Respaldo normalizado inválido.")
        activo, movimiento = self._registro.activo(ident), self._registro.movimiento(ident)
        if activo is None or movimiento["borrado_en"] is None or movimiento["fecha_banco"] != fecha.isoformat() or _firmado(movimiento) != monto_centavos or movimiento["referencia"] != referencia or _huella_contexto(movimiento) != activo["huella_contexto"]:
            raise DescarteNoPermitido("El respaldo no coincide con el movimiento descartado confirmado.")
        self._registro.actualizar_respaldo(activo["id"], dict(fecha_banco=fecha.isoformat(),
            monto_banco_centavos=monto_centavos, referencia_banco=referencia, huella_movimiento=_huella(movimiento)))
