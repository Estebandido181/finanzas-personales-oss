"""Huella estable del registro y signo del monto; sin persistencia."""
import hashlib
import json


def _huella(fila):
    return hashlib.sha256(json.dumps(fila, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode()).hexdigest()


def _firmado(fila):
    return fila["monto_centavos"] if fila["tipo"] == "ingreso" else -fila["monto_centavos"]


def _huella_contexto(fila):
    # Solo estos campos pueden cambiar por confirmación del banco/aviso.
    # Categoría, fecha/hora, origen, borrado y reglas siguen protegidos.
    financieros = {"monto_centavos", "estado", "fecha_banco", "referencia", "gmail_id", "no_en_banco"}
    return _huella({k: v for k, v in fila.items() if k not in financieros})
