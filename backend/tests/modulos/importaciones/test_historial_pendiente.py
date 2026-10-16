from finanzas.infraestructura import tokens_bancarios_ram
"""Orden atómico de confirmación/descarte, caducidad y RAM acotada."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest
from finanzas.infraestructura import tokens_bancarios_ram as t


def registro(reloj=lambda: 0):
    return t.RegistroHistorial(t.RegistroBancario(900, reloj), t.RegistroBancario(900, reloj), reloj)


def preparar(r, propietario="sesion-inventada"):
    token = r.agregar(None, r.iniciar_subida(propietario), (("fila inventada",),), propietario)
    archivos, generacion = r.leer_archivos(token, propietario)
    calculo = r.publicar(token, generacion, "analisis inventado", propietario)
    return token, calculo


def test_descartar_antes_de_confirmar_impide_guardar():
    r = registro()
    token, calculo = preparar(r)
    r.descartar_archivos(token, "sesion-inventada")
    guardados = []
    with pytest.raises(t.HistorialVencido):
        r.confirmar(calculo, "sesion-inventada", guardados.append)
    assert guardados == []


def test_confirmacion_retiene_candado_hasta_commit_y_no_bloquea_otra_sesion():
    r = registro()
    token, calculo = preparar(r)
    entro, continuar, esperando = Event(), Event(), Event()
    guardados = []

    class CandadoObservado:
        def __init__(self):
            self.candado = Lock()
        def __enter__(self):
            if self.candado.locked():
                esperando.set()
            self.candado.acquire()
        def __exit__(self, *args):
            self.candado.release()

    r._sesiones["sesion-inventada"].candado = CandadoObservado()
    def guardar(analisis):
        entro.set()
        assert continuar.wait(10)
        guardados.append(analisis)  # representa el commit antes de liberar
        return "guardado"

    with ThreadPoolExecutor(max_workers=2) as grupo:
        confirmacion = grupo.submit(r.confirmar, calculo, "sesion-inventada", guardar)
        assert entro.wait(10)
        descarte = grupo.submit(r.descartar_archivos, token, "sesion-inventada")
        try:
            assert esperando.wait(10), "El descarte no intentó tomar el candado"
            assert not descarte.done() and guardados == []
            # El candado de una confirmación no serializa otras sesiones.
            otro, _ = preparar(r, "otra-sesion-inventada")
            assert r.leer_archivos(otro, "otra-sesion-inventada")[0]
        finally:
            continuar.set()
        assert confirmacion.result(timeout=10) == "guardado"
        assert descarte.result(timeout=10) is None
    assert guardados == ["analisis inventado"]
    with pytest.raises(t.HistorialVencido):
        r.confirmar(calculo, "sesion-inventada", guardados.append)


def test_cierre_durante_primera_subida_impide_publicarla():
    r = registro()
    generacion = r.iniciar_subida("sesion-inventada")
    r.revocar("sesion-inventada")
    with pytest.raises(t.HistorialVencido):
        r.agregar(None, generacion, ((),), "sesion-inventada")
    assert not r.archivos._pendientes


def test_vencer_lista_impide_confirmar_aunque_preview_sea_mas_reciente():
    ahora = [0]
    r = registro(lambda: ahora[0])
    token = r.agregar(None, r.iniciar_subida("sesion-inventada"), ((),), "sesion-inventada")
    ahora[0] = 800
    _, generacion = r.leer_archivos(token, "sesion-inventada")
    calculo = r.publicar(token, generacion, "analisis inventado", "sesion-inventada")
    ahora[0] = 900
    with pytest.raises(t.HistorialVencido):
        r.confirmar(calculo, "sesion-inventada", lambda _: pytest.fail("No debe guardar"))


def test_limite_sesiones_no_reutiliza_generacion_expulsada(monkeypatch):
    monkeypatch.setattr(tokens_bancarios_ram, "MAXIMO_EN_MEMORIA", 2)
    r = registro()
    token, _ = preparar(r, "vieja-inventada")
    _, generacion = r.leer_archivos(token, "vieja-inventada")
    preparar(r, "segunda-inventada")
    preparar(r, "tercera-inventada")
    assert len(r._sesiones) == len(r.archivos._pendientes) == len(r.analisis._pendientes) == 2
    with pytest.raises(t.HistorialVencido):
        r.publicar(token, generacion, "analisis viejo inventado", "vieja-inventada")
    assert len(r._sesiones) <= 2
