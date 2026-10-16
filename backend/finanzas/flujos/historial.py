"""Historial normalizado y preparación de avisos sin base de datos ni HTTP."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from finanzas.modulos.importaciones.publico import MovimientoExcel

MAXIMO_ARCHIVOS = 12
MAXIMO_FILAS_HISTORIAL = 1440
MAXIMO_CORREOS = 10000


class ErrorArranque(Exception):
    """Error de entrada que no contiene datos privados del archivo."""


@dataclass(frozen=True)
class Historial:
    filas: tuple[MovimientoExcel, ...]
    cobertura: tuple[tuple[date, date], ...]
    huecos: tuple[tuple[date, date], ...]
    archivos: int
    filas_leidas: int
    solapadas: int
    truncados: int

    @property
    def desde(self):
        return min((f.fecha for f in self.filas), default=None)

    @property
    def hasta(self):
        return max((f.fecha for f in self.filas), default=None)


def identidad(fila):
    """Descripción recortada no es una identidad de movimiento (D38)."""
    return fila.fecha, fila.monto_centavos, fila.referencia


def _unir_intervalos(intervalos):
    salida = []
    for desde, hasta in sorted(intervalos):
        if salida and desde <= salida[-1][1] + timedelta(days=1):
            salida[-1] = (salida[-1][0], max(hasta, salida[-1][1]))
        else:
            salida.append((desde, hasta))
    return tuple(salida)


def unir_archivos(archivos):
    """Unión de multiconjuntos: conserva la mayor multiplicidad por archivo.

    Dos filas iguales dentro de una descarga siguen siendo dos; subir otra
    descarga del mismo periodo no las convierte en cuatro. Sin identificador
    bancario, nuevas repeticiones indistinguibles solo se acreditan cuando
    aparecen juntas en alguna descarga: no se adivinan.
    """
    archivos = tuple(tuple(a) for a in archivos)
    if not archivos or len(archivos) > MAXIMO_ARCHIVOS:
        raise ErrorArranque(f"Agrega entre 1 y {MAXIMO_ARCHIVOS} archivos del banco.")
    total = sum(map(len, archivos))
    if total > MAXIMO_FILAS_HISTORIAL:
        raise ErrorArranque("El historial tiene demasiadas filas. Divide la importación en periodos más pequeños.")
    maximos, variantes, observados, cobertura = Counter(), defaultdict(list), [], []
    truncados = 0
    for archivo in archivos:
        cantidades = Counter(identidad(f) for f in archivo)
        maximos |= cantidades
        for fila in archivo:
            variantes[identidad(fila)].append(fila)
        if not archivo:
            continue
        desde, hasta = min(f.fecha for f in archivo), max(f.fecha for f in archivo)
        observados.append((desde, hasta))
        # El día más antiguo de cada archivo puede venir cortado: el tope de
        # filas del banco no se conoce (D51). Ese día no acredita cobertura.
        truncados += 1
        desde += timedelta(days=1)
        if desde <= hasta:
            cobertura.append((desde, hasta))
    filas = []
    for clave in sorted(maximos, key=lambda c: (c[0], c[1], c[2] or "")):
        versiones = variantes[clave]
        # Representación estable incluso si los archivos cambian de orden.
        modelo = min(versiones, key=lambda f: f.descripcion)
        fila = MovimientoExcel(modelo.fecha, modelo.monto_centavos, modelo.descripcion,
            modelo.referencia, any(f.referencia_sin_formato for f in versiones))
        filas.extend([fila] * maximos[clave])
    rangos = _unir_intervalos(observados)
    huecos = tuple((anterior[1] + timedelta(days=1), siguiente[0] - timedelta(days=1))
        for anterior, siguiente in zip(rangos, rangos[1:]))
    return Historial(tuple(filas), _unir_intervalos(cobertura), huecos,
        len(archivos), total, total - len(filas), truncados)


def calcular_saldo_inicial(historial, saldo_actual_centavos):
    if type(saldo_actual_centavos) is not int or saldo_actual_centavos < 0:
        raise ErrorArranque("Escribe un saldo actual válido, en centavos enteros y sin signo negativo.")
    if not historial.filas:
        raise ErrorArranque("Los archivos no tienen movimientos. Agrega un reporte con historial.")
    ingresos = sum(f.monto_centavos for f in historial.filas if f.monto_centavos > 0)
    gastos = -sum(f.monto_centavos for f in historial.filas if f.monto_centavos < 0)
    inicial = saldo_actual_centavos - ingresos + gastos
    if inicial < 0:
        raise ErrorArranque("El saldo inicial calculado es negativo. Revisa el saldo actual y los archivos antes de continuar.")
    return {"saldo_actual_centavos": saldo_actual_centavos, "saldo_inicial_centavos": inicial,
        "ingresos_centavos": ingresos, "gastos_centavos": gastos,
        "fecha_inicio_propuesta": historial.desde.isoformat(),
        "desde": historial.desde.isoformat(), "hasta": historial.hasta.isoformat(),
        "archivos": historial.archivos, "filas": len(historial.filas),
        "filas_solapadas": historial.solapadas, "archivos_truncados": historial.truncados,
        "cobertura_verificada": False,
        "huecos": [{"desde": d.isoformat(), "hasta": h.isoformat()} for d, h in historial.huecos],
        "advertencia_cobertura": "El Excel muestra los movimientos descargados, pero no acredita que estén todos. Revisa que tus reportes incluyan el periodo completo.",
    }


@dataclass(frozen=True)
class AvisoNormalizado:
    gmail_id: str
    movimiento: object | None
    fecha: str | None = None
    asunto: str | None = None
    rechazado: bool = False


@dataclass(frozen=True)
class AnalisisArranque:
    historial: Historial
    avisos: tuple[AvisoNormalizado, ...]
    modo: str
    huella: str
    vista: dict
    balance: dict | None = None


def preparar_avisos(cliente, desde, registrados, remitentes, evaluar_correo, zona_colombia):
    """Red y autenticación fuera de cualquier transacción de escritura.

    El registro efímero recibe solo la salida del extractor validado o los
    metadatos de no reconocidos; nunca el objeto CorreoGmail ni sus cuerpos.
    Una descarga fallida aborta el cálculo: no se entrega un saldo calculado
    con una sincronización parcial sin que el dueño lo sepa.
    """
    salida = []
    ids = tuple(dict.fromkeys(cliente.listar_ids(desde)))
    if len(ids) > MAXIMO_CORREOS:
        raise ErrorArranque("Hay demasiados avisos en ese periodo. Empieza por un periodo más corto y extiende después el historial.")
    for ident in ids:
        if ident in registrados:
            continue
        correo = cliente.obtener(ident)
        fecha = correo.fecha.astimezone(zona_colombia).replace(tzinfo=None)
        if fecha.date() < desde:
            continue
        motivo, movimiento = evaluar_correo(correo, remitentes)
        if movimiento is not None:
            salida.append(AvisoNormalizado(ident, movimiento))
        else:
            salida.append(AvisoNormalizado(ident, None, fecha.isoformat(timespec="seconds"), correo.asunto, motivo is not None))
    return tuple(salida)
