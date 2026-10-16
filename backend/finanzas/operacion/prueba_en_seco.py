"""Prueba en seco del lector de avisos, para correr en la VM antes de desplegar.

El repositorio no tiene el cuerpo real de ningún aviso (solo encabezados
reales anonimizados), así que un cambio del lector (por ejemplo, el ítem 21:
avisos citados) se comprueba contra los correos reales sin tocar nada:

1. lee de la base, **en solo lectura**, los ``gmail_id`` de los movimientos con
   ``origen='gmail'`` (y, con ``--incluir-no-reconocidos``, los de
   ``correos_no_reconocidos``);
2. vuelve a descargar cada correo de Gmail (permiso ``gmail.readonly``);
3. lo pasa por la lógica actual completa: remitente y autenticación
   (``_motivo_rechazo``) y lectura del aviso en todas las
   versiones del cuerpo (``lector.clasificar_correo``);
4. imprime solo conteos y, para cada correo que no se leería como aviso
   válido, su fecha y su resultado. Nunca asuntos, montos, comercios,
   nombres, cuentas ni texto del correo.

Con ``--mostrar-previo`` (diagnóstico, ítem 21) muestra además, para cada
correo que sale ``citado`` o ``no reconocido``, lo que hay **delante** del
aviso en cada versión del cuerpo (ver ``describir_previo``): el estado de esa
versión, el texto previo al primer inicio de aviso y su clave de comparación
(``lector._clave_encabezado``). Todo enmascarado (dígitos -> ``#``,
direcciones de correo -> ``[correo]``), recortado a 300 caracteres y con los
caracteres invisibles escritos como ``\\uXXXX`` para que se vean. Nunca
muestra el aviso ni lo que va después. **Advertencia:** esa salida puede
traer texto de la plantilla del banco y quizá el nombre del dueño; hay que
revisarla y tapar lo personal antes de compartir una captura. Los correos
rechazados por remitente o autenticación no se muestran (el lector nunca los
lee).

Con ``--ayn`` (ítem 27, D30) hace otra cosa: antes de desplegar la lectura
del segundo remitente del banco (``gmail.REMITENTE_AYN``, pagos por PSE),
comprueba que sus correos pasan DMARC. Lee de la base, en solo lectura, la
fecha de inicio y los ids ya registrados; pide a Gmail los ids de **solo** esa
dirección desde la fecha de inicio (lo mismo que hará la sincronización) y
pasa cada correo por la misma lógica (``revisar_ayn``). Imprime solo
conteos (cuántos pasan la verificación de remitente y DMARC, cuántos se
rechazarían y por qué categoría genérica, cuántos se leerían como aviso y de
qué tipo, cuántos ya están registrados) y, para los que no se leerían, su
fecha y su resultado. Nunca montos, nombres, empresas, asuntos ni texto.

No escribe nada: la base se abre con ``mode=ro`` y no se llama a ninguna
función que guarde. Si el token de Gmail caduca, se renueva en memoria (con
la carpeta en solo lectura no se puede guardar y queda un aviso en el
registro; es lo esperado).

Uso::

    python -m finanzas.prueba_en_seco [--incluir-no-reconocidos] [--mostrar-previo]
    python -m finanzas.prueba_en_seco --ayn

Para correrla en la VM con un código distinto del desplegado y sin tocar la
app en marcha, ver deploy/GUIA.md 13.2 ("Prueba en seco...").

Códigos de salida: 0 terminó (aunque haya citados o no reconocidos: el
resultado se lee en la salida); 1 algún correo no se pudo descargar; 2 falta
configuración, la base o la autorización de Gmail.
"""

from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

from finanzas.modulos.sincronizacion.adaptadores.avisos import extractor, lector
from finanzas.modulos.sincronizacion.adaptadores.avisos.evaluacion import _motivo_rechazo
from finanzas.modulos.sincronizacion.publico import SincronizacionNoConfigurada, REMITENTES_OFICIALES
from finanzas.bootstrap.sincronizacion import cliente_desde_config
from finanzas.compartido.config import Config, ErrorConfiguracion
from finanzas.modulos.sincronizacion.contratos import REMITENTE_AYN, ClienteGmail, ErrorAutorizacionGmail
from finanzas.compartido.hora import ZONA_COLOMBIA

GRUPO_MOVIMIENTOS = "movimiento guardado"
GRUPO_NO_RECONOCIDOS = "no reconocido guardado"
GRUPO_AYN = "correo de ayn. en Gmail"

RESULTADO_VALIDO = "aviso válido"
RESULTADO_CITADO = "citado"
RESULTADO_NO_RECONOCIDO = "no reconocido"
RESULTADO_RECHAZADO = "rechazado por remitente o autenticación"
RESULTADO_ERROR = "error al descargar"
RESULTADO_ANTERIOR = "anterior a la fecha de inicio"

_POR_ESTADO = {
    lector.AVISO_VALIDO: RESULTADO_VALIDO,
    lector.AVISO_CITADO: RESULTADO_CITADO,
    lector.SIN_AVISO: RESULTADO_NO_RECONOCIDO,
}
_ORDEN = [RESULTADO_VALIDO, RESULTADO_CITADO, RESULTADO_NO_RECONOCIDO, RESULTADO_RECHAZADO, RESULTADO_ERROR]
# Solo con --ayn: además, los anteriores a la fecha de inicio.
_ORDEN_AYN = [*_ORDEN, RESULTADO_ANTERIOR]


@dataclass
class ResultadoPruebaEnSeco:
    """Conteos por grupo (de dónde venía el correo) y resultado.

    ``detalle`` guarda, para cada correo que no quedaría como aviso válido,
    solo (fecha "AAAA-MM-DD HH:MM" o "" si no se pudo descargar, grupo,
    resultado).
    """

    conteos: dict[str, dict[str, int]] = field(default_factory=dict)
    detalle: list[tuple[str, str, str]] = field(default_factory=list)
    # Solo con --mostrar-previo: índice en ``detalle`` -> líneas, ya
    # enmascaradas, con lo previo al aviso en cada versión del cuerpo.
    previos: dict[int, list[str]] = field(default_factory=dict)

    # Solo con --ayn: motivo genérico de rechazo -> cuántos; tipo del aviso
    # leído -> cuántos; y cuántos ids ya estaban registrados en la base.
    motivos_rechazo: dict[str, int] = field(default_factory=dict)
    tipos: dict[str, int] = field(default_factory=dict)
    ya_registrados: int = 0

    def sumar(self, grupo: str, resultado: str, fecha: str) -> None:
        por_grupo = self.conteos.setdefault(grupo, {r: 0 for r in (_ORDEN_AYN if grupo == GRUPO_AYN else _ORDEN)})
        por_grupo[resultado] += 1
        if resultado != RESULTADO_VALIDO:
            self.detalle.append((fecha, grupo, resultado))

    def total(self, resultado: str) -> int:
        return sum(por_grupo[resultado] for por_grupo in self.conteos.values())


# --- Diagnóstico --mostrar-previo -------------------------------------------

MAX_PREVIO = 300  # caracteres mostrados como máximo (antes de escapar invisibles)
LARGO_SIN_INICIO = 200  # sin inicio de aviso: cuánto del comienzo de la versión
# Una dirección de correo "a lo bruto": algo@algo sin espacios ni signos que
# la rodean. Mejor tapar de más que de menos.
_CORREO = re.compile(r"[^\s@<>()\[\]\"',;:«»]+@[^\s@<>()\[\]\"',;:«»]+")
# Categorías Unicode que se escapan: formato, separadores distintos del espacio
# normal, marcas (combinantes), control, uso privado, sin asignar y sustitutos.
_CATEGORIAS_ESCAPADAS = frozenset({"Cf", "Zs", "Zl", "Zp", "Mn", "Me", "Mc", "Cc", "Co", "Cn", "Cs"})
# Rellenos que se ven en blanco aunque Unicode los clasifique como letra o
# símbolo (los mismos de ``lector._RELLENOS_INVISIBLES``).
_RELLENOS = frozenset("ᅟᅠ⠀ㅤﾠ")


def _escapar_invisibles(texto: str) -> str:
    r"""Escribe como ``\uXXXX`` los caracteres invisibles o raros (y la barra
    ``\`` como ``\\``, para que no se confunda); el espacio normal, las letras
    con tilde y los signos visibles quedan igual."""
    partes = []
    for c in texto:
        if c == "\\":
            partes.append("\\\\")
        elif c != " " and (unicodedata.category(c) in _CATEGORIAS_ESCAPADAS or c in _RELLENOS):
            partes.append(ascii(c)[1:-1])
        else:
            partes.append(c)
    return "".join(partes)


def _enmascarar(texto: str) -> str:
    """Correos -> ``[correo]``; recorte a ``MAX_PREVIO`` (primera y última
    mitad); dígitos -> ``#``; invisibles escapados. Dice la longitud y si se
    recortó. El texto va entre « » para que se vean los espacios de los bordes."""
    sin_correos = _CORREO.sub("[correo]", texto)
    largo = len(sin_correos)
    if largo > MAX_PREVIO:
        mitad = MAX_PREVIO // 2
        visible = sin_correos[:mitad] + " [...] " + sin_correos[-mitad:]
        nota = f"{largo} caracteres, recortado a {MAX_PREVIO}: los primeros y los últimos {mitad}"
    else:
        visible = sin_correos
        nota = f"{largo} caracteres"
    visible = re.sub(r"\d", "#", visible)
    return f"({nota}) «{_escapar_invisibles(visible)}»"


def describir_previo(texto: str) -> tuple[str, str, str]:
    """(estado, previo enmascarado, clave enmascarada) de una versión del cuerpo.

    - estado: el de ``lector._analizar`` (``valido``, ``citado`` o
      ``sin_aviso``);
    - previo: el texto normalizado (tal como lo ve el lector) antes del
      **primer** inicio de aviso, que es lo que se compara. Si no hay
      ninguno, los primeros ``LARGO_SIN_INICIO`` caracteres, cortados antes
      de la primera palabra de aviso ("Bancolombia:", "Compraste",
      "Transferiste", "Recibiste") para no mostrar un aviso sin prefijo;
    - clave: ``lector._clave_encabezado`` de ese previo, sin las
      imágenes de la plantilla del comienzo (``IMAGENES_PLANTILLA``) y sin
      las direcciones de correo, que es lo que se busca en
      ``ENCABEZADOS_PERMITIDOS``.

    Nunca devuelve nada del aviso ni de lo que va después.
    """
    estado, _, _ = lector._analizar(texto)
    normalizado = extractor._normalizar(texto)
    inicio = lector._INICIO_AVISO.search(normalizado)
    if inicio is not None:
        previo = normalizado[: inicio.start()]
    else:
        previo = normalizado[:LARGO_SIN_INICIO]
        palabra = lector._OTRO_AVISO.search(previo)
        if palabra is not None:
            previo = previo[: palabra.start()]
    clave = lector._clave_encabezado(
        _CORREO.sub(" ", lector._sin_imagenes_plantilla(previo))
    )
    return estado, _enmascarar(previo), _enmascarar(clave)


def _nombre_version(i: int, total: int) -> str:
    # gmail.textos_del_cuerpo pone text/plain primero y HTML después; si el
    # correo trae una sola, desde CorreoGmail no se sabe cuál es.
    if total == 1:
        return "versión 1 de 1 (text/plain o HTML: el correo trae una sola)"
    nombre = {0: "text/plain", 1: "HTML"}.get(i, "otra")
    return f"versión {i + 1} de {total} ({nombre})"


def lineas_previo(textos: Sequence[str]) -> list[str]:
    """Líneas del diagnóstico, una versión del cuerpo tras otra, en el orden en
    que las revisa ``lector.clasificar_correo``."""
    lineas = []
    for i, texto in enumerate(textos):
        estado, previo, clave = describir_previo(texto)
        lineas += [
            f"    {_nombre_version(i, len(textos))}: estado {estado}",
            f"      previo {previo}",
            f"      clave  {clave}",
        ]
    return lineas


class BaseNoDisponible(Exception):
    """La base no existe o no se puede leer (el mensaje no lleva datos)."""


def ids_a_revisar(ruta_db: str, incluir_no_reconocidos: bool) -> list[tuple[str, str]]:
    """(gmail_id, grupo) de los correos ya registrados, leyendo en solo lectura."""
    ruta = Path(ruta_db)
    if not ruta.is_file():
        raise BaseNoDisponible(f"No existe la base en {ruta} (variable DB_PATH).")
    try:
        conexion = sqlite3.connect(f"{ruta.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as error:
        raise BaseNoDisponible(f"No se pudo abrir la base en solo lectura ({type(error).__name__}).") from None
    try:
        filas = [
            (str(fila[0]), GRUPO_MOVIMIENTOS)
            for fila in conexion.execute(
                "SELECT gmail_id FROM movimientos WHERE origen = 'gmail' AND gmail_id IS NOT NULL "
                "ORDER BY fecha_hora, id"
            )
        ]
        if incluir_no_reconocidos:
            filas += [
                (str(fila[0]), GRUPO_NO_RECONOCIDOS)
                for fila in conexion.execute("SELECT gmail_id FROM correos_no_reconocidos ORDER BY fecha, gmail_id")
            ]
    except sqlite3.Error as error:
        raise BaseNoDisponible(f"No se pudo leer la base ({type(error).__name__}).") from None
    finally:
        conexion.close()
    vistos: set[str] = set()
    return [(i, g) for i, g in filas if not (i in vistos or vistos.add(i))]


def datos_de_la_base(ruta_db: str) -> tuple[date, set[str]]:
    """(fecha de inicio, ids de Gmail ya registrados), leyendo en solo lectura.

    Lanza ``BaseNoDisponible`` si no hay base y
    ``SincronizacionNoConfigurada`` si falta la fecha de inicio.
    """
    ruta = Path(ruta_db)
    if not ruta.is_file():
        raise BaseNoDisponible(f"No existe la base en {ruta} (variable DB_PATH).")
    try:
        conexion = sqlite3.connect(f"{ruta.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as error:
        raise BaseNoDisponible(f"No se pudo abrir la base en solo lectura ({type(error).__name__}).") from None
    try:
        fila = conexion.execute("SELECT fecha_inicio FROM configuracion_saldo WHERE id = 1").fetchone()
        registrados = {
            str(f[0]) for f in conexion.execute(
                "SELECT gmail_id FROM movimientos WHERE gmail_id IS NOT NULL "
                "UNION SELECT gmail_id FROM correos_no_reconocidos"
            )
        }
    except sqlite3.Error as error:
        raise BaseNoDisponible(f"No se pudo leer la base ({type(error).__name__}).") from None
    finally:
        conexion.close()
    if fila is None:
        raise SincronizacionNoConfigurada(
            "Todavía no se ha configurado la fecha de inicio: no hay desde cuándo consultar."
        )
    try:
        return date.fromisoformat(str(fila[0])[:10]), registrados
    except ValueError:
        raise SincronizacionNoConfigurada("La fecha de inicio guardada no es válida.") from None


def revisar_ayn(
    cliente: ClienteGmail,
    fecha_inicio: date,
    registrados: set[str],
    remitentes_oficiales: str | Sequence[str] = REMITENTE_AYN,
) -> ResultadoPruebaEnSeco:
    """Lista los correos de ``cliente`` desde ``fecha_inicio`` y los clasifica
    como lo haría la sincronización, sin guardar nada.

    ``cliente`` debe consultar solo ``REMITENTE_AYN`` (``main`` lo crea así),
    y solo cuenta como "pasa" un correo que venga **exactamente** de
    ``REMITENTE_AYN`` con DMARC alineado con su dominio: lo que se quiere
    comprobar es esa dirección. Uno de la otra dirección oficial (o de
    cualquier otra) cuenta como rechazado por remitente.
    """
    resultado = ResultadoPruebaEnSeco()
    resultado.conteos[GRUPO_AYN] = {r: 0 for r in _ORDEN_AYN}
    for gmail_id in dict.fromkeys(cliente.listar_ids(fecha_inicio)):
        if gmail_id in registrados:
            resultado.ya_registrados += 1
        try:
            correo = cliente.obtener(gmail_id)
        except ErrorAutorizacionGmail:
            raise
        except Exception:
            resultado.sumar(GRUPO_AYN, RESULTADO_ERROR, "")
            continue
        fecha_colombia = correo.fecha.astimezone(ZONA_COLOMBIA)
        fecha = fecha_colombia.strftime("%Y-%m-%d %H:%M")
        if fecha_colombia.date() < fecha_inicio:
            resultado.sumar(GRUPO_AYN, RESULTADO_ANTERIOR, fecha)
            continue
        motivo = _motivo_rechazo(correo, remitentes_oficiales)
        if motivo is not None:
            resultado.motivos_rechazo[motivo] = resultado.motivos_rechazo.get(motivo, 0) + 1
            resultado.sumar(GRUPO_AYN, RESULTADO_RECHAZADO, fecha)
            continue
        estado, movimiento = lector.clasificar_correo(correo.textos)
        resultado.sumar(GRUPO_AYN, _POR_ESTADO[estado], fecha)
        if movimiento is not None:
            resultado.tipos[movimiento.tipo] = resultado.tipos.get(movimiento.tipo, 0) + 1
    return resultado


def informe_ayn(resultado: ResultadoPruebaEnSeco) -> list[str]:
    """Líneas para la salida de ``--ayn``: solo conteos, fechas y resultados."""
    c = resultado.conteos.get(GRUPO_AYN) or {r: 0 for r in _ORDEN_AYN}
    total = sum(c.values())
    pasan = c[RESULTADO_VALIDO] + c[RESULTADO_CITADO] + c[RESULTADO_NO_RECONOCIDO]
    motivos = ", ".join(f"{m} {n}" for m, n in sorted(resultado.motivos_rechazo.items()))
    tipos = ", ".join(f"{t} {n}" for t, n in sorted(resultado.tipos.items()))
    lineas = [
        "Prueba en seco de los correos de ayn. (no se escribió nada).",
        f"Correos de ayn. en Gmail desde la fecha de inicio: {total} "
        f"({resultado.ya_registrados} ya registrados en la base).",
        f"- pasan remitente y DMARC: {pasan}",
        f"- rechazados por remitente o autenticación: {c[RESULTADO_RECHAZADO]}" + (f" ({motivos})" if motivos else ""),
        f"- se leerían como aviso: {c[RESULTADO_VALIDO]}" + (f" ({tipos})" if tipos else ""),
        f"- quedarían como no reconocidos: {c[RESULTADO_CITADO] + c[RESULTADO_NO_RECONOCIDO]} "
        f"(citados {c[RESULTADO_CITADO]}, sin aviso {c[RESULTADO_NO_RECONOCIDO]})",
        f"- anteriores a la fecha de inicio: {c[RESULTADO_ANTERIOR]}; errores al descargar: {c[RESULTADO_ERROR]}",
    ]
    if resultado.detalle:
        lineas.append("Correos que no quedarían como aviso válido (fecha del correo -> resultado):")
        lineas += [f"  {fecha or 'sin fecha'} -> {res}" for fecha, _, res in resultado.detalle]
    if c[RESULTADO_RECHAZADO]:
        lineas.append("OJO: hay correos de ayn. rechazados. No despliegues sin revisarlo (deploy/GUIA.md 13.2).")
    elif total and not c[RESULTADO_ERROR]:
        lineas.append("Todos los correos de ayn. pasan remitente y DMARC.")
    return lineas


def revisar(
    ids: Sequence[tuple[str, str]],
    cliente: ClienteGmail,
    remitentes_oficiales: str | Sequence[str] = REMITENTES_OFICIALES,
    mostrar_previo: bool = False,
) -> ResultadoPruebaEnSeco:
    """Descarga y clasifica cada correo, sin guardar nada.

    Con ``mostrar_previo`` guarda en ``resultado.previos`` el diagnóstico de
    los correos citados o no reconocidos (no el de los rechazados por
    remitente o autenticación: el lector nunca los lee)."""
    resultado = ResultadoPruebaEnSeco()
    for gmail_id, grupo in ids:
        try:
            correo = cliente.obtener(gmail_id)
        except ErrorAutorizacionGmail:
            raise
        except Exception:
            resultado.sumar(grupo, RESULTADO_ERROR, "")
            continue
        fecha = correo.fecha.astimezone(ZONA_COLOMBIA).strftime("%Y-%m-%d %H:%M")
        if _motivo_rechazo(correo, remitentes_oficiales) is not None:
            resultado.sumar(grupo, RESULTADO_RECHAZADO, fecha)
            continue
        estado, _ = lector.clasificar_correo(correo.textos)
        resultado.sumar(grupo, _POR_ESTADO[estado], fecha)
        if mostrar_previo and estado != lector.AVISO_VALIDO:
            resultado.previos[len(resultado.detalle) - 1] = lineas_previo(correo.textos)
    return resultado


def informe(resultado: ResultadoPruebaEnSeco) -> list[str]:
    """Líneas para la salida: solo conteos, fechas y resultados."""
    revisados = sum(sum(c.values()) for c in resultado.conteos.values())
    lineas = [f"Prueba en seco del lector (no se escribió nada). Correos revisados: {revisados}."]
    for grupo in (GRUPO_MOVIMIENTOS, GRUPO_NO_RECONOCIDOS):
        if grupo in resultado.conteos:
            c = resultado.conteos[grupo]
            lineas.append(
                f"- {grupo} ({sum(c.values())}): " + ", ".join(f"{r} {c[r]}" for r in _ORDEN)
            )
    if resultado.detalle:
        lineas.append("Correos que no quedarían como aviso válido (fecha del correo, de dónde venía -> resultado):")
        if resultado.previos:
            lineas.append(
                "Con --mostrar-previo: texto delante del aviso en cada versión del cuerpo (dígitos -> #, "
                "correos -> [correo], invisibles como \\uXXXX). Puede traer tu nombre: tápalo antes de compartirlo."
            )
        for i, (fecha, grupo, res) in enumerate(resultado.detalle):
            lineas.append(f"  {fecha or 'sin fecha'}  {grupo} -> {res}")
            lineas += resultado.previos.get(i, [])
    else:
        lineas.append("Todos los correos revisados quedarían como aviso válido.")
    return lineas


def main(
    argv: list[str] | None = None,
    fabrica_cliente: Callable[[Config], ClienteGmail] = cliente_desde_config,
) -> int:
    """Punto de entrada de ``python -m finanzas.prueba_en_seco``."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="python -m finanzas.prueba_en_seco",
        description="Relee de Gmail los correos ya registrados con el lector actual, sin escribir nada.",
    )
    parser.add_argument(
        "--incluir-no-reconocidos", action="store_true",
        help="revisar también los correos guardados como no reconocidos",
    )
    parser.add_argument(
        "--mostrar-previo", action="store_true",
        help="diagnóstico: mostrar, enmascarado, el texto que hay delante del aviso en los correos citados "
        "o no reconocidos (puede traer tu nombre: revísalo antes de compartirlo)",
    )
    parser.add_argument(
        "--ayn", action="store_true",
        help="en vez de releer lo registrado, consultar en Gmail los correos del segundo remitente del banco "
        "(ayn., pagos PSE) desde la fecha de inicio y contar cuántos pasan DMARC y cómo se leerían",
    )
    args = parser.parse_args(argv)
    if args.ayn and (args.incluir_no_reconocidos or args.mostrar_previo):
        parser.error("--ayn no se combina con --incluir-no-reconocidos ni con --mostrar-previo")
    try:
        config = Config.desde_entorno()
    except ErrorConfiguracion as error:
        print(f"Error de configuración: {error}", file=sys.stderr)
        return 2
    if args.ayn:
        return _main_ayn(config, fabrica_cliente)
    try:
        ids = ids_a_revisar(config.db_path, args.incluir_no_reconocidos)
        resultado = revisar(ids, fabrica_cliente(config), config.gmail_remitentes, args.mostrar_previo)
    except (BaseNoDisponible, SincronizacionNoConfigurada, ErrorAutorizacionGmail) as error:
        print(f"No se pudo hacer la prueba en seco: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        # Solo el tipo: el mensaje de una excepción podría traer datos del correo.
        print(f"La prueba en seco falló ({type(error).__name__}).", file=sys.stderr)
        return 1
    for linea in informe(resultado):
        print(linea)
    return 1 if resultado.total(RESULTADO_ERROR) else 0


def _main_ayn(config: Config, fabrica_cliente: Callable[[Config], ClienteGmail]) -> int:
    try:
        fecha_inicio, registrados = datos_de_la_base(config.db_path)
        # Un cliente que consulta solo la dirección ayn.
        cliente = fabrica_cliente(replace(config, gmail_remitentes=(REMITENTE_AYN,)))
        resultado = revisar_ayn(cliente, fecha_inicio, registrados, REMITENTE_AYN)
    except (BaseNoDisponible, SincronizacionNoConfigurada, ErrorAutorizacionGmail) as error:
        print(f"No se pudo hacer la prueba en seco: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        # Solo el tipo: el mensaje de una excepción podría traer datos del correo.
        print(f"La prueba en seco falló ({type(error).__name__}).", file=sys.stderr)
        return 1
    for linea in informe_ayn(resultado):
        print(linea)
    return 1 if resultado.total(RESULTADO_ERROR) else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
