"""Operaciones de sesión sobre el estado y servicios prestados por composición."""
import secrets

from .contratos import (
    AccesoBloqueado, CLAVE_AUTENTICADO, CLAVE_CSRF, ContrasenaIncorrecta,
    DUENO, EstadoSesion, GenerarToken, LARGO_TOKEN_CSRF, LimitadorAcceso,
    RevocarPreviews, SesionRequerida, UsuarioSesion, VerificarContrasena,
)


class SesionActual:
    def __init__(self, estado: EstadoSesion, generar_token: GenerarToken):
        self.estado = estado
        self._generar_token = generar_token

    def esta_iniciada(self) -> bool:
        return self.estado.get(CLAVE_AUTENTICADO) is True

    def usuario(self) -> UsuarioSesion:
        if not self.esta_iniciada():
            raise SesionRequerida()
        return DUENO

    def token_csrf(self) -> str:
        token = self.estado.get(CLAVE_CSRF)
        if not isinstance(token, str) or not token:
            token = self._generar_token(LARGO_TOKEN_CSRF)
            self.estado[CLAVE_CSRF] = token
        return token

    def csrf_valido(self, recibido: str | None) -> bool:
        esperado = self.estado.get(CLAVE_CSRF)
        if not isinstance(esperado, str) or not esperado or not recibido:
            return False
        return secrets.compare_digest(esperado.encode(), recibido.encode())


class Acceder:
    def __init__(self, sesion: SesionActual, limitador: LimitadorAcceso,
                 verificar: VerificarContrasena, revocar: RevocarPreviews):
        self._sesion = sesion
        self._limitador = limitador
        self._verificar = verificar
        self._revocar = revocar

    def iniciar(self, contrasena: str, hash_guardado: str, ip: str) -> None:
        # El adaptador llama sin await: comprobar y registrar el intento conserva
        # la secuencia síncrona del proceso único, también durante scrypt.
        if self._limitador.esta_bloqueada(ip):
            raise AccesoBloqueado()
        if not self._verificar(contrasena, hash_guardado):
            self._limitador.registrar_fallo(ip)
            raise ContrasenaIncorrecta()
        self._limitador.registrar_exito(ip)
        self._revocar()
        self._sesion.estado.clear()
        self._sesion.estado[CLAVE_AUTENTICADO] = True

    def cerrar(self) -> None:
        self._revocar()
        self._sesion.estado.clear()
