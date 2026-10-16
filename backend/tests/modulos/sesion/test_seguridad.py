"""Pruebas del hash de contraseña y del limitador de intentos."""

import pytest

from finanzas.seguridad import (
    LimitadorIntentos,
    generar_hash,
    hash_bien_formado,
    verificar_contrasena,
)

CONTRASENA = "clave-de-prueba-inventada"


@pytest.fixture(scope="module")
def hash_prueba():
    return generar_hash(CONTRASENA)


def test_formato_del_hash(hash_prueba):
    assert "$" not in hash_prueba  # la shell y systemd expanden "$"
    partes = hash_prueba.split(":")
    assert len(partes) == 6
    assert partes[:4] == ["scrypt", str(2**14), "8", "1"]
    assert len(bytes.fromhex(partes[4])) == 16
    assert hash_bien_formado(hash_prueba)


def test_verifica_correcta_y_rechaza_incorrecta(hash_prueba):
    assert verificar_contrasena(CONTRASENA, hash_prueba) is True
    assert verificar_contrasena("otra-clave", hash_prueba) is False
    assert verificar_contrasena("", hash_prueba) is False


def test_dos_hashes_de_la_misma_contrasena_son_distintos(hash_prueba):
    otro = generar_hash(CONTRASENA)
    assert otro != hash_prueba
    assert verificar_contrasena(CONTRASENA, otro)


@pytest.mark.parametrize(
    "malo",
    [
        "",
        "texto-cualquiera",
        "reemplazar-con-salida-de-python-m-finanzas.seguridad",
        "scrypt$16384$8$1$00ff$00ff",  # formato anterior con "$"
        "bcrypt:16384:8:1:00ff:00ff",
        "scrypt:16384:8:1:zz:00ff",
        "scrypt:16384:8:1::",
        "scrypt:16384:8:1:00ff:",
        "scrypt:abc:8:1:00ff:00ff",
        "scrypt:0:8:1:00ff:00ff",
        "scrypt:-2:8:1:00ff:00ff",
        "scrypt:+16384:8:1:00ff:00ff",
        "scrypt:3:8:1:00ff:00ff",  # n no es potencia de 2
        "scrypt:1099511627776:8:1:00ff:00ff",  # n enorme: supera el tope de memoria
        "scrypt:16384:8:1:00ff",
        "scrypt:16384:8:1:00ff:00ff:extra",
        "scrypt:16384:8:1:0f0:00ff",  # hex de largo impar
    ],
)
def test_hash_mal_formado_devuelve_false(malo):
    assert verificar_contrasena(CONTRASENA, malo) is False


def test_hash_con_dolares_expandidos_por_la_shell_falla(hash_prueba):
    # Lo que quedaría del formato anterior tras ``source .env``: "scrypt" y nada más.
    assert verificar_contrasena(CONTRASENA, "scrypt") is False
    assert not hash_bien_formado("scrypt")


def test_hash_truncado_no_esta_bien_formado(hash_prueba):
    assert not hash_bien_formado(hash_prueba[:-10].rsplit(":", 1)[0])
    assert not hash_bien_formado(hash_prueba + "z")


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def avanzar(self, minutos):
        self.t += minutos * 60


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def limitador(reloj):
    return LimitadorIntentos(max_intentos=3, bloqueo_minutos=15, reloj=reloj)


def test_bloquea_tras_n_fallos(limitador):
    for _ in range(2):
        limitador.registrar_fallo("1.1.1.1")
        assert not limitador.esta_bloqueada("1.1.1.1")
    limitador.registrar_fallo("1.1.1.1")
    assert limitador.esta_bloqueada("1.1.1.1")


def test_se_desbloquea_al_pasar_el_tiempo(limitador, reloj):
    for _ in range(3):
        limitador.registrar_fallo("1.1.1.1")
    reloj.avanzar(14.9)
    assert limitador.esta_bloqueada("1.1.1.1")
    reloj.avanzar(0.2)
    assert not limitador.esta_bloqueada("1.1.1.1")
    # tras el desbloqueo el contador arranca de cero
    limitador.registrar_fallo("1.1.1.1")
    assert not limitador.esta_bloqueada("1.1.1.1")


def test_exito_reinicia_el_contador(limitador):
    limitador.registrar_fallo("1.1.1.1")
    limitador.registrar_fallo("1.1.1.1")
    limitador.registrar_exito("1.1.1.1")
    limitador.registrar_fallo("1.1.1.1")
    limitador.registrar_fallo("1.1.1.1")
    assert not limitador.esta_bloqueada("1.1.1.1")


def test_fallos_fuera_de_la_ventana_no_cuentan(limitador, reloj):
    limitador.registrar_fallo("1.1.1.1")
    limitador.registrar_fallo("1.1.1.1")
    reloj.avanzar(16)
    limitador.registrar_fallo("1.1.1.1")
    assert not limitador.esta_bloqueada("1.1.1.1")


def test_separa_por_ip(limitador):
    for _ in range(3):
        limitador.registrar_fallo("1.1.1.1")
    assert limitador.esta_bloqueada("1.1.1.1")
    assert not limitador.esta_bloqueada("2.2.2.2")
    limitador.registrar_fallo("2.2.2.2")
    assert not limitador.esta_bloqueada("2.2.2.2")


def test_parametros_invalidos():
    with pytest.raises(ValueError):
        LimitadorIntentos(0, 15)
    with pytest.raises(ValueError):
        LimitadorIntentos(5, 0)


def test_cli_imprime_hash_verificable(monkeypatch, capsys):
    from finanzas import seguridad

    monkeypatch.setattr(seguridad.getpass, "getpass", lambda _: CONTRASENA)
    assert seguridad.main() == 0
    salida = capsys.readouterr().out.strip()
    assert verificar_contrasena(CONTRASENA, salida)


def test_cli_exige_12_caracteres(monkeypatch, capsys):
    from finanzas import seguridad

    monkeypatch.setattr(seguridad.getpass, "getpass", lambda _: "corta-11chr")
    assert seguridad.main() == 1
    salida = capsys.readouterr()
    assert salida.out == ""
    assert "12" in salida.err


def test_cli_rechaza_si_no_coinciden(monkeypatch, capsys):
    from finanzas import seguridad

    respuestas = iter([CONTRASENA, "distinta"])
    monkeypatch.setattr(seguridad.getpass, "getpass", lambda _: next(respuestas))
    assert seguridad.main() == 1
    assert capsys.readouterr().out == ""
