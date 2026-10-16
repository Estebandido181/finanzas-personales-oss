"""Coordinación de correo mediante puertos; autenticidad y escritura prestadas."""
from collections.abc import Callable, Sequence
import logging
from finanzas.modulos.sincronizacion.publico import (
    ClienteGmail, CorreoGmail, REMITENTES_OFICIALES, ErrorAutorizacionGmail,
    ResultadoSincronizacion, EstadoSincronizacion, MovimientoExtraido,
)
from .contratos import ResultadoReproceso, SincronizacionNoConfigurada, RegistroSincronizacion
from finanzas.compartido.hora import ZONA_COLOMBIA

logger = logging.getLogger("finanzas.sincronizacion")
MOTIVO_REMITENTE = "remitente"


class Sincronizar:
    def __init__(self, registro: RegistroSincronizacion,
                 evaluar: Callable[[CorreoGmail, str | Sequence[str]], tuple[str | None, MovimientoExtraido | None]]):
        self._registro = registro
        self._evaluar = evaluar

    def ejecutar(self, fabrica_cliente: Callable[[], ClienteGmail], remitentes_oficiales: str | Sequence[str]=REMITENTES_OFICIALES, origen: str='comando') -> ResultadoSincronizacion:
        """Comprueba la fecha de inicio, crea el cliente, sincroniza y guarda el estado.

        La fecha se comprueba antes de crear el cliente para no tocar el token ni
        Google si todavía no hay nada que sincronizar.

        Al terminar, bien o mal, guarda el resultado en ``estado_sincronizacion``
        (ver ``guardar_estado``; ``origen`` es ``"web"`` o ``"comando"``) y
        después devuelve el resultado o deja pasar la misma excepción que antes:
        quien llama sigue decidiendo qué mostrar.
        """
        estado, error = self._ejecutar(fabrica_cliente, remitentes_oficiales, origen)
        if error is not None:
            raise error
        assert estado.resultado is not None
        return estado.resultado

    def ejecutar_reproceso(self, fabrica_cliente: Callable[[], ClienteGmail], remitentes_oficiales: str | Sequence[str]=REMITENTES_OFICIALES, gmail_id: str | None=None) -> tuple[ResultadoReproceso | None, str | None]:
        """Como ``ejecutar_con_estado`` pero para el reproceso: no lanza.

        Devuelve ``(resultado, None)`` o ``(None, codigo_error)`` con los mismos
        códigos que la sincronización (``db.CODIGOS_ERROR_SINCRONIZACION``). No
        toca ``estado_sincronizacion``: un reproceso no es una sincronización.
        La fecha se comprueba antes de crear el cliente, y si no hay nada que
        reprocesar no se crea, para no tocar el token ni Google en vano.
        """
        try:
            self._registro.leer_fecha_inicio()
        except SincronizacionNoConfigurada:
            return (None, 'sin_fecha_inicio')
        if not (self._registro.es_no_reconocido(gmail_id) if gmail_id is not None else self._registro.listar_no_reconocidos()):
            self._registro.cerrar_lectura()
            return (ResultadoReproceso(), None)
        try:
            return (self.reprocesar(fabrica_cliente(), remitentes_oficiales, gmail_id), None)
        except SincronizacionNoConfigurada:
            return (None, 'gmail_no_configurado')
        except ErrorAutorizacionGmail:
            return (None, 'autorizacion_gmail')
        except Exception as error:
            logger.error('Reproceso fallido (%s)', type(error).__name__)
            return (None, 'error_inesperado')
        finally:
            if self._registro.en_transaccion():
                self._registro.cerrar_lectura()

    def reprocesar(self, cliente: ClienteGmail, remitentes_oficiales: str | Sequence[str]=REMITENTES_OFICIALES, gmail_id: str | None=None) -> ResultadoReproceso:
        """Vuelve a descargar los no reconocidos y les aplica el camino normal.

        Para cada correo de la lista (o solo ``gmail_id``, si se indica y está en
        la lista): lo descarga otra vez (solo lectura), aplica la misma barrera de
        fecha de inicio que ``sincronizar`` y ``evaluar_correo`` (remitente,
        DMARC, aviso citado y extractor). Si ahora es un aviso válido, guarda el
        movimiento y quita el correo de la lista en una sola transacción
        (``gmail_id`` único: reprocesar dos veces no duplica). Si no, el correo se
        queda en la lista tal como estaba.

        Como ``sincronizar``: lanza ``SincronizacionNoConfigurada`` si falta la
        fecha de inicio y deja pasar ``ErrorAutorizacionGmail``. Si la lista está
        vacía, no consulta Gmail.

        Registros: solo contadores y tipos de error. Nunca ids, asuntos, cuerpos
        ni montos.
        """
        fecha_inicio = self._registro.leer_fecha_inicio()
        resultado = ResultadoReproceso()
        ids = [str(fila['gmail_id']) for fila in self._registro.listar_no_reconocidos() if fila['gmail_id'] is not None]
        if gmail_id is not None:
            ids = [i for i in ids if i == gmail_id]
        for actual in ids:
            resultado.revisados += 1
            try:
                correo = cliente.obtener(actual)
            except ErrorAutorizacionGmail:
                raise
            except Exception as error:
                resultado.errores += 1
                logger.warning('Reproceso: error al descargar un correo (%s)', type(error).__name__)
                continue
            try:
                if correo.fecha.astimezone(ZONA_COLOMBIA).date() < fecha_inicio:
                    resultado.siguen_sin_reconocerse += 1
                    continue
                motivo, movimiento = self._evaluar(correo, remitentes_oficiales)
                if motivo is not None or movimiento is None:
                    resultado.siguen_sin_reconocerse += 1
                elif self._registro.guardar_movimiento(actual, movimiento, quitar_no_reconocido=True):
                    resultado.movimientos_creados += 1
                else:
                    resultado.ya_registrados += 1
            except Exception as error:
                resultado.errores += 1
                logger.warning('Reproceso: error al procesar un correo (%s)', type(error).__name__)
        logger.info('Reproceso terminado: %s', resultado.resumen())
        return resultado

    def ejecutar_con_estado(self, fabrica_cliente: Callable[[], ClienteGmail], remitentes_oficiales: str | Sequence[str]=REMITENTES_OFICIALES, origen: str='web') -> EstadoSincronizacion:
        """Como ``ejecutar``, pero no lanza: devuelve el estado que guardó (para la API).

        Un error inesperado se registra solo con su tipo: el mensaje podría traer
        datos de un correo.
        """
        estado, error = self._ejecutar(fabrica_cliente, remitentes_oficiales, origen)
        if error is not None and estado.codigo_error == 'error_inesperado':
            logger.error('Sincronización fallida (%s)', type(error).__name__)
        return estado

    def sincronizar(self, cliente: ClienteGmail, remitentes_oficiales: str | Sequence[str]=REMITENTES_OFICIALES) -> ResultadoSincronizacion:
        """Trae los correos nuevos de Gmail y los registra (ver el docstring del módulo).

        Lanza ``SincronizacionNoConfigurada`` si falta la fecha de inicio (sin
        llamar a Gmail) y deja pasar ``ErrorAutorizacionGmail``: si el token deja
        de servir no tiene sentido seguir, y lo ya guardado se conserva.
        """
        fecha_inicio = self._registro.leer_fecha_inicio()
        resultado = ResultadoSincronizacion()
        ids = list(dict.fromkeys(cliente.listar_ids(fecha_inicio)))
        registrados = self._registro.ids_registrados()
        pendientes = [gmail_id for gmail_id in ids if gmail_id not in registrados]
        logger.info('Sincronización: %d correos en Gmail, %d pendientes', len(ids), len(pendientes))
        for gmail_id in pendientes:
            try:
                correo = cliente.obtener(gmail_id)
            except ErrorAutorizacionGmail:
                raise
            except Exception as error:
                resultado.errores += 1
                logger.warning('Correo %s: error al descargar (%s)', gmail_id, type(error).__name__)
                continue
            try:
                if correo.fecha.astimezone(ZONA_COLOMBIA).date() < fecha_inicio:
                    logger.info('Correo %s: anterior a la fecha de inicio, se descarta', gmail_id)
                    continue
                motivo, movimiento = self._evaluar(correo, remitentes_oficiales)
                if motivo is not None:
                    if self._registro.guardar_correo_no_reconocido(correo):
                        resultado.rechazados_autenticacion += 1
                        logger.warning('Correo %s: rechazado por %s (motivo=%s)', gmail_id, 'remitente' if motivo == MOTIVO_REMITENTE else 'autenticación', motivo)
                    else:
                        resultado.duplicados += 1
                        logger.info('Correo %s: ya estaba registrado', gmail_id)
                    continue
                if movimiento is not None:
                    if self._registro.guardar_movimiento(gmail_id, movimiento):
                        resultado.nuevos += 1
                        logger.info('Correo %s: movimiento registrado', gmail_id)
                    else:
                        resultado.duplicados += 1
                        logger.info('Correo %s: ya estaba registrado', gmail_id)
                elif self._registro.guardar_correo_no_reconocido(correo):
                    resultado.no_reconocidos += 1
                    logger.info('Correo %s: no reconocido, queda para revisión', gmail_id)
                else:
                    resultado.duplicados += 1
                    logger.info('Correo %s: ya estaba registrado', gmail_id)
            except Exception as error:
                resultado.errores += 1
                logger.warning('Correo %s: error al procesar (%s)', gmail_id, type(error).__name__)
        logger.info('Sincronización terminada: %s', resultado.resumen())
        return resultado

    def _ejecutar(self, fabrica_cliente: Callable[[], ClienteGmail], remitentes_oficiales: str | Sequence[str], origen: str) -> tuple[EstadoSincronizacion, Exception | None]:
        try:
            self._registro.leer_fecha_inicio()
        except SincronizacionNoConfigurada as error:
            return (self._registro.guardar_estado_sincronizacion(origen, codigo_error='sin_fecha_inicio'), error)
        try:
            resultado = self.sincronizar(fabrica_cliente(), remitentes_oficiales)
        except SincronizacionNoConfigurada as error:
            return (self._registro.guardar_estado_sincronizacion(origen, codigo_error='gmail_no_configurado'), error)
        except ErrorAutorizacionGmail as error:
            return (self._registro.guardar_estado_sincronizacion(origen, codigo_error='autorizacion_gmail'), error)
        except Exception as error:
            return (self._registro.guardar_estado_sincronizacion(origen, codigo_error='error_inesperado'), error)
        return (self._registro.guardar_estado_sincronizacion(origen, resultado=resultado), None)
