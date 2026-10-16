"""Saldo y operaciones manuales: políticas puras sobre participantes del registro."""
from datetime import date, datetime, time

from finanzas.modulos.saldo.contratos import (
    BorradoNoPermitido, Configuracion, CopiaIngreso, Desglose, ErrorSaldo,
    MovimientoNoEncontrado, RestauracionNoPermitida, SaldoNoConfigurado, TiempoSaldo, UnidadSaldo,
)
from finanzas.modulos.saldo.politica import (
    MAXIMO_CENTAVOS, TOLERANCIA_FUTURO, MAXIMO_DESCRIPCION, DESCRIPCION_INGRESO, DESCRIPCION_AJUSTE, ULTIMOS_POR_DEFECTO, TIPOS_GASTO, TIPO_AJUSTE, ORIGEN_MANUAL, MENSAJE_INGRESO_NO_EXISTE, MENSAJE_NO_SE_BORRA_AJUSTE, MENSAJE_NO_SE_BORRA_GMAIL, MENSAJE_NO_SE_BORRA_GASTO, MENSAJE_NO_SE_PUDO_BORRAR, MENSAJE_CONCILIADO, MENSAJE_ANTERIOR_AL_AJUSTE, MENSAJE_RESTAURAR_TRAS_AJUSTE, MENSAJE_RESTAURAR_ANTES_DEL_INICIO, MENSAJE_RESTAURAR_SIN_CONFIGURACION, MENSAJE_RESTAURAR_TRAS_IMPORTAR, MENSAJE_RESTAURAR_CATEGORIA_CAMBIO, MENSAJE_MONTO_INVALIDO, TIPO_INGRESO
)
from finanzas.modulos.saldo.politica import _es_entero, _limite_iso, _validar_no_negativo
from finanzas.modulos.movimientos.publico import MovimientoNuevo


class OperarSaldo:
    def __init__(self, unidad: UnidadSaldo, tiempo: TiempoSaldo):
        self._unidad, self._tiempo = unidad, tiempo

    def leer_configuracion(self) -> Configuracion | None:
        return self._unidad.saldo.leer()

    def puede_extender_historial(self, *, desde: date | None = None) -> bool:
        configuracion = self.leer_configuracion()
        return configuracion is not None and (desde is None or desde < configuracion.fecha_inicio)

    def exigir_configuracion(self) -> Configuracion:
        configuracion = self.leer_configuracion()
        if configuracion is None:
            raise SaldoNoConfigurado()
        return configuracion

    def configuracion_fija(self) -> bool:
        return self._unidad.movimientos.hay_movimientos()

    def configurar(self, saldo_inicial_centavos: int, fecha_inicio: date) -> None:
        _validar_no_negativo(saldo_inicial_centavos, "saldo inicial")
        if isinstance(fecha_inicio, datetime) or not isinstance(fecha_inicio, date):
            raise ErrorSaldo("La fecha de inicio debe ser una fecha (sin hora).")
        if fecha_inicio > self._tiempo.hoy():
            raise ErrorSaldo("La fecha de inicio no puede ser futura.")
        with self._unidad.escritura(inmediata=True):
            if self.configuracion_fija():
                raise ErrorSaldo("Ya hay movimientos registrados: el saldo inicial y la fecha de inicio "
                                 "ya no se pueden cambiar. Corrige el saldo con un ajuste.")
            self._unidad.saldo.guardar(saldo_inicial_centavos, fecha_inicio)

    def desglose_saldo(self) -> Desglose:
        componentes = self._unidad.movimientos.componentes_saldo()
        if componentes is None:
            raise SaldoNoConfigurado()
        return Desglose(*componentes)

    def saldo_actual(self) -> int:
        return self.desglose_saldo().saldo_centavos

    def suma_entre(self, tipos: tuple[str, ...], desde: datetime, hasta: datetime) -> int:
        return self._unidad.movimientos.suma_entre(tipos, _limite_iso(desde), _limite_iso(hasta))

    def gasto_entre(self, desde: datetime, hasta: datetime) -> int:
        return self.suma_entre(TIPOS_GASTO, desde, hasta)

    def ingresos_entre(self, desde: datetime, hasta: datetime) -> int:
        return self.suma_entre((TIPO_INGRESO,), desde, hasta)

    def registrar_ingreso(self, monto_centavos: int, fecha_hora: datetime, descripcion: str) -> int:
        if not _es_entero(monto_centavos):
            raise ErrorSaldo("El monto debe ser un número entero de centavos.")
        if monto_centavos <= 0:
            raise ErrorSaldo("El monto del ingreso debe ser mayor que 0.")
        if monto_centavos > MAXIMO_CENTAVOS:
            raise ErrorSaldo("El monto es demasiado grande.")
        if not isinstance(fecha_hora, datetime):
            raise ErrorSaldo("Indica la fecha y hora del ingreso.")
        if not isinstance(descripcion, str):
            descripcion = ""
        descripcion = descripcion.strip() or DESCRIPCION_INGRESO
        if len(descripcion) > MAXIMO_DESCRIPCION:
            raise ErrorSaldo(f"La descripción admite como máximo {MAXIMO_DESCRIPCION} caracteres.")
        momento = self._tiempo.a_hora(fecha_hora).replace(microsecond=0)
        configuracion = self.exigir_configuracion()
        if momento < datetime.combine(configuracion.fecha_inicio, time(0, 0)):
            raise ErrorSaldo("La fecha del ingreso no puede ser anterior a la fecha de inicio.")
        if momento > self._tiempo.ahora() + TOLERANCIA_FUTURO:
            raise ErrorSaldo("La fecha del ingreso no puede ser futura.")
        with self._unidad.escritura():
            return self._unidad.movimientos.registrar(MovimientoNuevo(
                fecha_hora=momento.isoformat(timespec="seconds"), monto_centavos=monto_centavos,
                tipo=TIPO_INGRESO, descripcion=descripcion, origen="manual", estado="provisional"))

    def ajustar_saldo(self, saldo_real_centavos: int) -> int:
        _validar_no_negativo(saldo_real_centavos, "saldo real")
        with self._unidad.escritura(inmediata=True):
            diferencia = saldo_real_centavos - self.saldo_actual()
            if diferencia == 0:
                return 0
            self._unidad.movimientos.registrar(MovimientoNuevo(
                fecha_hora=self._tiempo.ahora().isoformat(timespec="seconds"), monto_centavos=diferencia,
                tipo=TIPO_AJUSTE, descripcion=DESCRIPCION_AJUSTE, origen="manual"))
            return diferencia

    def ultimos_ingresos_y_ajustes(self, limite: int = ULTIMOS_POR_DEFECTO) -> list[dict]:
        return self._unidad.movimientos.ultimos_ingresos_y_ajustes(limite)

    def ingresos_y_ajustes_entre(self, desde: datetime, hasta: datetime) -> list[dict]:
        return self._unidad.movimientos.ingresos_y_ajustes_entre(_limite_iso(desde), _limite_iso(hasta))

    def ajustes_entre(self, desde: datetime, hasta: datetime) -> tuple[int, int]:
        return self._unidad.movimientos.ajustes_entre(_limite_iso(desde), _limite_iso(hasta))

    def comprobar_borrable(self, movimiento_id: int) -> int:
        fila = self._unidad.movimientos.datos_borrabilidad(movimiento_id)
        if fila is None:
            raise MovimientoNoEncontrado(MENSAJE_INGRESO_NO_EXISTE)
        if fila["tipo"] == TIPO_AJUSTE:
            raise BorradoNoPermitido(MENSAJE_NO_SE_BORRA_AJUSTE)
        if fila["origen"] != ORIGEN_MANUAL or fila["gmail_id"] is not None:
            raise BorradoNoPermitido(MENSAJE_NO_SE_BORRA_GMAIL)
        if fila["tipo"] != TIPO_INGRESO:
            raise BorradoNoPermitido(MENSAJE_NO_SE_BORRA_GASTO)
        if fila["conciliado"]:
            raise BorradoNoPermitido(MENSAJE_CONCILIADO)
        if fila["ajuste_posterior"]:
            raise BorradoNoPermitido(MENSAJE_ANTERIOR_AL_AJUSTE)
        return int(fila["monto_centavos"])

    def borrar_ingreso_con_copia(self, movimiento_id: int) -> tuple[CopiaIngreso, int | None]:
        if not _es_entero(movimiento_id):
            raise MovimientoNoEncontrado(MENSAJE_INGRESO_NO_EXISTE)
        registro = self._unidad.movimientos
        with self._unidad.escritura(inmediata=True):
            self.comprobar_borrable(movimiento_id)
            fila = registro.copia_movimiento(movimiento_id)
            categoria = None if fila.get("categoria_id") is None else registro.categoria_identidad(fila["categoria_id"])
            ultima_importacion = registro.ultima_importacion_id()
            if registro.borrar_manual_si_permitido(movimiento_id) != 1:
                raise BorradoNoPermitido(MENSAJE_NO_SE_PUDO_BORRAR)
            try:
                saldo_despues = self.saldo_actual()
            except SaldoNoConfigurado:
                saldo_despues = None
        return CopiaIngreso(fila=fila, categoria_nombre=None if categoria is None else str(categoria[0]),
            categoria_clase=None if categoria is None else str(categoria[1]),
            ultima_importacion_id=int(ultima_importacion)), saldo_despues

    def borrar_ingreso(self, movimiento_id: int) -> tuple[int, int | None]:
        copia, saldo_despues = self.borrar_ingreso_con_copia(movimiento_id)
        return copia.monto_centavos, saldo_despues

    def restaurar_ingreso(self, copia: CopiaIngreso) -> tuple[int, int]:
        registro = self._unidad.movimientos
        with self._unidad.escritura(inmediata=True):
            configuracion = self.leer_configuracion()
            if configuracion is None:
                raise RestauracionNoPermitida(MENSAJE_RESTAURAR_SIN_CONFIGURACION)
            if copia.fecha_hora < datetime.combine(configuracion.fecha_inicio, time(0, 0)).isoformat():
                raise RestauracionNoPermitida(MENSAJE_RESTAURAR_ANTES_DEL_INICIO)
            if registro.hay_ajuste_para_restaurar(copia.id, copia.fecha_hora):
                raise RestauracionNoPermitida(MENSAJE_RESTAURAR_TRAS_AJUSTE)
            if copia.fila.get("fecha_banco") is not None or registro.hubo_importacion_desde(copia.ultima_importacion_id):
                raise RestauracionNoPermitida(MENSAJE_RESTAURAR_TRAS_IMPORTAR)
            valores = dict(copia.fila)
            if copia.categoria_id is not None:
                actual = registro.categoria_identidad(copia.categoria_id)
                if actual is None:
                    valores.update(categoria_id=None, origen_categoria=None, regla_id=None)
                elif actual != (copia.categoria_nombre, copia.categoria_clase):
                    raise RestauracionNoPermitida(MENSAJE_RESTAURAR_CATEGORIA_CAMBIO)
            if valores.get("regla_id") is not None and not registro.existe_regla(valores["regla_id"]):
                valores["regla_id"] = None
            if registro.existe_movimiento(copia.id):
                del valores["id"]
            nuevo_id = registro.restaurar_fila_completa(valores)
            return nuevo_id, self.saldo_actual()
