"""Tokens bancarios privados por sesión, bounded y atómicos."""
from concurrent.futures import ThreadPoolExecutor
from finanzas.infraestructura.tokens_bancarios_ram import RegistroBancario, MAXIMO_EN_MEMORIA


def test_otro_propietario_no_consume_token_y_solo_una_peticion_gana():
    registro = RegistroBancario(30)
    token = registro.guardar("copia inventada", "sesion inventada uno")
    assert registro.tomar(token, "sesion inventada dos") is None
    with ThreadPoolExecutor(max_workers=4) as hilos:
        resultados = list(hilos.map(lambda _: registro.tomar(token, "sesion inventada uno"), range(8)))
    assert sum(r is not None for r in resultados) == 1


def test_caducidad_tope_y_revocacion():
    ahora = [0]
    registro = RegistroBancario(30, reloj=lambda: ahora[0])
    primero = registro.guardar("primero", "dueno")
    for _ in range(MAXIMO_EN_MEMORIA):
        ultimo = registro.guardar("otro", "dueno")
    assert registro.tomar(primero, "dueno") is None
    ahora[0] = 30
    assert registro.tomar(ultimo, "dueno") is None
    otro = registro.guardar("otro", "dueno")
    registro.revocar("dueno")
    assert registro.tomar(otro, "dueno") is None
