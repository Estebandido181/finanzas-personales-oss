"""Comparación efímera con una referencia manual, sin corregir el saldo.

Los snapshots del preview se conservan solo con su token en RAM. La hora
representa la recepción/comprobación del servidor, nunca una consulta al banco.
"""

from finanzas.modulos.saldo.politica import TIPO_INGRESO, TIPO_AJUSTE, TIPOS_GASTO, MAXIMO_CENTAVOS
from finanzas.modulos.saldo.contratos import ErrorSaldo




def cobertura(desde=None, hasta=None, *, proteccion=False, huecos=()):
    # "archivos_de_120_filas" queda en el contrato, siempre nulo: el tope de filas
    # del banco no se conoce (D51) y contar archivos de 120 no dice nada.
    return {"desde": desde, "hasta": hasta, "archivos_de_120_filas": None,
        "proteccion_ausencias_conservadora": proteccion,
        "cobertura_verificada": False, "cobertura_hasta_consulta_verificada": False,
        "huecos": list(huecos),
        "advertencia": "El reporte sólo indica días, no acredita que estén todos los movimientos ni que cubra hasta la hora de esta comprobación. Coincidir en saldo no verifica la cobertura."}


def _efecto(fila, configuracion):
    if fila is None or configuracion is None or fila["borrado_en"] is not None:
        return 0
    if fila["fecha_hora"] < configuracion["fecha_inicio"][:10] + "T00:00:00":
        return 0
    if fila["tipo"] in (TIPO_INGRESO, TIPO_AJUSTE):
        return fila["monto_centavos"]
    if fila["tipo"] in TIPOS_GASTO:
        return -fila["monto_centavos"]
    return 0


def preparar(antes, despues, pendientes, cobertura_reporte, *, origen="actual", fotos=None):
    contribuciones = None
    if fotos is not None:
        anterior, posterior = fotos
        conf_antes = next(iter(anterior["configuracion_saldo"]), None)
        conf_despues = next(iter(posterior["configuracion_saldo"]), None)
        contribuciones = {"agregados_centavos": 0, "corregidos_centavos": 0,
            "ajustes_centavos": 0, "cambio_inicial_centavos":
            despues["saldo_inicial_centavos"] - (antes["saldo_inicial_centavos"] if antes else 0),
            "otros_centavos": 0}
        a = {f["id"]: f for f in anterior["movimientos"]}
        d = {f["id"]: f for f in posterior["movimientos"]}
        for ident in a.keys() | d.keys():
            viejo, nuevo = a.get(ident), d.get(ident)
            efecto = _efecto(nuevo, conf_despues) - _efecto(viejo, conf_antes)
            if (nuevo or viejo)["tipo"] == TIPO_AJUSTE:
                clave = "ajustes_centavos"
            elif viejo is None:
                clave = "agregados_centavos"
            elif nuevo is not None and (viejo["monto_centavos"], viejo["tipo"]) != (nuevo["monto_centavos"], nuevo["tipo"]):
                clave = "corregidos_centavos"
            else:
                # P. ej. movimientos existentes que entran al extender la
                # fecha. Su efecto se mide, sin adjudicar una causa bancaria.
                clave = "otros_centavos"
            contribuciones[clave] += efecto
        previo = antes["saldo_centavos"] if antes else 0
        if previo + sum(contribuciones.values()) != despues["saldo_centavos"]:
            raise RuntimeError("El desglose de la comprobación no coincide.")
    return {"origen": origen, "desglose_antes": antes, "desglose_despues": despues,
        "contribuciones": contribuciones, "pendientes": pendientes, "cobertura": cobertura_reporte}


def comparar(snapshot, saldo_real_centavos, huella, *, recibido_en: str):
    if type(saldo_real_centavos) is not int or not 0 <= saldo_real_centavos <= MAXIMO_CENTAVOS:
        raise ErrorSaldo("Escribe un saldo válido en centavos enteros.")
    antes, despues = snapshot["desglose_antes"], snapshot["desglose_despues"]
    calculado = despues["saldo_centavos"] if despues else None
    diferencia = None if calculado is None else saldo_real_centavos - calculado
    return {**snapshot, "estado": "disponible" if despues else "sin_configuracion",
        "saldo_real_centavos": saldo_real_centavos, "saldo_app_centavos": calculado,
        "diferencia_centavos": diferencia, "coincide": None if diferencia is None else diferencia == 0,
        "recibido_en": recibido_en,
        "huella": huella, "verificacion_independiente": despues is not None and snapshot["origen"] != "arranque",
        "diferencia_forzada_por_inicial": snapshot["origen"] == "arranque" and diferencia == 0,
        "saldo_antes_centavos": antes["saldo_centavos"] if antes else None,
        "saldo_despues_centavos": calculado,
        "efecto_conciliacion_centavos": calculado - antes["saldo_centavos"] if antes and despues else None,
        "resto_no_explicado_centavos": diferencia}
