"""Pruebas de propiedades (Hypothesis, D44) de las reglas de oro de la conciliación.

Hypothesis genera cientos de combinaciones de movimientos del correo,
ingresos manuales, ajustes y filas del banco (montos de una lista corta para
que haya muchas repeticiones, destinos que coinciden o no, días cruzados y
filas anteriores a la fecha de inicio) y comprueba que siempre:

1. importar dos veces es igual que importar una vez;
2. un saldo ya cuadrado (ajuste posterior a todas las filas) sigue igual;
3. ningún movimiento se borra solo, ni cambia lo que llegó del correo salvo
   el monto de un parecido;
4. en la base nunca queda un número de ``Referencia`` completo;
5. cada fila del banco termina en exactamente un lugar y cada movimiento se
   empareja como mucho una vez (motor puro).

Datos inventados. Cada ejemplo trabaja sobre una copia de una base plantilla
ya migrada (migrar en cada ejemplo haría la suite lenta).
"""

from __future__ import annotations
from finanzas.bootstrap.saldo import componer_saldo

import shutil
from collections import Counter
import tempfile
from datetime import date, datetime, time
from pathlib import Path

import pytest
from hypothesis import HealthCheck, event, example, given, settings
from hypothesis import strategies as st

from finanzas.modulos.importaciones import motor as c
from finanzas import db, importacion, sincronizacion
from finanzas.modulos.sincronizacion.adaptadores.avisos import extractor
from finanzas.modulos.importaciones.adaptadores.archivos.excel_bancolombia import MovimientoExcel, ultimos_4_de_referencia
from tests.soporte.ayudas_db import sql as _sql
from tests.soporte.conciliacion_propiedades import Base, plantilla, sql  # ayudas compartidas

AJUSTES = settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])

MONTOS = [100000, 355000, 620000, 950000, 980000, 1065000, 16000000]
DESCRIPCIONES_CORREO = ["TIENDA EJEMPLO", "WOMPI EJEMPLO", "*3000000001", "*3000000002", "PERSONA EJEMPLO"]
DESCRIPCIONES_BANCO = ["COMPRA EN  TIENDA EJEMPLO", "COMPRA EN  WOMPI EJEMPLO", "TRANSFERENCIAS A NEQUI",
                       "COBRO VIAJE TRANSPORTE MASIVO", "TRANSFERENCIA CTA SUC VIRTUAL"]








# --- Estrategias ------------------------------------------------------------------------------

_dia = st.integers(min_value=1, max_value=28)
_correo = st.tuples(_dia, st.sampled_from(["compra", "transferencia", "ingreso"]),
                    st.sampled_from(MONTOS), st.sampled_from(DESCRIPCIONES_CORREO))
# Referencias de 5 a 12 dígitos que empiezan por 7: ninguna descripción ni
# fecha de la base contiene una racha así, así que si aparece es que se guardó.
_referencia_completa = st.text(alphabet="0123456789", min_size=4, max_size=11).map(lambda r: "7" + r)
_referencia = st.one_of(st.none(), _referencia_completa, st.sampled_from(["3000000001", "3000000002"]),
                        st.sampled_from(["PSE0000001", "12", "ABC"]))
_fila = st.tuples(
    st.integers(min_value=-2, max_value=28),  # 0 o menos: julio, antes de la fecha de inicio
    st.sampled_from(MONTOS), st.booleans(), st.integers(min_value=-3, max_value=3),
    st.sampled_from(DESCRIPCIONES_BANCO), _referencia,
)
@st.composite
def _escenario(draw):
    """Correo, ingresos manuales y filas del banco. Parte de las filas sale de
    lo del correo (mismo día o ±1, monto exacto o parecido) para que haya
    muchas confirmaciones, correcciones y preguntas, no solo filas sueltas."""
    correos = draw(st.lists(_correo, max_size=8))
    manuales = draw(st.lists(st.tuples(_dia, st.sampled_from(MONTOS)), max_size=2))
    filas = draw(st.lists(_fila, max_size=10))
    for dia, tipo, monto, _descripcion in correos + [(d, "ingreso", m, "") for d, m in manuales]:
        if draw(st.booleans()):
            corrimiento = draw(st.sampled_from([0, 0, 0, 1, -1]))
            filas.append((max(1, min(28, dia + corrimiento)), monto, tipo != "ingreso",
                          draw(st.sampled_from([0, 0, -3, 2, 4])), draw(st.sampled_from(DESCRIPCIONES_BANCO)),
                          None))
    return {"correos": correos, "manuales": manuales, "filas": draw(st.permutations(filas))}


def _fecha(dia: int) -> date:
    return date(2026, 8, dia) if dia >= 1 else date(2026, 7, 31 + dia)


def _a_excel(filas) -> list[MovimientoExcel]:
    """Como las devolvería el lector: de la Referencia solo los últimos 4 dígitos."""
    salida = []
    for dia, monto, es_gasto, ajuste_pct, descripcion, referencia in filas:
        valor = monto + monto * ajuste_pct // 100  # a veces un monto parecido
        destino, sin_formato = ultimos_4_de_referencia(referencia)
        salida.append(MovimientoExcel(_fecha(dia), -valor if es_gasto else valor, descripcion, destino, sin_formato))
    return salida


def _preparar(conn, escenario, ajuste=0) -> None:
    with db.transaccion(conn):
        for i, (dia, tipo, monto, descripcion) in enumerate(escenario["correos"]):
            conn.execute(db.movimientos.insert().values(
                fecha_hora=f"2026-08-{dia:02d}T10:00:00", monto_centavos=monto, tipo=tipo,
                descripcion=descripcion, origen="gmail", gmail_id=f"id-inventado-{i}",
            ))
        for dia, monto in escenario["manuales"]:
            conn.execute(db.movimientos.insert().values(
                fecha_hora=f"2026-08-{dia:02d}T09:00:00", monto_centavos=monto, tipo="ingreso",
                descripcion="Ingreso", origen="manual", estado="provisional",
            ))
        if ajuste:
            conn.execute(db.movimientos.insert().values(
                fecha_hora="2026-09-15T18:00:00", monto_centavos=ajuste, tipo="ajuste",
                descripcion="Ajuste de saldo", origen="manual",
            ))


def _foto(conn) -> dict:
    return {
        "movimientos": [tuple(f) for f in sql(conn, "SELECT * FROM movimientos ORDER BY id")],
        "preguntas": [tuple(f) for f in sql(conn, "SELECT * FROM preguntas_conciliacion ORDER BY id")],
        "candidatos": [tuple(f) for f in sql(conn, "SELECT * FROM candidatos_pregunta ORDER BY 1, 2")],
    }


# --- Flujo completo: importar, avisos tardíos y respuestas del dueño -------------------------------
#
# El "mundo" de cada ejemplo: las filas del banco son los movimientos reales
# de la cuenta; cada aviso tardío es el aviso de UNA fila concreta (exacto o
# con un monto parecido, dentro del 5 %), y el dueño sabe de qué fila es cada
# aviso y responde de forma coherente con eso. Lo demás (sí o no, ¿ya estaba?)
# lo elige Hypothesis. El oráculo (``_comprobar_reglas_de_oro``) no usa la
# lógica que elige candidatos: solo cuenta.

FIN_DE_MES = 46  # "día" del ajuste posterior a todas las filas (15 de septiembre)


def _fecha_ajuste(dia: int) -> str:
    return "2026-09-15T18:00:00" if dia == FIN_DE_MES else f"2026-08-{dia:02d}T18:00:00"


def _preparar_con_ajuste(conn, escenario, dia_ajuste: int, monto_ajuste: int) -> None:
    _preparar(conn, escenario)
    with db.transaccion(conn):
        conn.execute(db.movimientos.insert().values(
            fecha_hora=_fecha_ajuste(dia_ajuste), monto_centavos=monto_ajuste, tipo="ajuste",
            descripcion="Ajuste de saldo", origen="manual",
        ))


def _clave(fecha, monto_con_signo) -> tuple[str, int]:
    return (str(fecha)[:10], int(monto_con_signo))


def _avisos_tardios(conn, data) -> dict[str, tuple[extractor.MovimientoExtraido, tuple[str, int]]]:
    """Avisos de algunas filas que entraron sin aviso o que esperan respuesta.

    Devuelve ``gmail_id -> (aviso, clave de su fila)``. Cada aviso es exacto,
    parecido sin nombre en común ("AVISO INVENTADO") o parecido con el nombre
    del banco; este último solo si su fila es la única de su día, para que el
    emparejamiento automático por nombre (D38) no pueda tomar otra.
    """
    filas = [
        (date.fromisoformat(f[0][:10]), str(f[1]), int(f[2]), str(f[3]))
        for f in sql(conn, "SELECT fecha_hora, tipo, monto_centavos, descripcion FROM movimientos "
                           "WHERE origen = 'extracto' AND estado = 'sin_aviso' ORDER BY id")
    ]
    for f in sql(conn, "SELECT fecha, monto_centavos, referencia, descripcion FROM preguntas_conciliacion "
                       "WHERE fuente = 'banco' AND respuesta IS NULL ORDER BY id"):
        fila = c.FilaBanco(date.fromisoformat(f[0]), int(f[1]), str(f[3]), f[2])
        filas.append((fila.fecha, c.tipo_de_fila(fila), abs(fila.monto_centavos), fila.descripcion))
    dias = Counter(f[0] for f in sql(conn, "SELECT substr(fecha_hora, 1, 10) FROM movimientos "
                                           "WHERE fecha_banco IS NOT NULL OR origen = 'extracto'"))
    dias.update(f[0] for f in sql(conn, "SELECT fecha FROM preguntas_conciliacion WHERE fuente = 'banco'"))
    avisos = {}
    for i, (fecha, tipo, monto, descripcion) in enumerate(filas):
        clase = data.draw(st.sampled_from(["ninguno", "exacto", "parecido", "parecido con nombre"]),
                          label=f"aviso {i}")
        if clase == "ninguno":
            continue
        valor, texto = monto, "AVISO INVENTADO"
        if clase != "exacto":
            diferencia = max(1, monto * data.draw(st.integers(min_value=1, max_value=5), label=f"% {i}") // 100)
            valor = monto + diferencia if data.draw(st.booleans(), label=f"más {i}") else monto - diferencia
            if clase == "parecido con nombre" and dias[fecha.isoformat()] == 1:
                texto = descripcion
        avisos[f"id-tarde-{i}"] = (
            extractor.MovimientoExtraido(tipo, valor, datetime.combine(fecha, time(12, 0)), texto),
            _clave(fecha, c.signo(tipo) * monto),
        )
    return avisos


def _recibir(conn, avisos) -> None:
    for gmail_id, (movimiento, _clave_fila) in avisos.items():
        sincronizacion._guardar_movimiento(conn, gmail_id, movimiento)
    # Para ver con --hypothesis-show-statistics que se recorren los caminos.
    if sql(conn, "SELECT 1 FROM candidatos_pregunta WHERE de_aviso = 1"):
        event("aviso reservado en una fila que espera")
    if sql(conn, "SELECT 1 FROM preguntas_conciliacion WHERE fuente = 'correo'"):
        event("aviso que espera en una pregunta \"¿es el mismo?\"")
    if sql(conn, "SELECT 1 FROM preguntas_conciliacion WHERE tipo = 'ya_estaba_en_ajuste'"):
        event("pregunta del mismo día del ajuste")


def _clave_de(conn, movimiento_id: int) -> tuple[str, int] | None:
    """Clave de la fila del banco que representa el movimiento, si ya la tiene."""
    f = sql(conn, "SELECT fecha_banco, tipo, monto_centavos FROM movimientos WHERE id = ?", (movimiento_id,))[0]
    return None if f[0] is None else _clave(f[0], c.signo(f[1]) * int(f[2]))


def _responder_como_el_duenio(conn, data, avisos) -> None:
    """Responde todo. El dueño sabe de qué fila es cada aviso: lo usa para su
    fila y nunca dice que un aviso es otra cosa. El resto lo decide Hypothesis."""
    clave_del_aviso = {
        int(f[0]): avisos[f[1]][1]
        for f in sql(conn, "SELECT id, gmail_id FROM movimientos WHERE gmail_id LIKE 'id-tarde-%'")
    }
    while True:
        pendientes = importacion.preguntas_pendientes(conn)
        if not pendientes:
            return
        p = pendientes[0]
        if p["fuente"] == "correo":
            gmail_id = sql(conn, "SELECT gmail_id FROM preguntas_conciliacion WHERE id = ?", (p["id"],))[0][0]
            propia = avisos[gmail_id][1]
            suyos = [m for m in p["candidatos"] if _clave_de(conn, m) == propia
                     and not sql(conn, "SELECT gmail_id FROM movimientos WHERE id = ? AND gmail_id IS NOT NULL", (m,))]
            if suyos:
                importacion.responder_pregunta(conn, p["id"], si=True, movimiento_id=suyos[0])
            else:  # ninguno es su fila: no es el mismo
                importacion.responder_pregunta(conn, p["id"], si=False)
                clave_del_aviso.update({
                    int(f[0]): propia for f in sql(conn, "SELECT id FROM movimientos WHERE gmail_id = ?", (gmail_id,))
                })
            continue
        propia = _clave(p["fecha"], p["monto_centavos"])
        libres = [m for m in p["candidatos"]
                  if sql(conn, "SELECT 1 FROM movimientos WHERE id = ? AND fecha_banco IS NULL", (m,))]
        su_aviso = [m for m in libres if clave_del_aviso.get(m) == propia]
        ajenos = [m for m in libres if m not in clave_del_aviso]  # nunca el aviso de otra fila
        if any(clave == propia for _aviso, clave in avisos.values()):
            # Su aviso tardío existe en este mundo (aunque todavía espere en otra
            # pregunta): la fila es la de ese aviso, nunca otro movimiento (D50, A).
            ajenos = []
        ya_estaba = data.draw(st.booleans(), label=f"ya estaba {p['id']}")
        if p["tipo"] == c.PREGUNTA_YA_ESTABA:
            # Sin candidato libre (o solo avisos de otras filas), "ninguno de estos":
            # se agrega la fila y los avisos siguen esperando (D50, B).
            elegido = su_aviso[0] if su_aviso else (ajenos[0] if ajenos else None)
            importacion.responder_pregunta(conn, p["id"], si=ya_estaba, movimiento_id=elegido,
                                           ninguno=elegido is None)
            continue
        if su_aviso:
            importacion.responder_pregunta(conn, p["id"], si=True, movimiento_id=su_aviso[0],
                                           ya_estaba_en_ajuste=ya_estaba)
        elif ajenos and data.draw(st.booleans(), label=f"es el mismo {p['id']}"):
            importacion.responder_pregunta(conn, p["id"], si=True, movimiento_id=ajenos[0],
                                           ya_estaba_en_ajuste=ya_estaba)
        else:
            importacion.responder_pregunta(conn, p["id"], si=False, ya_estaba_en_ajuste=ya_estaba)


def _comprobar_reglas_de_oro(conn, escenario, avisos, originales: set[int]) -> None:
    """Oráculo independiente: solo cuenta, no elige candidatos.

    * cada fila real del banco está representada exactamente una vez: los
      movimientos respaldados por el banco son, uno a uno, las filas;
    * cada aviso tardío es el aviso de una fila: aparece una sola vez y en un
      movimiento respaldado por el banco, nunca suelto (contado dos veces);
    * lo que queda sin respaldo es solo lo que ya estaba (correo y manual);
    * el saldo es el inicial + las filas + lo sin respaldo + el ajuste.
    """
    filas = Counter(
        _clave(m.fecha, m.monto_centavos) for m in _a_excel(escenario["filas"]) if m.fecha >= date(2026, 8, 1)
    )
    respaldados = Counter(
        _clave(f[0], c.signo(f[1]) * int(f[2]))
        for f in sql(conn, "SELECT fecha_banco, tipo, monto_centavos FROM movimientos "
                           "WHERE fecha_banco IS NOT NULL")
    )
    assert respaldados == filas
    for gmail_id in avisos:
        assert [tuple(f) for f in sql(conn, "SELECT fecha_banco IS NOT NULL FROM movimientos WHERE gmail_id = ?",
                                      (gmail_id,))] == [(1,)]
    sin_respaldo = {int(f[0]): c.signo(f[1]) * int(f[2]) for f in sql(
        conn, "SELECT id, tipo, monto_centavos FROM movimientos WHERE fecha_banco IS NULL AND tipo <> 'ajuste'")}
    assert set(sin_respaldo) <= originales
    ajustes = sum(int(f[0]) for f in sql(conn, "SELECT monto_centavos FROM movimientos WHERE tipo = 'ajuste'"))
    inicial = sql(conn, "SELECT saldo_inicial_centavos FROM configuracion_saldo")[0][0]
    assert componer_saldo(conn).saldo_actual() == inicial + sum(k[1] * n for k, n in filas.items()) \
        + sum(sin_respaldo.values()) + ajustes


def _dia_ajuste(data, escenario) -> int:
    """Posterior a todo, o el día de alguna fila (para que haya preguntas del mismo día)."""
    dias = sorted({f[0] for f in escenario["filas"] if f[0] >= 1})
    return data.draw(st.sampled_from([FIN_DE_MES, *dias]) if dias else st.just(FIN_DE_MES), label="día del ajuste")


_monto_ajuste = st.one_of(st.integers(min_value=-5_000_000, max_value=-1), st.integers(min_value=1, max_value=5_000_000))


def _hasta_el_ajuste(escenario, dia_ajuste: int) -> dict:
    """Solo filas hasta el día del ajuste: lo posterior mueve el saldo, como debe."""
    filas = [f for f in escenario["filas"] if dia_ajuste == FIN_DE_MES or f[0] <= dia_ajuste]
    return {**escenario, "filas": filas}


def _flujo(conn, escenario, data):
    originales = {int(f[0]) for f in sql(conn, "SELECT id FROM movimientos WHERE tipo <> 'ajuste'")}
    filas = _a_excel(escenario["filas"])
    importacion.importar(conn, filas)
    avisos = _avisos_tardios(conn, data)
    _recibir(conn, avisos)
    _responder_como_el_duenio(conn, data, avisos)
    _comprobar_reglas_de_oro(conn, escenario, avisos, originales)
    return filas, avisos


# --- Casos fijos (@example) ---------------------------------------------------------------------------
#
# ``st.data()`` no admite un valor en ``@example``; ``_Elecciones`` hace sus
# veces: devuelve lo elegido para cada etiqueta y, si no está, "ninguno" (un
# aviso) o False (lo demás).

class _Elecciones:
    def __init__(self, **por_etiqueta):
        self._por_etiqueta = {k.replace("_", " "): v for k, v in por_etiqueta.items()}

    def draw(self, _estrategia, label: str):
        if label in self._por_etiqueta:
            return self._por_etiqueta[label]
        return "ninguno" if label.startswith("aviso ") else False

    def __repr__(self) -> str:
        return f"_Elecciones({self._por_etiqueta!r})"


# Ítem 44: un aviso exacto de una fila que espera ($3.443,50) también es un
# parecido sin apoyo de otra del mismo día que espera ($3.585,50), así que
# queda reservado en las dos preguntas. El dueño responde "no" a la de
# $3.585,50: antes eso exigía elegir un candidato (y la pantalla no ofrecía
# "son distintos"); ahora esa fila entra sin aviso y el aviso sigue con la suya.
CASO_AVISO_RESERVADO_EN_DOS_FILAS = {
    "correos": [(1, "compra", 355000, "TIENDA EJEMPLO")],
    "manuales": [],
    "filas": [(1, 355000, True, 1, "COMPRA EN  TIENDA EJEMPLO", None),
              (1, 355000, True, -3, "COMPRA EN  TIENDA EJEMPLO", None)],
}
# También del ítem 44 (corrida con max_examples alto): el aviso exacto de una
# fila que espera ($9.690) es parecido sin apoyo de otra que entró sin aviso
# ($10.094) y queda en una pregunta "¿es el mismo?". Si el dueño responde
# primero "no" a la fila (que entra sin aviso) y luego "no" a la pregunta del
# aviso, el aviso quedaba suelto: contado dos veces.
CASO_AVISO_QUE_ESPERA_Y_SU_FILA_ENTRA = {
    "correos": [(1, "transferencia", 950000, "*3000000001")],
    "manuales": [],
    "filas": [(1, 980000, True, 3, "COMPRA EN  TIENDA EJEMPLO", None),
              (1, 950000, True, 2, "COMPRA EN  TIENDA EJEMPLO", None)],
}
# Y: dos cobros iguales del mismo día del ajuste y sus dos avisos (uno parecido,
# otro exacto). El dueño usa el parecido para la primera fila; el exacto, que
# solo estaba reservado en esa pregunta, quedaba suelto y la segunda fila
# entraba aparte: contado dos veces.
CASO_DOS_FILAS_IGUALES_Y_EL_AVISO_QUE_SOBRA = {
    "correos": [],
    "manuales": [],
    "filas": [(4, 355000, True, 0, "COMPRA EN  TIENDA EJEMPLO", None),
              (4, 355000, True, 0, "COMPRA EN  TIENDA EJEMPLO", None)],
}


# Ítem 45 (D50), con max_examples=2000:
# A. La fila de $9.690 es el cargo del correo de $9.500 y además tiene su aviso
#    tardío exacto; el dueño simulado decía que era el correo, contra su propio
#    mundo. Se corrigió la prueba: con su aviso en el mundo, nunca "otro movimiento".
# B. Dos ingresos del día del ajuste ($3.550 y $3.585,50) y el aviso exacto de uno,
#    reservado en las dos preguntas "¿ya estaba en el saldo?": para la otra no
#    había salida sin elegir el aviso ajeno. Ahora hay "ninguno de estos".
CASO_DOS_INGRESOS_DEL_DIA_DEL_AJUSTE = {
    "correos": [],
    "manuales": [],
    "filas": [(1, 355000, False, 0, "COMPRA EN  TIENDA EJEMPLO", None),
              (1, 355000, False, 1, "COMPRA EN  TIENDA EJEMPLO", None)],
}
# C/D. Un aviso parecido de una fila que espera llega cuando la fila que sí es
#    su par está reservada por otra pregunta (o ni siquiera entró): se escondía,
#    y tras los "no" el aviso quedaba suelto. Ahora se muestran también las
#    reservadas y un "no" que deja otro candidato dudoso vuelve a preguntar.
CASO_TRES_INGRESOS_Y_DOS_AVISOS = {
    "correos": [],
    "manuales": [(20, 980000), (20, 980000)],
    "filas": [(19, 1065000, False, 0, "COMPRA EN  TIENDA EJEMPLO", None),
              (19, 980000, False, -3, "COMPRA EN  TIENDA EJEMPLO", None),
              (19, 980000, False, 2, "COMPRA EN  TIENDA EJEMPLO", None)],
}


# Revisión del 45 (semilla 224878410948398485243243658554936322513, reducido a
# mano): el aviso exacto de una fila que entró sin aviso ($9.996 del día 1)
# llega cuando esa fila está reservada por la pregunta de otro aviso; se
# reservaba en la fila que espera del día 2 y, al sobrar, quedaba suelto.
CASO_AVISO_DE_FILA_RESERVADA_Y_OTRA_QUE_ESPERA = {
    "correos": [(2, "compra", 980000, "TIENDA EJEMPLO"), (2, "compra", 980000, "TIENDA EJEMPLO")],
    "manuales": [],
    "filas": [(1, 1065000, True, 0, "COMPRA EN  TIENDA EJEMPLO", None),
              (2, 980000, True, 2, "COMPRA EN  TIENDA EJEMPLO", None),
              (1, 980000, True, 2, "COMPRA EN  TIENDA EJEMPLO", None)],
}


def _ejemplos_44(prueba):
    """Los casos fijos de los ítems 44 y 45, para las propiedades con avisos tardíos."""
    tres = {"aviso_0": "exacto", "aviso_1": "parecido", "%_1": 2, "más_1": True}
    casos = [
        (CASO_AVISO_RESERVADO_EN_DOS_FILAS, {"aviso_1": "exacto", "día_del_ajuste": FIN_DE_MES}),
        (CASO_AVISO_QUE_ESPERA_Y_SU_FILA_ENTRA, {"aviso_1": "exacto", "día_del_ajuste": FIN_DE_MES}),
        (CASO_DOS_FILAS_IGUALES_Y_EL_AVISO_QUE_SOBRA,
         {"día_del_ajuste": 4, "aviso_0": "parecido", "%_0": 1, "más_0": False, "aviso_1": "exacto"}),
        # 45-A: el mismo escenario que el anterior del 44, con el dueño que antes se contradecía.
        (CASO_AVISO_QUE_ESPERA_Y_SU_FILA_ENTRA,
         {"aviso_1": "exacto", "es_el_mismo_1": True, "día_del_ajuste": FIN_DE_MES}),
        # 45-B
        (CASO_DOS_INGRESOS_DEL_DIA_DEL_AJUSTE, {"día_del_ajuste": 1, "aviso_0": "exacto"}),
        # 45-C/D: aviso parecido con su fila escondida, y con el ajuste el mismo día.
        (CASO_AVISO_QUE_ESPERA_Y_SU_FILA_ENTRA,
         {"aviso_1": "parecido", "%_1": 1, "más_1": False, "día_del_ajuste": FIN_DE_MES}),
        (CASO_TRES_INGRESOS_Y_DOS_AVISOS, {**tres, "día_del_ajuste": FIN_DE_MES}),
        (CASO_TRES_INGRESOS_Y_DOS_AVISOS, {**tres, "día_del_ajuste": 19}),
        (CASO_AVISO_DE_FILA_RESERVADA_Y_OTRA_QUE_ESPERA,
         {"día_del_ajuste": FIN_DE_MES, "aviso_0": "parecido", "%_0": 2, "más_0": False,
          "aviso_1": "exacto", "aviso_2": "exacto"}),
    ]
    for escenario, elecciones in reversed(casos):
        prueba = example(escenario=escenario, monto_ajuste=-1, data=_Elecciones(**elecciones))(prueba)
    return prueba


# --- 1. Importar dos veces = importar una vez ----------------------------------------------------

@AJUSTES
@given(_escenario(), _monto_ajuste, st.data())
def test_importar_dos_veces_es_igual_que_una(plantilla, escenario, monto_ajuste, data):
    dia_ajuste = _dia_ajuste(data, escenario)
    with Base(plantilla) as conn:
        _preparar_con_ajuste(conn, escenario, dia_ajuste, monto_ajuste)
        filas = _a_excel(escenario["filas"])
        importacion.importar(conn, filas)
        una_vez, saldo_una = _foto(conn), componer_saldo(conn).saldo_actual()
        segunda = importacion.importar(conn, filas).conteos
        assert _foto(conn) == una_vez and componer_saldo(conn).saldo_actual() == saldo_una
        assert segunda.agregados == segunda.confirmados == segunda.corregidos == 0
        assert segunda.preguntas == segunda.no_en_banco == 0


@AJUSTES
@_ejemplos_44
@given(_escenario(), _monto_ajuste, st.data())
def test_con_avisos_tardios_y_respuestas_reimportar_no_cambia_nada(plantilla, escenario, monto_ajuste, data):
    dia_ajuste = _dia_ajuste(data, escenario)
    with Base(plantilla) as conn:
        _preparar_con_ajuste(conn, escenario, dia_ajuste, monto_ajuste)
        filas, avisos = _flujo(conn, escenario, data)
        # Otra importación solo puede marcar lo que el dueño descartó; después, nada.
        importacion.importar(conn, filas)
        asentado, saldo_asentado = _foto(conn), componer_saldo(conn).saldo_actual()
        tercera = importacion.importar(conn, filas).conteos
        _recibir(conn, avisos)
        assert _foto(conn) == asentado and componer_saldo(conn).saldo_actual() == saldo_asentado
        assert tercera.agregados == tercera.confirmados == tercera.corregidos == tercera.preguntas == 0


# --- 2. El saldo cuadrado sigue igual ----------------------------------------------------------------

@AJUSTES
@_ejemplos_44
@given(_escenario(), _monto_ajuste, st.data())
def test_un_saldo_cuadrado_antes_de_importar_sigue_igual(plantilla, escenario, monto_ajuste, data):
    """Ajuste posterior a todas las filas: con avisos tardíos y cualquier respuesta, sigue cuadrado."""
    with Base(plantilla) as conn:
        _preparar_con_ajuste(conn, escenario, FIN_DE_MES, monto_ajuste)
        cuadrado = componer_saldo(conn).saldo_actual()
        importacion.importar(conn, _a_excel(escenario["filas"]))
        assert componer_saldo(conn).saldo_actual() == cuadrado  # lo dudoso espera, lo anterior reduce el ajuste
        _flujo(conn, escenario, data)
        assert componer_saldo(conn).saldo_actual() == cuadrado


@AJUSTES
@_ejemplos_44
@example(escenario=CASO_AVISO_RESERVADO_EN_DOS_FILAS, monto_ajuste=-1,  # ajuste del mismo día
         data=_Elecciones(**{"aviso_1": "exacto", "día_del_ajuste": 1}))
@given(_escenario(), _monto_ajuste, st.data())
def test_con_el_ajuste_dentro_del_reporte_nada_se_cuenta_dos_veces(plantilla, escenario, monto_ajuste, data):
    """Ajuste el día de alguna fila (preguntas del mismo día, respuestas al azar): las reglas de oro."""
    dia_ajuste = _dia_ajuste(data, escenario)
    escenario = _hasta_el_ajuste(escenario, dia_ajuste)
    with Base(plantilla) as conn:
        _preparar_con_ajuste(conn, escenario, dia_ajuste, monto_ajuste)
        cuadrado = componer_saldo(conn).saldo_actual()
        importacion.importar(conn, _a_excel(escenario["filas"]))
        assert componer_saldo(conn).saldo_actual() == cuadrado
        _flujo(conn, escenario, data)


# --- 3. Nada se borra solo ---------------------------------------------------------------------------

@AJUSTES
@given(_escenario())
def test_ningun_movimiento_se_borra_ni_cambia_lo_del_correo(plantilla, escenario):
    with Base(plantilla) as conn:
        _preparar(conn, escenario)
        columnas = "id, fecha_hora, tipo, descripcion, origen, gmail_id, categoria_id"
        antes = {tuple(f) for f in sql(conn, f"SELECT {columnas} FROM movimientos")}
        importacion.importar(conn, _a_excel(escenario["filas"]))
        despues = {tuple(f) for f in sql(conn, f"SELECT {columnas} FROM movimientos")}
        assert antes <= despues
        # Lo nuevo es todo del banco, sin aviso.
        nuevos = despues - antes
        assert all(f[4] == "extracto" for f in nuevos)


# --- 4. Nunca una Referencia completa en la base -----------------------------------------------------

@AJUSTES
@given(_escenario())
def test_en_la_base_nunca_queda_una_referencia_completa(plantilla, escenario):
    with Base(plantilla) as conn:
        _preparar(conn, escenario)
        importacion.importar(conn, _a_excel(escenario["filas"]))
        textos = [
            valor
            for (tabla,) in sql(conn, "SELECT name FROM sqlite_master WHERE type = 'table'")
            for fila in sql(conn, f'SELECT * FROM "{tabla}"')
            for valor in fila
            if isinstance(valor, str)
        ]
        for *_, referencia in escenario["filas"]:
            if referencia and referencia.startswith("7"):
                assert not any(referencia in texto for texto in textos)
        for (referencia,) in sql(conn, "SELECT referencia FROM movimientos WHERE referencia IS NOT NULL "
                                       "UNION ALL SELECT referencia FROM preguntas_conciliacion "
                                       "WHERE referencia IS NOT NULL"):
            assert len(referencia) == 5 and referencia[0] == "*" and referencia[1:].isdigit()


# --- 5. Cada fila en un solo lugar (motor puro) ---------------------------------------------------------

_movimiento_app = st.builds(
    lambda i, dia, tipo, monto, descripcion, origen: c.MovimientoApp(
        i, date(2026, 8, dia), tipo, monto, descripcion, origen,
        estado=c.ESTADO_PROVISIONAL if origen == c.ORIGEN_MANUAL else None),
    st.just(0), _dia, st.sampled_from(["compra", "transferencia", "ingreso"]), st.sampled_from(MONTOS),
    st.sampled_from(DESCRIPCIONES_CORREO), st.sampled_from([c.ORIGEN_GMAIL, c.ORIGEN_MANUAL]),
)


@settings(max_examples=200, deadline=None)
@given(st.lists(_movimiento_app, max_size=10), st.lists(_fila, max_size=15),
       st.one_of(st.none(), _dia))
def test_cada_fila_termina_en_un_solo_lugar(movimientos, filas, dia_ajuste):
    movimientos = [
        c.MovimientoApp(i + 1, m.fecha, m.tipo if m.origen == c.ORIGEN_GMAIL else "ingreso",
                        m.monto_centavos, m.descripcion, m.origen, estado=m.estado)
        for i, m in enumerate(movimientos)
    ]
    filas_banco = [c.FilaBanco(m.fecha, m.monto_centavos, m.descripcion, m.referencia) for m in _a_excel(filas)]
    ajuste = None if dia_ajuste is None else c.AjusteApp(999, date(2026, 8, dia_ajuste), -1000)
    plan = c.conciliar(filas_banco, movimientos, date(2026, 8, 1), ajuste)
    total = (plan.anteriores + len(plan.ya_estaban) + len(plan.ya_preguntadas) + len(plan.confirmar)
             + len(plan.corregir) + len(plan.agregar) + len(plan.preguntas))
    assert total == len(filas_banco)
    emparejados = [p.movimiento_id for p in plan.confirmar + plan.corregir]
    assert len(emparejados) == len(set(emparejados))
    assert not set(emparejados) & set(plan.marcar)
    for pregunta in plan.preguntas:
        assert not set(pregunta.candidatos) & set(emparejados)
    for p in plan.confirmar:
        m = next(x for x in movimientos if x.id == p.movimiento_id)
        assert m.monto_centavos == abs(p.fila.monto_centavos)
        assert abs((m.fecha - p.fila.fecha).days) <= 1
    # Solo lo del correo se marca; los provisionales nunca (D39).
    assert all(next(x for x in movimientos if x.id == i).origen == c.ORIGEN_GMAIL for i in plan.marcar)


# Oráculo exhaustivo: enumera asignaciones posibles en escenarios pequeños.
# No usa helpers del motor ni su algoritmo de caminos de aumento.
_dia_destino = st.tuples(st.integers(1, 4), st.sampled_from([None, "*0001", "*0002"]))


@settings(max_examples=200, deadline=None)
@given(st.lists(_dia_destino, max_size=5), st.lists(_dia_destino, max_size=5))
def test_exactos_confirman_el_maximo_posible_sin_duplicar(correos, banco):
    def maximo(i, usados):
        if i == len(banco):
            return 0
        dia, destino = banco[i]
        posibles = [j for j, (d, ref) in enumerate(correos)
                    if j not in usados and abs(d - dia) <= 1
                    and (destino is None or ref is None or destino == ref)]
        return max([maximo(i + 1, usados)] + [1 + maximo(i + 1, usados | {j}) for j in posibles])

    movs = [c.MovimientoApp(i + 1, date(2026, 8, dia), "transferencia", 620000, ref or "PERSONA EJEMPLO",
                           "gmail") for i, (dia, ref) in enumerate(correos)]
    filas = [c.FilaBanco(date(2026, 8, dia), -620000, "TRANSFERENCIA EJEMPLO", ref) for dia, ref in banco]
    plan = c.conciliar(filas, movs, date(2026, 8, 1))
    esperado = maximo(0, set())
    assert len(plan.confirmar) == esperado
    assert len(plan.agregar) == len(banco) - esperado


@settings(max_examples=100, deadline=None)
@given(st.lists(st.integers(0, 9), max_size=6), st.lists(st.integers(0, 9), max_size=6))
def test_reportes_solapados_conservan_repeticiones_por_destino(plantilla, primeros, siguientes):
    with Base(plantilla) as conn:
        def filas(destinos):
            return [MovimientoExcel(date(2026, 8, 10), -620000, "TRANSFERENCIA EJEMPLO", f"*000{d}")
                    for d in destinos]
        importacion.importar(conn, filas(primeros))
        importacion.importar(conn, filas(siguientes))
        cantidades = Counter(primeros) | Counter(siguientes)
        guardados = Counter(ref for (ref,) in sql(conn, "SELECT referencia FROM movimientos"))
        assert guardados == Counter({f"*000{d}": n for d, n in cantidades.items()})
        assert componer_saldo(conn).saldo_actual() == 500_000_000 - 620000 * sum(cantidades.values())
        antes = _foto(conn)
        importacion.importar(conn, filas(siguientes))
        assert _foto(conn) == antes
