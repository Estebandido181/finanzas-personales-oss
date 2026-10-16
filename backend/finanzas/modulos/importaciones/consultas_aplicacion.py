"""Detalle, recordatorio y guardas de reversión sobre datos primitivos."""
from datetime import datetime, timezone
import json
from finanzas.modulos.saldo.publico import TiempoSaldo
from .contratos import MENSAJE_REVERSION
from .diferencias_aplicacion import _grupos

def _deshacible(registro, f):
    if f["deshecha_en"]:
        return False, "Esta importación ya se deshizo."
    rev = registro.reversion(f["id"])
    posterior = registro.importacion_posterior(f["id"])
    if rev is None:
        return False, "Esta importación no tiene un registro de reversión compatible."
    ajuste_posterior = registro.ajuste_posterior(rev["ultimo_movimiento_id"])
    # Restituir la fecha antigua o quitar una configuración nueva puede
    # dejar fuera movimientos posteriores ajenos. Es un conflicto explícito.
    arranque_posterior = rev["arranque"] is not None and registro.movimiento_posterior(rev["ultimo_movimiento_id"])
    ajustes_esperados = json.loads(rev["conteos"]).get("_ajustes")
    cambios = json.loads(rev["diario"])
    # Un ciclo reversible deja rastro aunque la fila vuelva a estar activa.
    # Los diarios antiguos no conocen esa reserva; no deben modificarla.
    ids = [c["clave"]["id"] for c in cambios if c["tabla"] == "movimientos"]
    propias = {c["clave"]["id"] for c in cambios if c["tabla"] == "descartes_movimientos"}
    conflicto_reservas = registro.reservas_ajenas(ids, propias)
    if posterior or ajuste_posterior or arranque_posterior or conflicto_reservas or (ajustes_esperados is not None and ajustes_esperados != registro.ajustes()) or not registro.coincide(cambios) or registro.hijos_ajenos(cambios):
        return False, MENSAJE_REVERSION
    return True, None


def _hora_importacion_colombia(valor, tiempo: TiempoSaldo):
    # AhoraIso guarda UTC sin zona; el contrato y el recordatorio usan Colombia.
    return tiempo.a_hora(datetime.fromisoformat(valor).replace(tzinfo=timezone.utc))


def _detalle(registro, ident, tiempo: TiempoSaldo):
    f = registro.registro(ident)
    rev = registro.reversion(ident)
    puede, motivo = _deshacible(registro, f)
    grupos = [] if f["deshecha_en"] else _grupos(registro.filas_sin_categoria(ident))
    preguntas, no_banco = registro.pendientes(), registro.no_banco()
    resumen = {k: v for k, v in json.loads(rev["conteos"]).items() if not k.startswith("_")} if rev else {
        **{k: f[k] for k in ("filas", "ya_estaban", "confirmados", "corregidos", "agregados", "no_en_banco", "anteriores", "sin_formato")},
        "ya_preguntadas": 0, "preguntas_es_el_mismo": f["preguntas"], "preguntas_ajuste": 0, "ajuste_reducido": False}
    return {"id": f["id"], "hecha_en": _hora_importacion_colombia(f["hecha_en"], tiempo).isoformat(timespec="seconds"), "deshecha_en": f["deshecha_en"],
        "resumen": resumen, "reporte": {"desde": f["desde"], "hasta": f["hasta"], "dia_incompleto": bool(f["filas"])},
        "saldo_centavos": registro.saldo_actual() if registro.configuracion() else None, "se_puede_deshacer": puede, "motivo_no_deshacer": motivo,
        "sin_categoria": sum(g["cuantos"] for g in grupos), "grupos": grupos,
        "preguntas_pendientes": preguntas, "no_en_banco_pendientes": no_banco,
        "siguiente": "categorizar" if grupos else "diferencias" if preguntas or no_banco else "inicio",
        "todo_resuelto": not grupos and preguntas == 0 and no_banco == 0,
        "puede_extender_historial": not bool(f["deshecha_en"]) and registro.ofrecer_extender_historial(
            resumen["anteriores"], f["desde"])}


def _estado(registro, tiempo: TiempoSaldo):
    f = registro.ultima_importacion_activa()
    conf = registro.configuracion()
    inicio = conf.fecha_inicio if conf else tiempo.hoy()
    rev = registro.reversion(f["id"]) if f else None
    ident = rev["ultimo_movimiento_id"] if rev else 0
    cuantos = registro.movimientos_desde(ident)
    desde = _hora_importacion_colombia(f["hecha_en"], tiempo).date() if f else inicio
    semanas = max(0, (tiempo.hoy() - desde).days // 7)
    preguntas, no_banco = registro.pendientes(), registro.no_banco()
    return {"ultima_id": f["id"] if f else None, "mostrar_recordatorio": conf is not None and (cuantos >= 100 or semanas >= 4),
        "movimientos_desde_ultima": cuantos, "semanas_desde_ultima": semanas,
        "preguntas_pendientes": preguntas, "no_en_banco_pendientes": no_banco,
        "sin_categoria": registro.contar_sin_categorizar(), "importacion_pendiente": preguntas > 0 or no_banco > 0}
