"""Motor de conciliación (ítem 29, D31, D37 a D40, D44 y D45): lógica pura.

Recibe las filas del reporte del banco y los movimientos que ya tiene la app,
y devuelve un ``Plan``: qué ya estaba, qué se confirma, qué se corrige, qué
falta, qué se pregunta y qué del correo no está en el banco. No toca la base
de datos ni la red: guardar el plan es de ``finanzas.importacion`` (en una
sola transacción) y la conciliación en seco solo lo cuenta.

Montos siempre en centavos enteros (D8), nunca ``float``. En ``FilaBanco`` el
monto lleva signo (negativo sale de la cuenta); en ``MovimientoApp`` es
positivo y el signo lo da el tipo (``ingreso`` suma; ``compra`` y
``transferencia`` restan), como en la tabla ``movimientos``.

Reglas, en el orden en que se aplican:

1. **Fecha de inicio (D40).** Las filas anteriores no se concilian: solo se
   cuentan (``Plan.anteriores``). Los movimientos anteriores tampoco se usan
   (no cuentan en el saldo y corregirlos movería el ajuste en vano).
2. **Lo que ya vino del banco.** Una fila igual (mismo día del banco, mismo
   monto con signo y sin destinos contradictorios) a un movimiento ya respaldado por el banco
   (``fecha_banco``) o a una pregunta pendiente es la misma fila importada
   antes: no cambia nada. Se cuentan las repeticiones (tres filas iguales
   necesitan tres respaldos). Es lo que hace que importar dos veces no cambie
   nada.
3. **Monto exacto, día ±1 (D38).** Contra lo del correo sin conciliar y los
   ingresos provisionales (D39). Por niveles: mismo día con el mismo destino,
   ±1 día con el mismo destino, mismo día y ±1 día sin destino que lo
   contradiga. Entre todos los niveles se busca el emparejamiento **máximo**
   (caminos de aumento), no el primero que aparezca: así las repeticiones y
   los destinos distintos quedan cada uno con el suyo. El destino solo
   cuenta cuando las dos partes lo traen (``*1234``); si los dos lo traen y
   no coinciden, no son el mismo.
4. **Montos parecidos (D38, D45).** Mismo día, mismo sentido, diferencia de
   hasta ``TOLERANCIA_PORCENTAJE`` % del monto del banco y sin destinos que
   se contradigan. Se empareja solo si la fila tiene un único candidato, ese
   candidato una única fila, y coincide el destino o comparten una palabra
   propia (``palabras_propias``); queda el monto del banco (``corregir``).
   Si no, se pregunta "¿es el mismo?" y la fila no entra hasta que el dueño
   responda.
5. **Lo que faltaba** entra como ``sin aviso`` (``agregar``).
6. **Último ajuste (D45).** Lo que cambia el saldo (una fila que falta o la
   corrección de un monto parecido) con fecha anterior al día del último
   ajuste reduce ese ajuste en el mismo efecto (``reduccion_ajuste``): un
   saldo ya cuadrado sigue igual. Si es del mismo día, se pregunta "¿ya
   estaba en el saldo que ajustaste?" (el banco no da la hora) y no se
   aplica hasta la respuesta. Lo posterior mueve el saldo.
7. **No está en el banco (D38, D45).** Lo del correo, dentro de las fechas
   del reporte, que no se emparejó ni está en una pregunta queda marcado.
   El día más antiguo de cualquier reporte nunca marca, tenga las filas que
   tenga: el banco corta las descargas en un tope que no se conoce y ese día
   puede venir incompleto (D51). Nada se borra. Los ingresos
   provisionales que no aparecen quedan como están (D39).

Los cobros que el banco acumula por día (Transmilenio) llegan como una sola
fila por día y se tratan así, sin partirla (D45).
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date

# --- Vocabulario (los mismos textos que guarda la base, migración 0008) -------

TIPO_COMPRA = "compra"
TIPO_TRANSFERENCIA = "transferencia"
TIPO_INGRESO = "ingreso"
TIPO_AJUSTE = "ajuste"

ORIGEN_GMAIL = "gmail"
ORIGEN_MANUAL = "manual"
ORIGEN_EXTRACTO = "extracto"

ESTADO_CONFIRMADO = "confirmado"
ESTADO_PROVISIONAL = "provisional"
ESTADO_SIN_AVISO = "sin_aviso"
# Lo del correo aún sin conciliar no tiene estado (NULL, D45).

PREGUNTA_ES_EL_MISMO = "es_el_mismo"
PREGUNTA_YA_ESTABA = "ya_estaba_en_ajuste"

TOLERANCIA_PORCENTAJE = 5

# Palabras que no identifican a nadie: prefijos del banco, tipos de
# movimiento, artículos y formas societarias. Se comparan sin tildes y en
# mayúsculas. Una palabra propia tiene al menos 3 letras y no está aquí.
PALABRAS_GENERICAS = frozenset(
    """
    COMPRA COMPRAS COMPRASTE PAGO PAGOS PAGASTE PAGAR TRANSFERENCIA TRANSFERENCIAS
    TRANSFERISTE TRANSF TRANSFER TRANS ABONO ABONOS COBRO COBROS RETIRO RETIROS
    RETIRASTE CAJERO CAJEROS RECIBISTE CONSIGNACION DEPOSITO CUENTA CUENTAS CTA
    SUC SUCURSAL VIRTUAL AHORROS AHORRO CORRIENTE TARJETA TARJ DEB DEBITO CREDITO
    INTERESES INTERES CUOTA MANEJO IMPTO IMPUESTO GOBIERNO NEQUI DAVIPLATA
    BANCOLOMBIA BANCO LLAVE BREB PSE CODIGO DESDE HACIA PARA POR CON DEL LAS LOS
    UNA UNO SAS LTDA CIA COLOMBIA NACIONAL VALOR TOTAL APP WEB
    """.split()
)


# --- Datos de entrada y salida --------------------------------------------------

@dataclass(frozen=True)
class FilaBanco:
    """Una fila del reporte del banco (lo que devuelve el lector, ítem 28).

    ``referencia``: ``"*1234"`` o ``None`` (D37). Nunca el número completo.
    """

    fecha: date
    monto_centavos: int  # con signo, distinto de 0
    descripcion: str
    referencia: str | None = None


@dataclass(frozen=True)
class MovimientoApp:
    """Un movimiento que ya está en la app (no ajuste).

    ``reservado``: es candidato de una pregunta pendiente; no se empareja ni
    se marca hasta que el dueño responda.
    """

    id: int
    fecha: date
    tipo: str
    monto_centavos: int  # positivo
    descripcion: str
    origen: str
    estado: str | None = None
    referencia: str | None = None
    fecha_banco: date | None = None
    no_en_banco: bool = False
    reservado: bool = False


@dataclass(frozen=True)
class ReservaDescarte:
    """Una ocurrencia excluida, ligada a su fila; nunca un veto por monto.

    ``banco`` es el respaldo conocido, sin descripción como identidad.
    Guardar una coincidencia puede confirmar la fila, pero no reactivarla.
    """

    movimiento: MovimientoApp
    banco: FilaBanco | None = None
    gmail_id: str | None = None


@dataclass(frozen=True)
class EleccionBanco:
    """Elección explícita por identidad normalizada y ordinal de repetición."""

    fecha: date
    monto_centavos: int
    referencia: str | None
    ocurrencia_banco: int
    movimiento_id: int


@dataclass(frozen=True)
class PreguntaPendiente:
    """Una fila del banco que espera respuesta del dueño (ya se importó una vez)."""

    id: int
    fecha: date
    monto_centavos: int  # con signo
    referencia: str | None = None
    ocurrencia_banco: int | None = None


@dataclass(frozen=True)
class AjusteApp:
    """El último ajuste: el de mayor fecha y hora (D45)."""

    id: int
    fecha: date
    monto_centavos: int


@dataclass(frozen=True)
class Emparejado:
    fila: FilaBanco
    movimiento_id: int


@dataclass(frozen=True)
class Pregunta:
    """Algo que decide el dueño. ``candidatos``: ids de movimientos (puede ser vacío
    en "¿ya estaba en el saldo que ajustaste?" de una fila que falta)."""

    tipo: str
    fila: FilaBanco
    candidatos: tuple[int, ...] = ()
    ocurrencia_banco: int | None = None


@dataclass
class Plan:
    """La decisión del motor. Nada se aplica hasta que ``importacion`` lo guarda."""

    filas: int = 0
    anteriores: int = 0
    ya_estaban: list[Emparejado] = field(default_factory=list)
    descartadas: list[Emparejado] = field(default_factory=list)
    ya_preguntadas: list[tuple[FilaBanco, int]] = field(default_factory=list)
    confirmar: list[Emparejado] = field(default_factory=list)
    corregir: list[Emparejado] = field(default_factory=list)
    agregar: list[FilaBanco] = field(default_factory=list)
    preguntas: list[Pregunta] = field(default_factory=list)
    marcar: list[int] = field(default_factory=list)
    ajuste_id: int | None = None
    reduccion_ajuste: int = 0  # efecto con signo que se resta del ajuste
    desde: date | None = None
    hasta: date | None = None

    @property
    def cambia_algo(self) -> bool:
        return bool(
            self.confirmar or self.corregir or self.agregar or self.preguntas
            or self.marcar or self.reduccion_ajuste
        )


# --- Ayudas -----------------------------------------------------------------------

def signo(tipo: str) -> int:
    """+1 si suma al saldo (ingreso), -1 si resta (compra, transferencia)."""
    if tipo == TIPO_INGRESO:
        return 1
    if tipo in (TIPO_COMPRA, TIPO_TRANSFERENCIA):
        return -1
    raise ValueError("tipo sin signo")


def monto_con_signo(movimiento: MovimientoApp) -> int:
    return signo(movimiento.tipo) * movimiento.monto_centavos


def tipo_de_fila(fila: FilaBanco) -> str:
    """Tipo con que entra una fila que no llegó por correo (D45).

    Positiva -> ingreso; negativa con destino -> transferencia; negativa sin
    destino -> compra.
    """
    if fila.monto_centavos > 0:
        return TIPO_INGRESO
    return TIPO_TRANSFERENCIA if fila.referencia else TIPO_COMPRA


_CUENTA_EN_DESCRIPCION = re.compile(r"\*?([0-9]{4,})")


def destino(movimiento: MovimientoApp) -> str | None:
    """``*1234`` del movimiento, si se sabe.

    La referencia que guardó el banco; o, en una transferencia del correo a
    una cuenta o celular, los últimos 4 dígitos de su descripción
    (``*3000000001`` -> ``*0001``). Un nombre (Bre-B) o "Pago QR" no tiene.
    """
    if movimiento.referencia:
        return movimiento.referencia
    if movimiento.tipo == TIPO_TRANSFERENCIA:
        encontrado = _CUENTA_EN_DESCRIPCION.fullmatch(movimiento.descripcion.strip())
        if encontrado:
            return "*" + encontrado.group(1)[-4:]
    return None


def palabras_propias(texto: str) -> frozenset[str]:
    """Palabras que pueden identificar a un comercio o persona.

    Sin tildes, en mayúsculas, partidas por lo que no es letra; al menos 3
    letras y fuera de ``PALABRAS_GENERICAS``. Los números no cuentan.
    """
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", texto.upper()) if not unicodedata.combining(c)
    )
    return frozenset(
        p for p in re.split(r"[^A-Z]+", sin_tildes) if len(p) >= 3 and p not in PALABRAS_GENERICAS
    )


def _mismo_sentido(fila: FilaBanco, movimiento: MovimientoApp) -> bool:
    return (fila.monto_centavos > 0) == (movimiento.tipo == TIPO_INGRESO)


def _destinos(fila: FilaBanco, movimiento: MovimientoApp) -> str:
    """``"igual"``, ``"distinto"`` o ``"desconocido"`` (si alguno no lo trae)."""
    del_movimiento = destino(movimiento)
    if fila.referencia is None or del_movimiento is None:
        return "desconocido"
    return "igual" if fila.referencia == del_movimiento else "distinto"


def es_parecido(monto_banco: int, monto_app: int) -> bool:
    """Montos distintos con diferencia de hasta el 5 % del monto del banco (D45)."""
    a, b = abs(monto_banco), abs(monto_app)
    return a != b and abs(a - b) * 100 <= TOLERANCIA_PORCENTAJE * a


def _emparejamiento_maximo(
    izquierda: Sequence[int], vecinos: dict[int, list[int]], anteriores: dict[int, int] | None = None,
) -> dict[int, int]:
    """Emparejamiento máximo (algoritmo de Kuhn): izquierda -> derecha.

    Determinista: recorre ``izquierda`` y cada lista de vecinos en el orden
    dado, que ya pone primero lo preferido.
    """
    # Conserva los pares preferidos; solo los mueve si permite emparejar otra fila.
    anteriores = anteriores or {}
    derecha_de: dict[int, int] = {j: i for i, j in anteriores.items()}

    def aumentar(i: int, vistos: set[int]) -> bool:
        for j in vecinos.get(i, ()):
            if j in vistos:
                continue
            vistos.add(j)
            if j not in derecha_de or aumentar(derecha_de[j], vistos):
                derecha_de[j] = i
                return True
        return False

    for i in izquierda:
        if i not in anteriores:
            aumentar(i, set())
    return {i: j for j, i in derecha_de.items()}


def _orden_fila(fila: FilaBanco) -> tuple:
    return (fila.fecha, fila.monto_centavos, fila.referencia or "", fila.descripcion)


# --- El motor ------------------------------------------------------------------------

def _conciliar_activos(
    filas: Iterable[FilaBanco],
    movimientos: Iterable[MovimientoApp],
    fecha_inicio: date,
    ultimo_ajuste: AjusteApp | None = None,
    preguntas_pendientes: Iterable[PreguntaPendiente] = (),
    reporte: Sequence[FilaBanco] | None = None,
    reservas_banco: Sequence[MovimientoApp] = (),
) -> Plan:
    """Decide qué hacer con cada fila del reporte. Función pura.

    ``movimientos``: los de la app que no son ajustes (bastan los de las
    fechas del reporte ±1 día y los que ya tienen ``fecha_banco`` en ellas).
    Cada fila queda en exactamente uno de: ``anteriores``, ``ya_estaban``,
    ``ya_preguntadas``, ``confirmar``, ``corregir``, ``agregar`` o
    ``preguntas``. Cada movimiento se usa como mucho una vez.
    """
    todas = list(filas)
    plan = Plan(filas=len(todas))
    if todas:
        plan.desde = min(f.fecha for f in todas)
        plan.hasta = max(f.fecha for f in todas)
    vigentes = sorted((f for f in todas if f.fecha >= fecha_inicio), key=_orden_fila)
    plan.anteriores = len(todas) - len(vigentes)

    movs = [m for m in movimientos if m.tipo != TIPO_AJUSTE and m.fecha >= fecha_inicio]

    # 2. Reportes solapados: día y monto exactos, sin contradecir el destino.
    respaldos: dict[tuple[date, int], list] = defaultdict(list)
    for m in sorted(movs, key=lambda m: m.id):
        if m.fecha_banco is not None and not m.reservado:
            respaldos[(m.fecha_banco, monto_con_signo(m))].append(("movimiento", m.id, destino(m)))
    for p in sorted(preguntas_pendientes, key=lambda p: p.id):
        respaldos[(p.fecha, p.monto_centavos)].append(("pregunta", p.id, p.referencia))
    respaldos_por_indice = [r for grupo in respaldos.values() for r in grupo]
    indices_respaldo = {(clase, ident): i for i, (clase, ident, _) in enumerate(respaldos_por_indice)}
    vecinos_respaldo: dict[int, list[int]] = {}
    for i, fila in enumerate(vigentes):
        vecinos_respaldo[i] = []
        for respaldo in respaldos.get((fila.fecha, fila.monto_centavos), []):
            if fila.referencia and respaldo[2] and fila.referencia != respaldo[2]:
                continue
            vecinos_respaldo[i].append(indices_respaldo[respaldo[:2]])
        vecinos_respaldo[i].sort(key=lambda j: respaldos_por_indice[j][2] != fila.referencia)
    anteriores = _emparejamiento_maximo(list(range(len(vigentes))), vecinos_respaldo)
    pendientes: list[FilaBanco] = []
    for i, fila in enumerate(vigentes):
        if i in anteriores:
            clase, ident, _ = respaldos_por_indice[anteriores[i]]
            if clase == "movimiento":
                plan.ya_estaban.append(Emparejado(fila, ident))
            else:
                plan.ya_preguntadas.append((fila, ident))
        else:
            pendientes.append(fila)

    # Lo que se puede emparejar ahora: correo sin conciliar e ingresos provisionales.
    libres = [
        m for m in movs
        if m.fecha_banco is None and not m.reservado and (
            (m.origen == ORIGEN_GMAIL and m.estado is None)
            or (m.origen == ORIGEN_MANUAL and m.tipo == TIPO_INGRESO
                and m.estado in (None, ESTADO_PROVISIONAL))
        )
    ]
    libres.sort(key=lambda m: (m.origen != ORIGEN_GMAIL, m.fecha, m.id))
    usados: set[int] = set()

    # 3. Monto exacto: conserva las preferencias entre niveles, pero permite
    # caminos de aumento con pares anteriores para evitar duplicar por un cruce.
    def preferencia(fila: FilaBanco, movimiento: MovimientoApp) -> int:
        return (0 if _destinos(fila, movimiento) == "igual" else 2) + (fila.fecha != movimiento.fecha)

    por_id = {m.id: m for m in libres}
    indices = list(range(len(pendientes)))
    todos_vecinos = {
        i: [m.id for m in libres
            if _mismo_sentido(fila, m) and m.monto_centavos == abs(fila.monto_centavos)
            and abs((m.fecha - fila.fecha).days) <= 1 and _destinos(fila, m) != "distinto"]
        for i, fila in enumerate(pendientes)
    }
    for i in indices:
        todos_vecinos[i].sort(key=lambda mid, f=pendientes[i]: preferencia(f, por_id[mid]))
    pares: dict[int, int] = {}
    for nivel in range(4):
        # Las aristas crecen entre niveles: las asignaciones previas siguen
        # siendo válidas y solo cambian para confirmar una fila más.
        vecinos = {i: [mid for mid in todos_vecinos[i] if preferencia(pendientes[i], por_id[mid]) <= nivel]
                   for i in indices}
        pares = _emparejamiento_maximo(indices, vecinos, pares)
    for i, mid in pares.items():
        plan.confirmar.append(Emparejado(pendientes[i], mid))
        usados.add(mid)
    pendientes = [f for i, f in enumerate(pendientes) if i not in pares]

    # 4. Montos parecidos, solo el mismo día.
    candidatos: dict[int, list[MovimientoApp]] = {}
    filas_de: dict[int, list[int]] = defaultdict(list)
    for i, fila in enumerate(pendientes):
        candidatos[i] = [
            m for m in libres
            if m.id not in usados
            and _mismo_sentido(fila, m)
            and m.fecha == fila.fecha
            and es_parecido(fila.monto_centavos, m.monto_centavos)
            and _destinos(fila, m) != "distinto"
        ]
        for m in candidatos[i]:
            filas_de[m.id].append(i)

    faltan: list[FilaBanco] = []
    for i, fila in enumerate(pendientes):
        cands = candidatos[i]
        if not cands:
            faltan.append(fila)
            continue
        unico = cands[0] if len(cands) == 1 and len(filas_de[cands[0].id]) == 1 else None
        if unico is not None and (
            _destinos(fila, unico) == "igual"
            or palabras_propias(fila.descripcion) & palabras_propias(unico.descripcion)
        ):
            usados.add(unico.id)
            efecto = signo(unico.tipo) * (abs(fila.monto_centavos) - unico.monto_centavos)
            if _efecto_en_ajuste(plan, ultimo_ajuste, fila, efecto, (unico.id,)):
                plan.corregir.append(Emparejado(fila, unico.id))
        else:
            plan.preguntas.append(
                Pregunta(PREGUNTA_ES_EL_MISMO, fila, tuple(sorted(m.id for m in cands)))
            )
            usados.update(m.id for m in cands)

    # 5. Lo que faltaba.
    respaldos_reservados = [m for m in movs if m.reservado] + list(reservas_banco)
    for fila in faltan:
        if any(m.reservado and _compatible_reserva(fila, m) for m in respaldos_reservados):
            # El respaldo posible espera en otra pregunta. No reutilizarlo
            # ni interpretar su reserva como prueba de un movimiento nuevo.
            # El dueño puede confirmar que esta ocurrencia adicional es nueva.
            plan.preguntas.append(Pregunta(PREGUNTA_ES_EL_MISMO, fila))
            continue
        if _efecto_en_ajuste(plan, ultimo_ajuste, fila, fila.monto_centavos, ()):
            plan.agregar.append(fila)

    # 7. Lo del correo que el banco no trae.
    cobertura = [f for f in (todas if reporte is None else reporte) if f.fecha >= fecha_inicio]
    if cobertura:
        desde = min(f.fecha for f in cobertura)
        hasta = max(f.fecha for f in cobertura)
        # Su día más antiguo puede venir cortado, sin importar cuántas filas
        # traiga (D51): nunca marca "no está en el banco".
        dia_cortado = min(f.fecha for f in (todas if reporte is None else reporte))
        if desde <= dia_cortado:
            desde = date.fromordinal(dia_cortado.toordinal() + 1)
        for m in sorted(libres, key=lambda m: m.id):
            if (
                m.id not in usados
                and m.origen == ORIGEN_GMAIL
                and desde <= m.fecha <= hasta
                and not m.no_en_banco
            ):
                plan.marcar.append(m.id)
    return plan


def _identidad(m: MovimientoApp) -> tuple:
    return (m.fecha_banco or m.fecha, monto_con_signo(m), destino(m))


def _exacto(f: FilaBanco, m: MovimientoApp) -> bool:
    return (
        _mismo_sentido(f, m) and abs(f.monto_centavos) == m.monto_centavos
        and _destinos(f, m) != "distinto"
        and (f.fecha == m.fecha_banco if m.fecha_banco is not None
             else abs((f.fecha - m.fecha).days) <= 1)
    )


def _compatible_reserva(f: FilaBanco, m: MovimientoApp) -> bool:
    """Posible coincidencia que espera decisión, con o sin respaldo bancario."""
    return _exacto(f, m) or (
        _mismo_sentido(f, m) and (m.fecha_banco or m.fecha) == f.fecha
        and es_parecido(f.monto_centavos, m.monto_centavos) and _destinos(f, m) != "distinto"
    )


def candidatos_para_pregunta(fila: FilaBanco, movimientos: Iterable[MovimientoApp]) -> tuple[int, ...]:
    """Repropone IDs libres después de una decisión, sin confirmar ni sumar.

    Exactos primero; si no hay, parecidos del mismo día. Una propuesta no
    transforma el descarte en movimiento activo ni decide por el dueño.
    """
    libres = [m for m in movimientos if not m.reservado and (m.fecha_banco is not None or _libre(m))]
    exactos = [m.id for m in libres if _exacto(fila, m)]
    return tuple(sorted(exactos or [m.id for m in libres if _libre(m) and _compatible_reserva(fila, m)]))


def _libre(m: MovimientoApp) -> bool:
    return m.fecha_banco is None and not m.reservado and (
        m.origen == ORIGEN_GMAIL and m.estado is None
        or m.origen == ORIGEN_MANUAL and m.tipo == TIPO_INGRESO
        and m.estado in (None, ESTADO_PROVISIONAL)
    )


def _componentes(vecinos: dict[int, list[int]]) -> Iterable[tuple[list[int], set[int]]]:
    """Componentes fila/ocurrencia: la multiplicidad se decide en conjunto."""
    por_movimiento: dict[int, list[int]] = defaultdict(list)
    for i, ids in vecinos.items():
        for mid in ids:
            por_movimiento[mid].append(i)
    vistos: set[int] = set()
    for primero in vecinos:
        if primero in vistos or not vecinos[primero]:
            continue
        filas, ids, pendientes = [], set(), [primero]
        while pendientes:
            i = pendientes.pop()
            if i in vistos:
                continue
            vistos.add(i)
            filas.append(i)
            for mid in vecinos[i]:
                if mid not in ids:
                    ids.add(mid)
                    pendientes.extend(por_movimiento[mid])
        yield sorted(filas), ids


def _clave_fila(fila: FilaBanco) -> tuple:
    return (fila.fecha, fila.monto_centavos, fila.referencia)


def _numerar(filas: Sequence[FilaBanco]) -> dict[int, int]:
    """Ordinal dentro de una identidad; nunca descripción ni índice global."""
    cantidades: Counter = Counter()
    resultado = {}
    for i, f in enumerate(filas):
        clave = _clave_fila(f)
        cantidades[clave] += 1
        resultado[i] = cantidades[clave]
    return resultado


def _numerar_preguntas(plan: Plan, filas: Sequence[FilaBanco], ordinales: Sequence[int]) -> None:
    # Los respaldos se consumen antes que filas nuevas. Entre repeticiones
    # indistinguibles, esas filas nuevas ocupan los ordinales que siguen.
    por_clave: dict[tuple, list[int]] = defaultdict(list)
    for f, ordinal in zip(filas, ordinales):
        por_clave[_clave_fila(f)].append(ordinal)
    cuentas = Counter(_clave_fila(p.fila) for p in plan.preguntas)
    siguientes = {clave: iter(valores[-cuentas[clave]:]) for clave, valores in por_clave.items() if cuentas[clave]}
    plan.preguntas = [replace(p, ocurrencia_banco=next(siguientes[_clave_fila(p.fila)])) for p in plan.preguntas]


def conciliar(
    filas: Iterable[FilaBanco], movimientos: Iterable[MovimientoApp], fecha_inicio: date,
    ultimo_ajuste: AjusteApp | None = None,
    preguntas_pendientes: Iterable[PreguntaPendiente] = (),
    descartes: Iterable[ReservaDescarte] = (),
    elecciones: Iterable[EleccionBanco] = (),
) -> Plan:
    """Consume reservas por ocurrencia; las dudas nunca reactivan ni agregan.

    Repeticiones con idéntica identidad son intercambiables cuando la cobertura
    alcanza todas las ocurrencias conocidas. Con cobertura parcial y una mezcla
    activo/descarte, o candidatos de identidades diferentes, decide el dueño.
    """
    todas, activos, preguntas, reservas = list(filas), list(movimientos), list(preguntas_pendientes), list(descartes)
    decisiones = list(elecciones)
    filas_vigentes = sorted((f for f in todas if f.fecha >= fecha_inicio), key=_orden_fila)
    ordinales = _numerar(filas_vigentes)
    if not reservas and not decisiones:
        plan = _conciliar_activos(todas, activos, fecha_inicio, ultimo_ajuste, preguntas)
        _numerar_preguntas(plan, filas_vigentes, list(ordinales.values()))
        return plan
    sombras = {}
    sombras_reservadas = []
    for r in reservas:
        m = r.movimiento
        if m.fecha < fecha_inicio:
            continue
        if r.banco is not None:
            m = replace(m, fecha_banco=r.banco.fecha, monto_centavos=abs(r.banco.monto_centavos),
                        referencia=r.banco.referencia)
        if m.reservado:
            sombras_reservadas.append(m)
            continue
        sombras[m.id] = m
    extra = Plan()
    # Las preguntas ya abiertas tienen su propia reserva de fila y prioridad.
    vecinos_p = {i: [p.id for p in preguntas if p.fecha == f.fecha and p.monto_centavos == f.monto_centavos
                     and (p.ocurrencia_banco is None or p.ocurrencia_banco == ordinales[i])
                     and not (p.referencia and f.referencia and p.referencia != f.referencia)]
                 for i, f in enumerate(filas_vigentes)}
    pares_p = _emparejamiento_maximo(list(vecinos_p), vecinos_p)
    extra.ya_preguntadas = [(filas_vigentes[i], pid) for i, pid in pares_p.items()]
    pendientes = {i: f for i, f in enumerate(filas_vigentes) if i not in pares_p}
    disponibles = {m.id: m for m in activos if m.fecha >= fecha_inicio and m.tipo != TIPO_AJUSTE
                   and not m.reservado and (m.fecha_banco is not None or _libre(m))}
    disponibles.update(sombras)
    usados: set[int] = set()
    reservados: set[int] = set()

    por_ocurrencia = {(_clave_fila(f), ordinales[i]): i for i, f in pendientes.items()}
    vigentes = [(d, por_ocurrencia[((d.fecha, d.monto_centavos, d.referencia), d.ocurrencia_banco)])
                for d in decisiones if ((d.fecha, d.monto_centavos, d.referencia), d.ocurrencia_banco) in por_ocurrencia]
    multiplicidad_ids = Counter(d.movimiento_id for d, _ in vigentes)
    obsoletas = []
    for d, i in vigentes:
        f, m = pendientes.pop(i), disponibles.get(d.movimiento_id)
        if (m is not None and not m.reservado and m.fecha_banco is not None
                and _exacto(f, m) and multiplicidad_ids[m.id] == 1):
            par = Emparejado(f, m.id)
            (extra.descartadas if m.id in sombras else extra.ya_estaban).append(par)
            usados.add(m.id)
        else:
            obsoletas.append((f, i))
    # Reservar todas las elecciones válidas antes de ofrecer un candidato
    # para cualquier elección obsoleta: el orden de lectura no decide dinero.
    for f, i in obsoletas:
        # La elección más reciente no se reemplaza por una vieja ni por
        # una inserción automática si cambió su respaldo o se contradice.
        candidatos = tuple(sorted(mid for mid, otro in disponibles.items()
            if mid not in usados and mid not in reservados and not otro.reservado and _exacto(f, otro)))
        extra.preguntas.append(Pregunta(PREGUNTA_ES_EL_MISMO, f, candidatos, ordinales[i]))
        reservados.update(candidatos)
    usados.update(reservados)

    vecinos = {}
    for i, f in pendientes.items():
        candidatos = sorted(mid for mid, m in disponibles.items() if mid not in usados and _exacto(f, m))
        # Una respuesta que ya vinculó esa fila tiene prioridad: no volver a
        # competir contra avisos sin respaldo al importar el mismo reporte.
        respaldados = [mid for mid in candidatos if disponibles[mid].fecha_banco is not None]
        vecinos[i] = respaldados or candidatos
    for indices, ids in _componentes(vecinos):
        if not ids.intersection(sombras):
            continue
        mezcla = bool(ids.intersection(sombras)) and bool(ids.difference(sombras))
        identidades = {_identidad(disponibles[mid]) for mid in ids}
        ambiguo = len(identidades) > 1 or (mezcla and len(indices) < len(ids))
        if ambiguo:
            for i in indices:
                extra.preguntas.append(Pregunta(PREGUNTA_ES_EL_MISMO, pendientes.pop(i), tuple(vecinos[i]), ordinales[i]))
            usados.update(ids)
            reservados.update(ids)
            continue
        pares = _emparejamiento_maximo(indices, vecinos)
        for i, mid in pares.items():
            f, m = pendientes.pop(i), disponibles[mid]
            par = Emparejado(f, mid)
            if mid in sombras:
                extra.descartadas.append(par)
            elif m.fecha_banco is not None:
                extra.ya_estaban.append(par)
            else:
                extra.confirmar.append(par)  # monto exacto: efecto cero
            usados.add(mid)

    # Un exacto activo tiene prioridad sobre cualquier sombra de monto parecido.
    vecinos_c = {}
    for i, f in pendientes.items():
        if any(mid not in usados and _exacto(f, m) for mid, m in disponibles.items() if mid not in sombras):
            continue
        vecinos_c[i] = sorted(mid for mid, m in disponibles.items() if mid not in usados and (
            mid in sombras or _libre(m)) and _mismo_sentido(f, m) and (m.fecha_banco or m.fecha) == f.fecha
            and es_parecido(f.monto_centavos, m.monto_centavos) and _destinos(f, m) != "distinto")
    for indices, ids in _componentes(vecinos_c):
        if not ids.intersection(sombras):
            continue
        unico = disponibles[next(iter(ids))] if len(ids) == len(indices) == 1 else None
        f = pendientes[indices[0]]
        seguro = unico is not None and (
            _destinos(f, unico) == "igual" or palabras_propias(f.descripcion) & palabras_propias(unico.descripcion))
        if seguro:
            extra.descartadas.append(Emparejado(pendientes.pop(indices[0]), unico.id))
        else:
            for i in indices:
                extra.preguntas.append(Pregunta(PREGUNTA_ES_EL_MISMO, pendientes.pop(i), tuple(vecinos_c[i]), ordinales[i]))
            reservados.update(ids)
        usados.update(ids)
    restantes = [replace(m, reservado=True) if m.id in reservados else m
                 for m in activos if m.id not in usados or m.id in reservados]
    # Estas sombras sólo protegen la decisión pendiente: nunca forman parte
    # de los movimientos activos, del saldo ni del emparejamiento automático.
    sombras_reservadas.extend(replace(sombras[mid], reservado=True) for mid in reservados if mid in sombras)
    resultado = _conciliar_activos(pendientes.values(), restantes, fecha_inicio, ultimo_ajuste, (),
                                 reporte=todas, reservas_banco=sombras_reservadas)
    # Una fila aún preguntada puede ser el aviso que quedó libre al contestar
    # otra ocurrencia. No afirmar su ausencia mientras falta esa decisión.
    por_id = {m.id: m for m in activos}
    resultado.marcar = [mid for mid in resultado.marcar if not any(
        _compatible_reserva(f, por_id[mid]) for f, _ in extra.ya_preguntadas)]
    _numerar_preguntas(resultado, list(pendientes.values()), [ordinales[i] for i in pendientes])
    resultado.filas, resultado.anteriores = len(todas), sum(f.fecha < fecha_inicio for f in todas)
    resultado.desde = min((f.fecha for f in todas), default=None)
    resultado.hasta = max((f.fecha for f in todas), default=None)
    for campo in ("ya_estaban", "ya_preguntadas", "confirmar", "descartadas", "preguntas"):
        getattr(resultado, campo).extend(getattr(extra, campo))
    return resultado


def _efecto_en_ajuste(
    plan: Plan,
    ajuste: AjusteApp | None,
    fila: FilaBanco,
    efecto: int,
    candidatos: tuple[int, ...],
) -> bool:
    """Aplica la regla del último ajuste a un cambio de saldo (D45).

    Devuelve ``True`` si el cambio sigue su camino (agregar o corregir) y
    ``False`` si se convirtió en la pregunta "¿ya estaba en el saldo que
    ajustaste?" (mismo día del ajuste).
    """
    if ajuste is None or efecto == 0 or fila.fecha > ajuste.fecha:
        return True
    if fila.fecha == ajuste.fecha:
        plan.preguntas.append(Pregunta(PREGUNTA_YA_ESTABA, fila, candidatos))
        return False
    plan.ajuste_id = ajuste.id
    plan.reduccion_ajuste += efecto
    return True


# --- Aviso que llega después de importar (D45) -------------------------------------

@dataclass(frozen=True)
class AvisoNuevo:
    """Un aviso del correo que la sincronización va a guardar."""

    fecha: date
    tipo: str
    monto_centavos: int  # positivo
    descripcion: str


@dataclass(frozen=True)
class DecisionAviso:
    """``accion``: ``"nuevo"`` (se guarda como siempre), ``"confirmar"`` (es el
    movimiento ``movimiento_id`` que ya entró del banco) o ``"preguntar"``
    (``candidatos``: los movimientos del banco que podrían ser)."""

    accion: str
    movimiento_id: int | None = None
    candidatos: tuple[int, ...] = ()


def _emparejar_aviso_activos(aviso: AvisoNuevo, sin_aviso: Iterable[MovimientoApp]) -> DecisionAviso:
    """Busca, entre lo que entró del banco sin aviso, el movimiento de este aviso.

    Mismas reglas que ``conciliar`` (D45): monto exacto con día ±1 y destinos
    que no se contradigan, prefiriendo el mismo destino y el mismo día; las
    repeticiones exactas son intercambiables (se toma la de menor id). Un
    exacto y un parecido del mismo día son ambiguos y se preguntan. Sin
    exactos, un único parecido con destino o palabra propia en común se
    confirma (queda el monto del banco); los demás se preguntan.
    """
    banco = [
        m for m in sin_aviso
        if m.origen == ORIGEN_EXTRACTO and m.estado == ESTADO_SIN_AVISO and not m.reservado
    ]
    como_fila = FilaBanco(
        aviso.fecha,
        signo(aviso.tipo) * aviso.monto_centavos,
        aviso.descripcion,
        destino(MovimientoApp(0, aviso.fecha, aviso.tipo, aviso.monto_centavos, aviso.descripcion,
                              ORIGEN_GMAIL)),
    )

    def destinos(m: MovimientoApp) -> str:
        return _destinos(como_fila, m)

    exactos = [
        m for m in banco
        if _mismo_sentido(como_fila, m)
        and m.monto_centavos == aviso.monto_centavos
        and abs((m.fecha - aviso.fecha).days) <= 1
        and destinos(m) != "distinto"
    ]
    parecidos = [
        m for m in banco
        if _mismo_sentido(como_fila, m)
        and m.fecha == aviso.fecha
        and m.monto_centavos != aviso.monto_centavos
        and es_parecido(signo(m.tipo) * m.monto_centavos, aviso.monto_centavos)
        and destinos(m) != "distinto"
    ]
    if exactos and parecidos:
        # Un exacto puede pertenecer a otro aviso indistinguible. Dejar que el
        # dueño elija evita consumirlo y dejar sin respaldo el aviso parecido.
        return DecisionAviso("preguntar", candidatos=tuple(sorted(m.id for m in exactos + parecidos)))
    if exactos:
        mejor = min(
            exactos,
            key=lambda m: (destinos(m) != "igual", abs((m.fecha - aviso.fecha).days), m.id),
        )
        return DecisionAviso("confirmar", mejor.id)
    if not parecidos:
        return DecisionAviso("nuevo")
    if len(parecidos) == 1 and (
        destinos(parecidos[0]) == "igual"
        or palabras_propias(aviso.descripcion) & palabras_propias(parecidos[0].descripcion)
    ):
        return DecisionAviso("confirmar", parecidos[0].id)
    return DecisionAviso("preguntar", candidatos=tuple(sorted(m.id for m in parecidos)))


def emparejar_aviso(
    aviso: AvisoNuevo, sin_aviso: Iterable[MovimientoApp], descartes: Iterable[ReservaDescarte] = (),
) -> DecisionAviso:
    """Un aviso tardío consume una sombra sin reactivar su movimiento.

    Si podría ser una ocurrencia activa o descartada, la identidad del aviso
    no permite escoger por ID: se pregunta. El gmail_id consume la reserva
    definitivamente en el guardado, por lo que otro aviso idéntico puede ser nuevo.
    """
    activos = list(sin_aviso)
    sombras = {r.movimiento.id: r.movimiento for r in descartes
               if r.gmail_id is None and r.banco is not None
               and r.movimiento.origen == ORIGEN_EXTRACTO
               and r.movimiento.estado == ESTADO_SIN_AVISO and not r.movimiento.reservado}
    if not sombras:
        return _emparejar_aviso_activos(aviso, activos)
    banco = [m for m in activos if m.origen == ORIGEN_EXTRACTO and m.estado == ESTADO_SIN_AVISO and not m.reservado]
    banco.extend(sombras.values())
    f = FilaBanco(aviso.fecha, signo(aviso.tipo) * aviso.monto_centavos, aviso.descripcion,
                  destino(MovimientoApp(0, aviso.fecha, aviso.tipo, aviso.monto_centavos, aviso.descripcion, ORIGEN_GMAIL)))
    exactos = [m for m in banco if _mismo_sentido(f, m) and m.monto_centavos == aviso.monto_centavos
               and abs((m.fecha - aviso.fecha).days) <= 1 and _destinos(f, m) != "distinto"]
    decision = _emparejar_aviso_activos(aviso, banco)
    if exactos and any(m.id in sombras for m in exactos):
        mezcla = any(m.id not in sombras for m in exactos)
        if mezcla or len({_identidad(m) for m in exactos}) > 1:
            candidatos = {m.id for m in exactos} | set(decision.candidatos)
            return DecisionAviso("preguntar", candidatos=tuple(sorted(candidatos)))
    if decision.accion == "confirmar" and decision.movimiento_id in sombras:
        return replace(decision, accion="descartado")
    return decision
