"""Análisis, confirmación y reversión por puertos, sin SQL ni lectores."""
from contextlib import nullcontext
from dataclasses import asdict
import json
from finanzas.modulos.saldo.publico import comprobacion
from .contratos import Analisis, ConflictoImportacion, ErrorConciliacion, MENSAJE_CONFLICTO, MENSAJE_REVERSION, UnidadGestion
from finanzas.modulos.movimientos.publico import DescarteNoPermitido
from .diferencias_aplicacion import _preguntas
from . import consultas_aplicacion as _consultas

def _rango(filas):
    return {"desde": min(f.fecha for f in filas).isoformat() if filas else None,
            "hasta": max(f.fecha for f in filas).isoformat() if filas else None, "dia_incompleto": bool(filas)}


class GestionarImportaciones:
    def __init__(self, unidad: UnidadGestion):
        self._unidad = unidad

    def resumen_acciones(self):
        return self._unidad.gestion.pendientes(), self._unidad.gestion.no_banco()

    def analizar(self, filas):
        registro = self._unidad.gestion
        filas = tuple(filas)
        with self._unidad.escritura(inmediata=True):
            anterior = registro.huella()
            saldo_antes = registro.saldo_actual()
            desglose_antes = registro.desglose()
            foto_antes = registro.foto()
            savepoint = self._unidad.savepoint()
            try:
                resultado = registro.guardar(filas)
                vista = {"resumen": asdict(resultado.conteos), "reporte": _rango(filas),
                         "saldo_antes_centavos": saldo_antes, "saldo_despues_centavos": registro.saldo_actual(),
                         "sin_categoria": registro.sin_categoria_importacion(resultado.importacion_id),
                         "preguntas_pendientes": registro.pendientes(),
                         "sin_cambios": not registro.diario(foto_antes, registro.foto())}
                vista.update(diferencia_centavos=vista["saldo_despues_centavos"] - saldo_antes,
                    entran_categorizados=registro.entran_categorizados(resultado.importacion_id),
                    fecha_inicio=registro.fecha_inicio(),
                    puede_extender_historial=registro.ofrecer_extender_historial(resultado.conteos.anteriores, vista["reporte"]["desde"]))
                vista["causas_probables"] = [
                    {"codigo": "reporte", "titulo": "Revisa el archivo", "texto": "Elige el reporte completo de los movimientos que quieres importar.", "accion": "elegir_otro_archivo"},
                    {"codigo": "saldo", "titulo": "Comprueba el saldo de tu cuenta", "texto": "El Excel no trae el saldo. Si no coincide con tu cuenta, revisa los movimientos y los ajustes antes de confirmar.", "accion": "ajustar_saldo"}]
                balance = comprobacion.preparar(desglose_antes, registro.desglose(), registro.pendientes_saldo(),
                    comprobacion.cobertura(vista["reporte"]["desde"], vista["reporte"]["hasta"],
                        proteccion=bool(filas)),
                    origen="importacion", fotos=(foto_antes, registro.foto()))
            finally:
                savepoint.rollback()
            if registro.huella() != anterior:
                raise RuntimeError("El análisis no revirtió completamente sus cambios.")
        return Analisis(filas, anterior, vista, balance)


    def confirmar(self, analisis):
        registro = self._unidad.gestion
        with self._unidad.escritura(inmediata=True):
            if registro.huella() != analisis.huella:
                raise ConflictoImportacion(MENSAJE_CONFLICTO)
            antes = registro.foto()
            resultado = registro.guardar(analisis.filas)
            registro.registrar_reversion(resultado, registro.diario(antes, registro.foto()))
            return registro.detalle(resultado.importacion_id)


    def deshacer_importacion(self, ident):
        registro = self._unidad.gestion
        with self._unidad.reversion():
            f = registro.registro(ident)
            puede, motivo = registro.deshacible(f)
            if not puede:
                raise ConflictoImportacion(motivo)
            registro.revertir(json.loads(registro.reversion(ident)["diario"]))
            registro.marcar_deshecha(ident)
            return registro.detalle(ident)


    def responder(self, decisiones, *, transaccion_externa=False):
        registro = self._unidad.gestion
        if len({ident for ident, _ in decisiones}) != len(decisiones):
            raise ErrorConciliacion("Una pregunta no puede responderse dos veces en el mismo envío.")
        with nullcontext() if transaccion_externa else self._unidad.escritura(inmediata=True):
            antes, saldo_antes = registro.foto(), registro.saldo_actual()
            revisiones_antes = registro.revisiones()
            repreguntadas = 0
            for ident, opcion in decisiones:
                lista, opciones = _preguntas(self._unidad.diferencias)
                parametros = opciones.get(ident, {}).get(opcion)
                if parametros is None:
                    raise ConflictoImportacion("La pregunta cambió o esa opción ya no está disponible. Recarga las diferencias.")
                foto_operacion = registro.foto()
                ajustes_antes = registro.ajustes()
                p = registro.pregunta(ident)
                try:
                    si, mid, ya, *resto = parametros
                    ninguno = bool(resto and resto[0])
                    self._unidad.respuestas.responder_pregunta(ident, si, mid, ya, ninguno=ninguno, transaccion_externa=True)
                except DescarteNoPermitido:
                    raise ConflictoImportacion("El movimiento descartado cambió. Recarga las diferencias antes de responder.") from None
                if registro.pregunta(ident)["respuesta"] is None:
                    repreguntadas += 1  # "no" con otro candidato dudoso: se vuelve a preguntar (D50, D)
                if p["importacion_id"] is not None and (rev := registro.reversion(p["importacion_id"])):
                    conteos_guardados = json.loads(rev["conteos"])
                    if conteos_guardados.get("_ajustes") == ajustes_antes:
                        conteos_guardados["_ajustes"] = registro.ajustes()
                    registro.actualizar_revision(p["importacion_id"],
                        registro.componer(json.loads(rev["diario"]), registro.diario(foto_operacion, registro.foto())), conteos_guardados)
            guardadas = len(decisiones) - repreguntadas
            resumen = "" if not guardadas else "Se guardó 1 respuesta." if guardadas == 1 else f"Se guardaron {guardadas} respuestas."
            if repreguntadas:
                otra = ("Hay otro movimiento que podría ser ese aviso: te lo preguntamos de nuevo." if repreguntadas == 1
                        else f"Hay otros movimientos que podrían ser {repreguntadas} de esos avisos: te los preguntamos de nuevo.")
                resumen = f"{resumen} {otra}".strip()
            resultado = {"aplicadas": [ident for ident, _ in decisiones], "resumen": resumen,
                "efecto_saldo_centavos": registro.saldo_actual() - saldo_antes, "saldo_centavos": registro.saldo_actual()}
            copia = {"diario": registro.diario(antes, registro.foto()), "revisiones_antes": revisiones_antes,
                "revisiones_despues": registro.revisiones(),
                "ultimo_id": registro.ultimo_id(), "ajustes": registro.ajustes(),
                "importaciones": registro.importaciones_actuales()}
            return resultado, copia


    def aceptar_sugerencias(self):
        registro = self._unidad.gestion
        # Lectura y aceptación comparten el candado para no usar una sugerencia
        # obsoleta por un aviso que llegue entre ambos pasos.
        with self._unidad.escritura(inmediata=True):
            lista, _ = _preguntas(self._unidad.diferencias)
            decisiones = [(p["id"], p["sugerencia"]["opcion"]) for p in lista if p["sugerencia"]["opcion"] is not None]
            if not decisiones:
                raise ErrorConciliacion("No hay sugerencias claras para aceptar.")
            return self.responder(decisiones, transaccion_externa=True)


    def decidir_no_en_banco(self, ident, opcion):
        registro = self._unidad.gestion
        if opcion not in ("borrar", "dejar"):
            raise ErrorConciliacion("La opción no es válida.")
        with self._unidad.escritura(inmediata=True):
            antes, saldo_antes = registro.foto(), registro.saldo_actual()
            f = registro.pendiente_no_en_banco(ident)
            if f is None:
                raise ConflictoImportacion("Ese movimiento ya no está pendiente. Recarga las diferencias.")
            reservada = registro.tiene_pregunta_pendiente(ident)
            if reservada:
                raise ConflictoImportacion("Resuelve primero la pregunta que incluye este movimiento.")
            registro.marcar_decision(ident, opcion)
            resultado = {"aplicadas": [ident], "resumen": "Movimiento borrado." if opcion == "borrar" else "Movimiento conservado.",
                "efecto_saldo_centavos": registro.saldo_actual() - saldo_antes, "saldo_centavos": registro.saldo_actual()}
            return resultado, {"diario": registro.diario(antes, registro.foto()), "revisiones_antes": [], "revisiones_despues": [],
                "ultimo_id": registro.ultimo_id(), "ajustes": registro.ajustes(),
                "importaciones": registro.importaciones_actuales()}


    def deshacer_decision(self, copia):
        registro = self._unidad.gestion
        with self._unidad.reversion():
            ajuste_nuevo = registro.ajuste_posterior(copia["ultimo_id"])
            # Importar tras un borrado puede crear la fila real del banco.
            # Restaurar el correo duplicaría el saldo aunque su fila siga igual.
            if (copia.get("importaciones") != registro.importaciones_actuales()
                    or ajuste_nuevo or copia["ajustes"] != registro.ajustes()):
                raise ConflictoImportacion(MENSAJE_REVERSION)
            for revision in copia["revisiones_despues"]:
                actual = registro.reversion(revision["importacion_id"])
                if actual is None or dict(actual) != revision:
                    raise ConflictoImportacion(MENSAJE_REVERSION)
            registro.revertir(copia["diario"])
            for revision in copia["revisiones_antes"]:
                registro.restaurar_revision(revision)
            return {"saldo_centavos": registro.saldo_actual(), "resumen": "La decisión se deshizo."}


    def comprobar_saldo(self, saldo_real_centavos, analisis=None):
        """Lectura consistente; nunca consume tokens ni guarda la referencia."""
        registro = self._unidad.gestion
        with self._unidad.lectura():
            actual = registro.huella()
            if analisis is not None:
                if analisis.huella != actual:
                    raise ConflictoImportacion(MENSAJE_CONFLICTO)
                balance = analisis.balance
                if balance is None:
                    raise ConflictoImportacion("Vuelve a calcular antes de comprobar el saldo.")
            else:
                partes = registro.desglose()
                ultimo = registro.ultima_importacion_activa()
                cobertura = comprobacion.cobertura(ultimo["desde"] if ultimo else None,
                    ultimo["hasta"] if ultimo else None, proteccion=bool(ultimo and ultimo["filas"]))
                balance = comprobacion.preparar(partes, partes, registro.pendientes_saldo(), cobertura)
            return comprobacion.comparar(balance, saldo_real_centavos, actual,
                recibido_en=self._unidad.tiempo.ahora().isoformat(timespec="seconds"))


    def detalle(self, ident):
        with self._unidad.lectura():
            return _consultas._detalle(self._unidad.gestion, ident, self._unidad.tiempo)


    def ultima(self):
        with self._unidad.lectura():
            ident = self._unidad.gestion.ultima_importacion_id()
            return {"importacion": None if ident is None else _consultas._detalle(self._unidad.gestion, ident, self._unidad.tiempo)}


    def estado(self):
        with self._unidad.lectura():
            return _consultas._estado(self._unidad.gestion, self._unidad.tiempo)


    def deshacible(self, fila):
        return _consultas._deshacible(self._unidad.gestion, fila)
