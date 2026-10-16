"""Diario y huellas deterministas de fotografías, sin persistencia ni SQL."""
import hashlib
import json
from collections.abc import Sequence
from .contratos import TablaDiario

def _json(valor):
    return json.dumps(valor, sort_keys=True, separators=(",", ":"), ensure_ascii=False)



def _clave(tabla: TablaDiario, fila):
    return {nombre: fila[nombre] for nombre in tabla.clave_primaria}


def huella_de_foto(foto):
    return hashlib.sha256(_json(foto).encode()).hexdigest()

def diario(antes, despues, tablas: Sequence[TablaDiario]):
    cambios = []
    for tabla in tablas:
        anterior = {_json(_clave(tabla, f)): f for f in antes[tabla.nombre]}
        posterior = {_json(_clave(tabla, f)): f for f in despues[tabla.nombre]}
        for clave in sorted(anterior.keys() | posterior.keys()):
            a, d = anterior.get(clave), posterior.get(clave)
            if a != d:
                cambios.append({"tabla": tabla.nombre, "clave": json.loads(clave), "antes": a, "despues": d})
    return cambios


def _componer(original, nuevo, tablas: Sequence[TablaDiario]):
    combinados = { (c["tabla"], _json(c["clave"])): dict(c) for c in original}
    for cambio in nuevo:
        clave = (cambio["tabla"], _json(cambio["clave"]))
        previo = combinados.get(clave)
        if previo is None:
            combinados[clave] = dict(cambio)
        elif previo["despues"] == cambio["antes"]:
            previo["despues"] = cambio["despues"]
        else:
            # Algo ajeno cambió la fila entre importación y respuesta:
            # conserva la expectativa anterior para que deshacer dé 409.
            return original
    orden = {t.nombre: i for i, t in enumerate(tablas)}
    return sorted(combinados.values(), key=lambda c: orden[c["tabla"]])
