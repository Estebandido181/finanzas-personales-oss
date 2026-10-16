"""Acceso puro: secuencia y revocación sin Request ni servidor."""
import pytest
from finanzas.modulos.sesion.publico import (
    Acceder, AccesoBloqueado, ContrasenaIncorrecta, SesionActual, SesionRequerida,
)


class Limitador:
    def __init__(self, eventos, bloqueada=False):
        self.eventos = eventos
        self.bloqueada = bloqueada

    def esta_bloqueada(self, ip):
        self.eventos.append(('bloqueada', ip))
        return self.bloqueada

    def registrar_exito(self, ip):
        self.eventos.append(('exito', ip))

    def registrar_fallo(self, ip):
        self.eventos.append(('fallo', ip))


def crear_acceso(estado, *, correcta=True, bloqueada=False):
    eventos = []
    sesion = SesionActual(estado, lambda largo: 'token-ficticio-nuevo')

    def verificar(contrasena, hash_guardado):
        eventos.append(('verificar', contrasena, hash_guardado))
        return correcta

    def revocar():
        eventos.append(('revocar', dict(estado)))

    return Acceder(sesion, Limitador(eventos, bloqueada), verificar, revocar), sesion, eventos


def test_bloqueo_no_comprueba_contrasena_ni_modifica_sesion():
    estado = {'csrf_token': 'anterior', 'autenticado': True}
    acceso, _, eventos = crear_acceso(estado, bloqueada=True)
    with pytest.raises(AccesoBloqueado):
        acceso.iniciar('inventada', 'hash-ficticio', 'ip-ficticia')
    assert eventos == [('bloqueada', 'ip-ficticia')]
    assert estado == {'csrf_token': 'anterior', 'autenticado': True}


def test_fallo_se_registra_sin_revocar_ni_reemplazar_sesion():
    estado = {'csrf_token': 'anterior'}
    acceso, _, eventos = crear_acceso(estado, correcta=False)
    with pytest.raises(ContrasenaIncorrecta):
        acceso.iniciar('inventada', 'hash-ficticio', 'ip-ficticia')
    assert eventos == [('bloqueada', 'ip-ficticia'),
                       ('verificar', 'inventada', 'hash-ficticio'), ('fallo', 'ip-ficticia')]
    assert estado == {'csrf_token': 'anterior'}


def test_exito_revoca_propietario_anterior_antes_de_rotar_sesion():
    estado = {'csrf_token': 'anterior', 'dato-antiguo': 'ficticio'}
    acceso, sesion, eventos = crear_acceso(estado)
    acceso.iniciar('inventada', 'hash-ficticio', 'ip-ficticia')
    assert eventos == [('bloqueada', 'ip-ficticia'),
                       ('verificar', 'inventada', 'hash-ficticio'), ('exito', 'ip-ficticia'),
                       ('revocar', {'csrf_token': 'anterior', 'dato-antiguo': 'ficticio'})]
    assert estado == {'autenticado': True}
    assert sesion.token_csrf() == 'token-ficticio-nuevo'
    assert not sesion.csrf_valido('anterior')
    assert sesion.csrf_valido('token-ficticio-nuevo')
    assert sesion.usuario().id == 'dueno'


def test_cierre_revoca_antes_de_limpiar_y_rechaza_usuario():
    estado = {'autenticado': True, 'csrf_token': 'anterior'}
    acceso, sesion, eventos = crear_acceso(estado)
    acceso.cerrar()
    assert eventos == [('revocar', {'autenticado': True, 'csrf_token': 'anterior'})]
    assert estado == {}
    assert not sesion.csrf_valido('anterior')
    with pytest.raises(SesionRequerida):
        sesion.usuario()


@pytest.mark.parametrize('valor', [1, 'true', False, None])
def test_identidad_exige_autenticado_booleano_true(valor):
    sesion = SesionActual({'autenticado': valor}, lambda largo: 'ficticio')
    assert not sesion.esta_iniciada()
    with pytest.raises(SesionRequerida):
        sesion.usuario()


def test_fallo_al_revocar_no_limpia_la_sesion_anterior():
    estado = {'csrf_token': 'anterior'}
    eventos = []

    def fallar():
        raise RuntimeError('fallo ficticio')

    acceso = Acceder(SesionActual(estado, lambda largo: 'nuevo'),
                    Limitador(eventos), lambda clave, hash_: True, fallar)
    with pytest.raises(RuntimeError, match='fallo ficticio'):
        acceso.iniciar('inventada', 'hash-ficticio', 'ip-ficticia')
    assert estado == {'csrf_token': 'anterior'}
