"""Arranque y extensión: cálculo real en savepoint y confirmación revalidada."""
from dataclasses import asdict
from datetime import date
from finanzas.modulos.saldo.publico import MAXIMO_CENTAVOS
from finanzas.modulos.saldo.publico import comprobacion
from finanzas.modulos.sincronizacion.publico import ResultadoSincronizacion
from finanzas.modulos.importaciones.publico import ConflictoImportacion, ImportacionInexistente
from finanzas.modulos.importaciones.publico import MENSAJE_CONFLICTO
from .contratos import UnidadArranque
from .historial import ErrorArranque, AnalisisArranque, unir_archivos


class OperarArranque:
    def __init__(self, unidad: UnidadArranque):
        self._unidad = unidad

    def _guardar_historial(self, historial, avisos, inicio_anterior=None):
        resultado_gmail = self._guardar_avisos(avisos)
        resultado = self._unidad.importaciones.guardar_historial(historial, avisos, inicio_anterior)
        return resultado, resultado_gmail

    def _guardar_avisos(self, avisos):
        registrados = self._unidad.avisos.ids_registrados()
        resultado = ResultadoSincronizacion()
        for aviso in avisos:
            if aviso.gmail_id in registrados:
                resultado.duplicados += 1
                continue
            if aviso.movimiento is not None:
                if self._unidad.avisos.guardar_movimiento(aviso.gmail_id, aviso.movimiento):
                    resultado.nuevos += 1
                else:
                    resultado.duplicados += 1
            else:
                guardado = self._unidad.avisos.guardar_no_reconocido(aviso)
                if guardado:
                    if aviso.rechazado:
                        resultado.rechazados_autenticacion += 1
                    else:
                        resultado.no_reconocidos += 1
                else:
                    resultado.duplicados += 1
            registrados.add(aviso.gmail_id)
        return resultado


    def estado_arranque(self):
        """Elegibilidad que comparten el contrato de pantalla y las guardas."""
        configurado = self._unidad.saldo.leer_configuracion() is not None
        return {"mostrar_arranque_inicial": not configurado,
            "puede_iniciar_arranque": not self._unidad.saldo.configuracion_fija(),
            "puede_extender_historial": self._unidad.saldo.puede_extender_historial()}


    def analizar(self, archivos, saldo_actual_centavos, *, modo, avisos=(), huella_esperada=None,
                 saldo_real_centavos=None, recibido_en=None):
        archivos = tuple(tuple(a) for a in archivos)
        historial = unir_archivos(archivos)
        # Valida el objetivo aun si después cambia el neto por avisos del correo.
        if type(saldo_actual_centavos) is not int or not 0 <= saldo_actual_centavos <= MAXIMO_CENTAVOS:
            raise ErrorArranque("Escribe un saldo actual válido en centavos enteros.")
        if saldo_real_centavos is not None:
            if type(saldo_real_centavos) is not int or not 0 <= saldo_real_centavos <= MAXIMO_CENTAVOS:
                raise ErrorArranque("Escribe un saldo real válido en centavos enteros.")
            if modo == "arranque" and saldo_real_centavos != saldo_actual_centavos:
                raise ErrorArranque("En el primer arranque usa una sola referencia de saldo para calcular el inicial.")
        if not historial.filas:
            raise ErrorArranque("Los archivos no tienen movimientos. Agrega un reporte con historial.")
        if historial.hasta > self._unidad.tiempo.hoy():
            raise ErrorArranque("El archivo tiene fechas futuras. Revisa el reporte antes de continuar.")
        avisos = tuple(avisos)
        with self._unidad.escritura(inmediata=True):
            huella = self._unidad.importaciones.huella()
            if huella_esperada is not None and huella != huella_esperada:
                raise ConflictoImportacion(MENSAJE_CONFLICTO)
            conf = self._unidad.saldo.leer_configuracion()
            desglose_antes, foto_antes = self._unidad.importaciones.desglose(), self._unidad.importaciones.foto()
            elegibilidad = self.estado_arranque()
            if modo == "arranque":
                if not elegibilidad["puede_iniciar_arranque"]:
                    raise ErrorArranque("Ya tienes movimientos. Usa Extender historial para agregar meses anteriores.")
                objetivo = saldo_actual_centavos
            elif modo == "extension":
                if not self._unidad.saldo.puede_extender_historial(desde=historial.desde):
                    raise ErrorArranque("Agrega un reporte con movimientos anteriores a tu fecha de inicio.")
                objetivo = self._unidad.saldo.saldo_actual()
            else:
                raise ErrorArranque("El modo de historial no es válido.")
            punto = self._unidad.savepoint()
            try:
                self._unidad.configuracion.guardar(0, historial.desde)
                resultado, resultado_gmail = self._guardar_historial(historial, avisos, conf.fecha_inicio if modo == "extension" else None)
                neto = self._unidad.saldo.saldo_actual()
                inicial = objetivo - neto
                if not 0 <= inicial <= MAXIMO_CENTAVOS:
                    raise ErrorArranque("El saldo inicial calculado no es válido. Revisa el saldo actual y los archivos antes de continuar.")
                ingresos = sum(f.monto_centavos for f in historial.filas if f.monto_centavos > 0)
                gastos = -sum(f.monto_centavos for f in historial.filas if f.monto_centavos < 0)
                resto = neto - (ingresos - gastos)
                self._unidad.configuracion.guardar(inicial, historial.desde)
                vista = {"modo": modo, "saldo_actual_centavos": objetivo, "saldo_inicial_centavos": inicial,
                    "ingresos_centavos": ingresos, "gastos_centavos": gastos,
                    "otros_movimientos_netos_centavos": resto,
                    "fecha_inicio_propuesta": historial.desde.isoformat(),
                    "fecha_inicio_anterior": conf.fecha_inicio.isoformat() if conf else None,
                    "saldo_inicial_anterior_centavos": conf.saldo_inicial_centavos if conf else None,
                    "desde": historial.desde.isoformat(), "hasta": historial.hasta.isoformat(),
                    "archivos": historial.archivos, "filas": len(historial.filas),
                    "filas_solapadas": historial.solapadas, "archivos_truncados": historial.truncados,
                    "cobertura_verificada": False,
                    "huecos": [{"desde": d.isoformat(), "hasta": h.isoformat()} for d, h in historial.huecos],
                    "advertencia_cobertura": "El Excel no acredita que estén todos los movimientos. Comprueba que tus reportes incluyan el periodo completo; los tramos entre archivos pueden necesitar otro reporte.",
                    "explicacion_otros_movimientos": "El cálculo incluye los avisos de Gmail y los movimientos ya registrados que no duplican las filas del banco. Las diferencias pendientes siguen contando hasta que las revises.",
                    "correos_leidos": len(avisos), "no_reconocidos": sum(a.movimiento is None for a in avisos),
                    "contadores_gmail": asdict(resultado_gmail),
                    "resumen": asdict(resultado.conteos), "sin_categoria": self._unidad.importaciones.sin_categoria_importacion(resultado.importacion_id),
                    "preguntas_pendientes": self._unidad.importaciones.pendientes(), "saldo_despues_centavos": self._unidad.saldo.saldo_actual()}
                balance = comprobacion.preparar(desglose_antes, self._unidad.importaciones.desglose(), self._unidad.importaciones.pendientes_saldo(),
                    comprobacion.cobertura(historial.desde.isoformat(), historial.hasta.isoformat(),
                        proteccion=bool(historial.truncados), huecos=vista["huecos"]),
                    origen=modo, fotos=(foto_antes, self._unidad.importaciones.foto()))
                referencia = saldo_actual_centavos if modo == "arranque" else saldo_real_centavos
                if referencia is not None:
                    vista["comprobacion_saldo"] = comprobacion.comparar(balance, referencia, huella, recibido_en=recibido_en or self._unidad.tiempo.ahora().isoformat(timespec="seconds"))
            finally:
                punto.rollback()
            if self._unidad.importaciones.huella() != huella:
                raise RuntimeError("El cálculo de arranque no revirtió completamente sus cambios.")
        return AnalisisArranque(historial, avisos, modo, huella, vista, balance)


    def confirmar(self, analisis):
        with self._unidad.escritura(inmediata=True):
            if self._unidad.importaciones.huella() != analisis.huella:
                raise ConflictoImportacion(MENSAJE_CONFLICTO)
            antes = self._unidad.importaciones.foto()
            self._unidad.configuracion.guardar(analisis.vista["saldo_inicial_centavos"], analisis.historial.desde)
            anterior = analisis.vista["fecha_inicio_anterior"]
            resultado, resultado_gmail = self._guardar_historial(analisis.historial, analisis.avisos,
                date.fromisoformat(anterior) if analisis.modo == "extension" else None)
            if self._unidad.saldo.saldo_actual() != analisis.vista["saldo_despues_centavos"]:
                raise ConflictoImportacion("El cálculo cambió. Vuelve a calcular antes de guardar el historial.")
            self._unidad.avisos.guardar_estado(resultado_gmail)
            self._unidad.importaciones.registrar_historial(resultado, antes, analisis.vista)
            return self.resultado_arranque(resultado.importacion_id)


    def resultado_arranque(self, ident):
        detalle = self._unidad.importaciones.detalle(ident)
        registro = self._unidad.importaciones.reversion(ident)
        if registro is None or registro["arranque"] is None:
            raise ImportacionInexistente("Ese historial guiado no existe.")
        import json
        calculo = json.loads(registro["arranque"])
        conf = self._unidad.saldo.leer_configuracion()
        return {"fase": "deshecho" if detalle["deshecha_en"] else "categorizar" if detalle["grupos"] else
            "diferencias" if detalle["preguntas_pendientes"] or detalle["no_en_banco_pendientes"] else "listo",
            "calculo": calculo, "importacion": detalle,
            "fecha_inicio": conf.fecha_inicio.isoformat() if conf else None,
            "saldo_inicial_centavos": conf.saldo_inicial_centavos if conf else None}
