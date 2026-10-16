"""Copias bancarias efímeras ligadas a sesión, sin mutar su cookie.

Una lectura concurrente puede devolver la cookie anterior. Guardar los tokens
solo en servidor evita perder un análisis o deshacer por esa respuesta tardía.
El identificador de propietario es el CSRF aleatorio que rota en cada login.
"""
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
import secrets
import threading
import time

MAXIMO_EN_MEMORIA = 100


@dataclass(frozen=True)
class Pendiente:
    copia: object
    propietario: str
    vence: float


class RegistroBancario:
    def __init__(self, segundos, reloj=time.monotonic):
        self.segundos, self._reloj = segundos, reloj
        self._pendientes = OrderedDict()
        self._candado = threading.Lock()

    def _limpiar(self):
        ahora = self._reloj()
        for token in [t for t, p in self._pendientes.items() if p.vence <= ahora]:
            del self._pendientes[token]
        while len(self._pendientes) > MAXIMO_EN_MEMORIA:
            self._pendientes.popitem(last=False)

    def guardar(self, copia, propietario):
        token = secrets.token_urlsafe(24)
        with self._candado:
            self._limpiar()
            self._pendientes[token] = Pendiente(copia, propietario, self._reloj() + self.segundos)
            self._limpiar()
        return token

    def tomar(self, token, propietario):
        with self._candado:
            self._limpiar()
            pendiente = self._pendientes.get(token)
            if pendiente is None or not secrets.compare_digest(pendiente.propietario, propietario):
                return None
            return self._pendientes.pop(token)

    def ver(self, token, propietario):
        """Consulta sin consumir ni prolongar TTL; copias del arranque inmutables."""
        with self._candado:
            self._limpiar()
            pendiente = self._pendientes.get(token)
            if pendiente is None or not secrets.compare_digest(pendiente.propietario, propietario):
                return None
            return pendiente

    def revocar(self, propietario):
        with self._candado:
            for token in [t for t, p in self._pendientes.items() if p.propietario == propietario]:
                del self._pendientes[token]


class HistorialVencido(Exception):
    """El historial cambió, venció o pertenece a otra sesión."""


@dataclass
class _SesionHistorial:
    generacion: str
    vence: float
    candado: object
    usuarios: int = 0


@dataclass(frozen=True)
class _CalculoHistorial:
    generacion: str
    archivos_token: str
    analisis: object


class RegistroHistorial:
    """Serializa cambios/publicación/confirmación del arranque por sesión.

    Gmail y el cálculo reversible ocurren fuera del candado. Cada publicación
    comprueba la generación capturada y la vigencia de su lista bajo el mismo
    candado que las mutaciones y la transacción de confirmación. Las generaciones
    aleatorias evitan reutilizar una versión después de vencer o expulsar una
    sesión. No se mantienen tombstones ni sesiones ilimitadas en memoria.
    """

    def __init__(self, archivos, analisis, reloj=time.monotonic):
        self.archivos, self.analisis, self._reloj = archivos, analisis, reloj
        self._sesiones = OrderedDict()
        self._candado = threading.Lock()

    def _eliminar(self, propietario):
        del self._sesiones[propietario]
        self.archivos.revocar(propietario)
        self.analisis.revocar(propietario)

    @contextmanager
    def _sesion(self, propietario):
        # El candado del mapa nunca se conserva al esperar el de una sesión.
        # Las sesiones en uso no se expulsan: no puede haber dos candados para
        # el mismo propietario durante una confirmación o una mutación.
        with self._candado:
            ahora = self._reloj()
            for p, s in list(self._sesiones.items()):
                if not s.usuarios and s.vence <= ahora:
                    self._eliminar(p)
            if propietario not in self._sesiones:
                if len(self._sesiones) >= MAXIMO_EN_MEMORIA:
                    expulsable = next((p for p, s in self._sesiones.items() if not s.usuarios), None)
                    if expulsable is None:
                        raise HistorialVencido()
                    self._eliminar(expulsable)
                self._sesiones[propietario] = _SesionHistorial(
                    secrets.token_urlsafe(24), ahora + self.archivos.segundos, threading.Lock())
            sesion = self._sesiones[propietario]
            sesion.usuarios += 1
            self._sesiones.move_to_end(propietario)
        try:
            with sesion.candado:
                yield sesion
        finally:
            with self._candado:
                sesion.usuarios -= 1

    def _rotar(self, sesion, propietario):
        sesion.generacion = secrets.token_urlsafe(24)
        sesion.vence = self._reloj() + self.archivos.segundos
        self.analisis.revocar(propietario)

    def _archivos(self, token, propietario):
        pendiente = self.archivos.ver(token, propietario)
        if pendiente is None:
            raise HistorialVencido()
        return pendiente.copia

    def leer_archivos(self, token, propietario):
        with self._sesion(propietario) as sesion:
            return self._archivos(token, propietario), sesion.generacion

    def iniciar_subida(self, propietario):
        with self._sesion(propietario) as sesion:
            return sesion.generacion

    def agregar(self, token, generacion, archivos, propietario):
        with self._sesion(propietario) as sesion:
            if generacion != sesion.generacion:
                raise HistorialVencido()
            if token is not None:
                self._archivos(token, propietario)
            self.archivos.revocar(propietario)
            self._rotar(sesion, propietario)
            return self.archivos.guardar(archivos, propietario)

    def modificar(self, token, propietario, transformar):
        with self._sesion(propietario) as sesion:
            archivos = transformar(self._archivos(token, propietario))
            self.archivos.revocar(propietario)
            self._rotar(sesion, propietario)
            return self.archivos.guardar(archivos, propietario), archivos

    def descartar_archivos(self, token, propietario):
        with self._sesion(propietario) as sesion:
            self._archivos(token, propietario)
            self.archivos.revocar(propietario)
            self._rotar(sesion, propietario)

    def publicar(self, token_archivos, generacion, analisis, propietario):
        with self._sesion(propietario) as sesion:
            if generacion != sesion.generacion:
                raise HistorialVencido()
            self._archivos(token_archivos, propietario)
            self._rotar(sesion, propietario)
            calculo = _CalculoHistorial(sesion.generacion, token_archivos, analisis)
            return self.analisis.guardar(calculo, propietario)

    def _consumir(self, token, propietario, sesion):
        pendiente = self.analisis.tomar(token, propietario)
        if pendiente is None or pendiente.copia.generacion != sesion.generacion:
            raise HistorialVencido()
        self._archivos(pendiente.copia.archivos_token, propietario)
        self._rotar(sesion, propietario)
        return pendiente.copia.analisis

    def consultar(self, token, propietario, leer):
        """Lectura no consumidora: candado sesión → lectura DB, como confirmar.

        No prolonga TTL ni permite comprobar un cálculo de una lista revocada.
        """
        with self._sesion(propietario) as sesion:
            pendiente = self.analisis.ver(token, propietario)
            if pendiente is None or pendiente.copia.generacion != sesion.generacion:
                raise HistorialVencido()
            self._archivos(pendiente.copia.archivos_token, propietario)
            return leer(pendiente.copia.analisis)

    def descartar_analisis(self, token, propietario):
        with self._sesion(propietario) as sesion:
            self._consumir(token, propietario, sesion)

    def confirmar(self, token, propietario, guardar):
        with self._sesion(propietario) as sesion:
            analisis = self._consumir(token, propietario, sesion)
            # El candado cubre también el commit DB. Un descarte exitoso
            # anterior impide confirmar; uno posterior espera a este commit.
            return guardar(analisis)

    def revocar(self, propietario):
        with self._sesion(propietario) as sesion:
            self.archivos.revocar(propietario)
            self._rotar(sesion, propietario)
