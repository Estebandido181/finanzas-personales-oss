"""Consultas y sugerencias de diferencias por puertos, sin SQL ni lectores."""
from finanzas.modulos.categorias import publico as cat
from finanzas.modulos.saldo import publico as saldo
from finanzas.modulos.movimientos.publico import DescarteNoPermitido
from .contratos import ErrorConciliacion, PersistenciaDiferencias, UnidadDiferencias

def _grupos(filas):
    grupos = {}
    for f in filas:
        clave = cat.clave_grupo(f["tipo"], f["descripcion"])
        if clave is None:
            clave = f'sin-descripcion:{f["id"]}'
        grupos.setdefault(clave, []).append(f)
    salida = []
    for clave, miembros in grupos.items():
        f = miembros[0]
        texto = cat.normalizar(f["descripcion"])
        modos = (("empieza_por", "Empieza por"), ("contiene", "Contiene"), ("exacta", "Es igual a")) if all(m["origen"] == "extracto" for m in miembros) else (("exacta", "Es igual a"),)
        salida.append({"clave": clave, "tipo": f["tipo"], "descripcion": f["descripcion"],
            "clase_categoria": cat.clase_para_tipo(f["tipo"]), "cuantos": len(miembros),
            "suma_centavos": sum(m["monto_centavos"] for m in miembros), "ids": [m["id"] for m in miembros],
            "desde": min(str(m["fecha_banco"] or m["fecha_hora"])[:10] for m in miembros),
            "hasta": max(str(m["fecha_banco"] or m["fecha_hora"])[:10] for m in miembros),
            "es_gasto": f["tipo"] in saldo.TIPOS_GASTO,
            "regla": {"tipo_movimiento": f["tipo"], "campo": cat.campo_para_tipo(f["tipo"]), "condiciones": "texto",
                "texto": texto, "monto_centavos": None, "frase": cat.frase_condiciones(cat.campo_para_tipo(f["tipo"]), f["descripcion"])} if texto else None,
            "reglas_propuestas": [{"modo": modo, "texto": texto, "frase": f'{etiqueta} «{f["descripcion"]}»'}
                for modo, etiqueta in modos] if texto else []})
    return sorted(salida, key=lambda g: (-g["cuantos"], g["clave"]))


def _dato(f, *, es_pregunta=False):
    monto = int(f["monto_centavos"])
    tipo = f.get("tipo_movimiento") if es_pregunta else f["tipo"]
    if es_pregunta and tipo is None:
        tipo = "ingreso" if monto > 0 else "transferencia" if f["referencia"] else "compra"
    fecha = str(f["fecha"] if es_pregunta else f["fecha_hora"])
    return {"id": None if es_pregunta else f["id"], "descripcion": f["descripcion"], "tipo": tipo,
        "origen": ("extracto" if f["fuente"] == "banco" else "gmail") if es_pregunta else f["origen"],
        "monto_centavos": abs(monto) if tipo != "ajuste" else monto,
        "fecha_hora": fecha if "T" in fecha else fecha + "T00:00:00",
        "destino_ultimos4": f.get("referencia"),
        "descartado": bool(f.get("descartado", False)),
        "nota_descartado": "Sigue descartado; confirmar no lo devuelve al saldo." if f.get("descartado", False) else None}


def _identificaciones(candidatos):
    """Identidad legible, sin convertir los ids técnicos en textos de selección."""
    montos = [abs(int(c["monto_centavos"])) for c in candidatos]
    textos = []
    for c, monto in zip(candidatos, montos):
        texto = cat.pesos(monto)
        if montos.count(monto) > 1:
            fecha = str(c["fecha_hora"])
            texto += f' · {c["descripcion"] or "Sin descripción"} · {fecha[:10]}'
            if c["origen"] != "extracto" and "T" in fecha:
                texto += f" a las {fecha[11:16]}"
            if c["referencia"]:
                texto += f' · destino {c["referencia"]}'
        if c.get("descartado", False):
            texto += " · descartado"
        textos.append(texto)
    etiquetas = [f"Candidato {i + 1}" if textos.count(t) > 1 else None for i, t in enumerate(textos)]
    return {c["id"]: (f"{t} · {etiqueta}" if etiqueta else t, etiqueta)
            for c, t, etiqueta in zip(candidatos, textos, etiquetas)}


def _preguntas(registro: PersistenciaDiferencias):
    salida, respuestas = [], {}
    for p in registro.preguntas_pendientes():
        candidatos = registro.candidatos(p["id"])
        for candidato in candidatos:
            candidato["descartado"] = candidato["borrado_en"] is not None and candidato["reserva_activa"]
        # Un candidato borrado por otro flujo no puede aparecer como opción.
        ids = [candidato["id"] for candidato in candidatos]
        por_id = {candidato["id"]: candidato for candidato in candidatos}
        identificaciones = _identificaciones(candidatos)
        ajuste = registro.ajuste(p["ajuste_id"])
        opciones, parametrizaciones = [], {}
        ultimo = registro.ultimo_ajuste()
        del_dia = p["fuente"] == "banco" and ultimo and str(p["fecha"])[:10] == ultimo[0].fecha.isoformat()
        if p["tipo"] == "ya_estaba_en_ajuste":
            posibles = [(si, mid, None, False) for mid in [None, *ids] for si in (True, False)]
        else:
            posibles = [(True, mid, ya, False) for mid in ids for ya in ((True, False) if del_dia else (None,))]
            posibles += [(False, None, ya, False) for ya in ((True, False) if del_dia else (None,))]
        for si, mid, ya, ninguno in posibles:
            clave = ("si" if si else "no") + (f":{mid}" if mid is not None else "") + (":ninguno" if ninguno else "") + (":ajuste_si" if ya is True else ":ajuste_no" if ya is False else "")
            try:
                efecto = registro.simular_respuesta(p, si, mid, ya, ninguno)
            except (ErrorConciliacion, DescarteNoPermitido):
                # "¿Ya estaba en el saldo?" sin elegir y con un candidato dudoso: no se
                # elige solo; se ofrece "ninguno de estos" (D50, caso B).
                if p["tipo"] == "ya_estaba_en_ajuste" and mid is None and not ninguno and ids:
                    posibles.append((si, None, None, True))
                continue
            if p["tipo"] == "ya_estaba_en_ajuste":
                etiqueta = "Ya estaba en mi saldo" if si else "No estaba en mi saldo"
                if mid is not None:
                    etiqueta += f": el de {identificaciones[mid][0]}"
                elif ninguno:
                    etiqueta += ": no es ninguno de estos avisos"
            elif si:
                monto_banco = p["monto_centavos"] if p["fuente"] == "banco" else candidatos[0]["monto_centavos"]
                etiqueta = f'Es el mismo: quedarse con {cat.pesos(abs(int(monto_banco)))}' if len(candidatos) == 1 else f"Es el de {identificaciones[mid][0]}"
            else:
                etiqueta = "Son distintos: conservar lo descartado y registrar este movimiento" if any(c["descartado"] for c in candidatos) else "Son distintos: dejar los dos"
            if ya is not None:
                etiqueta += "; ya estaba en el saldo del ajuste" if ya else "; no estaba en el saldo del ajuste"
            consecuencia = "El saldo no cambia." if efecto == 0 else f'El saldo {"sube" if efecto > 0 else "baja"} {cat.pesos(abs(efecto))}.'
            if si and mid is not None and por_id[mid]["descartado"]:
                consecuencia = "Sigue descartado; confirmar no lo devuelve al saldo. " + consecuencia
            opciones.append({"id": clave, "texto": etiqueta, "consecuencia": consecuencia})
            parametrizaciones[clave] = (si, mid, ya, ninguno)
        respuestas[p["id"]] = parametrizaciones
        diferencia = abs(abs(int(p["monto_centavos"])) - int(candidatos[0]["monto_centavos"])) if len(candidatos) == 1 else None
        tipo = "mismo_dia_ajuste" if p["tipo"] == "ya_estaba_en_ajuste" or del_dia else "varios_candidatos" if len(candidatos) > 1 else "monto_parecido"
        sugerencia = {"opcion": None, "motivo": "No hay una pista clara: elige tú.",
            "analisis": "El banco no trae la hora del movimiento." if tipo == "mismo_dia_ajuste" else
            "Los datos disponibles no permiten confirmar una coincidencia sin tu decisión."}
        if tipo == "monto_parecido" and len(candidatos) == 1 and p["fuente"] == "banco":
            candidato = candidatos[0]
            opcion = f'si:{candidato["id"]}'
            banco = abs(int(p["monto_centavos"]))
            reservas = registro.reservas_candidato(candidato["id"])
            if (opcion in parametrizaciones and reservas == 1 and banco > 0
                    and diferencia * 100 <= banco * 5
                    and str(candidato["fecha_hora"])[:10] == str(p["fecha"])[:10]):
                # Política del prototipo aprobado: sugerir por día/monto,
                # sin convertir una semejanza en respuesta automática (D38).
                decimas = (diferencia * 1000 + banco // 2) // banco
                porcentaje = f"{decimas // 10},{decimas % 10}"
                sugerencia = {"opcion": opcion, "motivo": "Te sugerimos: es el mismo. Tú decides antes de cambiarlo.",
                    "analisis": f"Hay un único candidato del mismo día; la diferencia es de {cat.pesos(diferencia)} ({porcentaje} % del monto del banco). Los nombres pueden llegar recortados. La coincidencia requiere tu decisión."}
        salida.append({"id": p["id"], "tipo": tipo, "fuente": p["fuente"], "movimiento": _dato(dict(p), es_pregunta=True),
            "candidatos": [{**_dato(f), "etiqueta": identificaciones[f["id"]][1]} for f in candidatos], "ajuste": None if ajuste is None else _dato(dict(ajuste)),
            "diferencia_centavos": diferencia, "opciones": opciones, "sugerencia": sugerencia})
    return salida, respuestas


def _no_en_banco(registro: PersistenciaDiferencias):
    ultima_fila = registro.ultima_importacion_activa()
    filas = registro.fuera_del_banco()
    movimientos = [{"id": f["id"], "movimiento": _dato(dict(f)), "sugerencia": {
        "opcion": None, "motivo": "Comprueba si el cobro se completó antes de borrarlo.",
        "analisis": "El aviso está dentro de las fechas del reporte y no tiene una fila equivalente en el banco. Puedes dejarlo o borrarlo."}} for f in filas]
    return {"movimientos": movimientos, "reporte": None if ultima_fila is None else {
        "desde": ultima_fila["desde"], "hasta": ultima_fila["hasta"], "dia_incompleto": bool(ultima_fila["filas"])}}


class ConsultarDiferencias:
    def __init__(self, unidad: UnidadDiferencias):
        self._unidad = unidad

    def preguntas(self):
        with self._unidad.lectura():
            lista, _ = _preguntas(self._unidad.diferencias)
            return {"preguntas": lista, "total": len(lista),
                "con_sugerencia": sum(p["sugerencia"]["opcion"] is not None for p in lista)}

    def no_en_banco(self):
        with self._unidad.lectura():
            return _no_en_banco(self._unidad.diferencias)
