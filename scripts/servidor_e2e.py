"""Servidor para las pruebas en navegador del frontend (ítem 12).

Levanta la app real (``crear_app``: API, CSP, sesión, CSRF y ``/app``) con una
base SQLite temporal y **solo datos inventados**, sirviendo la compilación de
``frontend/dist``. Lo usa Playwright (``frontend/playwright.config.ts``,
``webServer``); no sirve para producción.

    python scripts/servidor_e2e.py --puerto 8123

La contraseña de prueba (inventada) es ``CONTRASENA_E2E``; Playwright la lee
de la misma constante en ``frontend/e2e/ayudas.ts``.

Datos de Inicio (ítem 13), todos inventados y con fechas relativas al mes
actual de Colombia (así las pruebas sirven cualquier mes): saldo configurado
desde el día 1 del mes anterior, gastos de todas las categorías (las mismas
cifras del prototipo aprobado), ingresos, un ajuste y 3 movimientos sin
categorizar; el mes anterior con algunos gastos y un ingreso, y la última
sincronización correcta.

Movimientos (ítem 14): dos reglas inventadas (compras en SUPERMERCADO LA
ESPIGA van a Mercado; transferencias a *3000000001, a Transporte). Lo que
coincide con ellas queda categorizado "por regla"; lo demás del mes actual,
"a mano", salvo PAPELERIA EJEMPLO y el mes anterior, que quedan sin origen
(como lo categorizado antes de guardar cómo: "desconocido"). Como las pruebas
de Movimientos categorizan y crean reglas, ``GET /e2e/datos/reiniciar`` deja
los datos como al arrancar.

Categorías y reglas (ítem 15): las categorías iniciales de la migración, una
propia inventada ("Mascotas", de gasto) con una regla, la regla de ingreso
(ingresos de EMPRESA EJEMPLO S.A.S. van a Sueldo) y un ingreso sin
categorizar del mes anterior (pendiente, como los gastos). Como las pruebas
crean, renombran y borran categorías, ``/e2e/datos/reiniciar`` también las
deja como al arrancar.

Reglas combinables (ítem 17): ``GET /e2e/datos/buses`` agrega hoy dos
transferencias pendientes de $3.200 a cuentas distintas (inventadas), para
probar que una regla por monto las categoriza sin importar el destino. No
están en los datos de arranque (así no cambian las cifras de las demás
pruebas); ``/e2e/datos/reiniciar`` las quita.

Ítem 38 (pulido): el servidor de pruebas declara un ``gmail_token`` inventado para
que el servidor diga ``debe_sincronizar_al_abrir`` (con Gmail falso, la
sincronización no trae nada). ``GET /e2e/datos/sincronizacion-vieja`` deja la
última sincronización de hace 3 horas (entonces el servidor dice que toca
sincronizar al abrir); ``GET /e2e/datos/grupos`` agrega hoy 20 compras iguales
pendientes de $3.200 ("COBRO VIAJE TRANSPORTE MASIVO"), un grupo para
categorizar con un toque. Las dos son idempotentes y ``/e2e/datos/reiniciar``
las quita.

Gmail no se usa de verdad: el cliente falso no trae correos. Solo para las
pruebas, ``GET /e2e/gmail/revocado`` hace que la siguiente sincronización
falle (y el reproceso de No reconocidos) como si Gmail hubiera revocado el
permiso, y ``GET /e2e/gmail/ok`` lo deja como antes. Ítem 19: hay 3 correos no
reconocidos inventados; al reprocesarlos, el Gmail falso hace que uno
(``correo-e2e-2``) se reconozca y los otros dos sigan sin reconocerse. Esa ruta existe solo en este servidor de pruebas.

Saldo (ítem 16): ``GET /e2e/datos/saldo`` deja los datos como al arrancar y
suma dos ingresos a mano del mes actual: uno anterior al último ajuste (no se
puede borrar) y otro posterior a todos los ajustes (se puede borrar); es
idempotente. En los datos de arranque, "Efectivo venta bicicleta" tampoco se
puede borrar: el ajuste del mes anterior se registró después (id mayor).
Para "Configurar saldo", ``GET /e2e/datos/sin-saldo`` borra los movimientos y
la configuración del saldo (idempotente); ``/e2e/datos/reiniciar`` los repone.
``GET /e2e/datos/movimiento-anterior`` deja el saldo desde el día 1 de este mes
y una sola compra del día anterior (configuración fija, desglose en cero).
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))

import uvicorn  # noqa: E402

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

from finanzas import db, seguridad, sincronizacion  # noqa: E402
from finanzas.bootstrap.saldo import componer_saldo  # noqa: E402
from finanzas.compartido import hora  # noqa: E402
from finanzas.categorizacion import CAMPO_POR_TIPO, normalizar  # noqa: E402
from finanzas.compartido.config import Config  # noqa: E402
from finanzas.gmail import CorreoGmail, ErrorAutorizacionGmail  # noqa: E402
from finanzas.compartido.hora import ZONA_COLOMBIA  # noqa: E402
from finanzas.web.app import crear_app  # noqa: E402
from tests.soporte.gmail_falso import AUTENTICACION_LEGITIMA, REMITENTE_OFICIAL  # noqa: E402

CONTRASENA_E2E = "clave-e2e-inventada"
SECRETO_E2E = "secreto-e2e-inventado-de-mas-de-32-caracteres"
# Correos no reconocidos inventados (ítem 19), con fechas relativas a hoy:
# (id, días antes de hoy, hora, asunto). Al reprocesar, el Gmail falso solo
# "arregla" RECONOCIBLE: ese pasa a ser un movimiento y los otros siguen igual.
NO_RECONOCIDOS = [
    ("correo-e2e-1", 1, "21:28", "Alertas y Notificaciones"),
    ("correo-e2e-2", 3, "11:02", "Bancolombia te informa"),
    ("correo-e2e-3", 5, "18:47", "Aviso de transacción"),
]
RECONOCIBLE = "correo-e2e-2"
DESCRIPCION_RECONOCIDO = "TIENDA REPROCESADA EJEMPLO"


# Saldo inicial (inventado) elegido para que el saldo actual sea el del
# prototipo: 869.400 + ingresos 10.550.000 − gastos 6.649.450 − ajustes
# (18.400 + 12.400) = 4.739.150. (Ítem 15: el ingreso pendiente de 400.000 del
# mes anterior se resta aquí para no mover el saldo del prototipo.)
SALDO_INICIAL = 86_940_000

# (días antes de hoy, hora, tipo, descripción, centavos, categoría u None).
# Mes actual: gasto total $1.842.450 (el del prototipo), ingresos $5.350.000.
MES_ACTUAL = [
    (0, "07:40", "compra", "PANADERIA EL TRIGAL", 850_000, None),
    (0, "07:12", "transferencia", "*3000000001", 320_000, "Transporte"),
    (1, "21:28", "transferencia", "LAURA GÓMEZ EJEMPLO", 620_000, None),
    (1, "18:15", "compra", "SUPERMERCADO LA ESPIGA", 13_244_950, "Mercado"),
    (2, "12:30", "compra", "TIENDA LA ESQUINA EJEMPLO", 1_300_000, None),
    (2, "08:00", "ingreso", "EMPRESA EJEMPLO S.A.S.", 480_000_000, "Sueldo"),
    (3, "20:10", "compra", "RESTAURANTE LA OLLA EJEMPLO", 29_840_000, "Restaurantes"),
    (4, "10:05", "compra", "MERCADO EL CAMPO EJEMPLO", 35_380_000, "Mercado"),
    (5, "09:00", "compra", "EMPRESA DE SERVICIOS EJEMPLO", 41_280_000, "Vivienda y servicios"),
    (5, "17:45", "compra", "ESTACION DE SERVICIO EJEMPLO", 18_340_000, "Transporte"),
    (6, "16:20", "compra", "ALMACEN EJEMPLO", 15_990_000, "Compras"),
    (6, "15:00", "compra", "HELADERIA EJEMPLO", 9_630_000, "Antojos"),
    (7, "11:11", "compra", "DROGUERIA EJEMPLO", 8_400_050, "Salud"),
    (8, "19:30", "compra", "CINE EJEMPLO", 6_200_000, "Entretenimiento"),
    (8, "10:00", "ingreso", "Efectivo venta bicicleta", 55_000_000, "Otros ingresos"),
    (9, "13:40", "compra", "PAPELERIA EJEMPLO", 2_850_000, "Otros"),
    (9, "23:00", "ajuste", "Ajuste de saldo", -1_840_000, None),
]
# Mes anterior: gasto $4.807.000, ingreso $4.800.000, un ajuste y un pendiente
# (días del mes): así "Últimos movimientos" de un mes pasado muestra un ingreso
# y un ajuste, y la bandeja tiene un pendiente de otro mes.
MES_ANTERIOR = [
    (3, "09:00", "compra", "EMPRESA DE SERVICIOS EJEMPLO", 210_000_000, "Vivienda y servicios"),
    (8, "18:00", "compra", "SUPERMERCADO LA ESPIGA", 145_000_000, "Mercado"),
    (12, "20:00", "compra", "RESTAURANTE LA OLLA EJEMPLO", 70_000_000, "Restaurantes"),
    (15, "07:00", "transferencia", "*3000000001", 35_000_000, "Transporte"),
    (20, "16:00", "compra", "ALMACEN EJEMPLO", 20_000_000, "Compras"),
    (25, "23:00", "ajuste", "Ajuste de saldo", -1_240_000, None),
    (28, "08:00", "ingreso", "EMPRESA EJEMPLO S.A.S.", 480_000_000, "Sueldo"),
    # Pendiente de un mes anterior: la bandeja "Sin categorizar" es de todos los meses (ítem 14).
    (10, "12:00", "compra", "CAFETERIA EL PARQUE EJEMPLO", 700_000, None),
    # Ingreso sin categorizar (ítem 15): también es pendiente, y su monto va aparte del de los gastos.
    (14, "11:00", "ingreso", "CARLOS RUIZ EJEMPLO", 40_000_000, None),
]

# Saldo (ítem 16), solo con /e2e/datos/saldo: (descripción, centavos) de un
# ingreso a mano anterior al último ajuste (no se puede borrar) y de uno
# posterior a todos (se puede borrar; con centavos, para ver que el saldo baja
# exactamente su monto).
INGRESO_ANTERIOR_AL_AJUSTE = ("Efectivo arriendo garaje EJEMPLO", 20_000_000)
INGRESO_BORRABLE = ("Efectivo venta de libros EJEMPLO", 8_500_050)

# Categoría propia inventada (ítem 15): (nombre, clase, color, ícono). Su par
# color + ícono no lo usa ninguna de las iniciales.
CATEGORIAS_PROPIAS = [("Mascotas", "gasto", "cat-antojos", "heart-pulse")]

# Reglas inventadas (ítem 14): (tipo, descripción, categoría). La de ingreso
# (ítem 15, como en el prototipo): así los ingresos no quedan pendientes y la
# bandeja conserva sus cifras.
REGLAS = [
    ("compra", "SUPERMERCADO LA ESPIGA", "Mercado"),
    ("transferencia", "*3000000001", "Transporte"),
    ("ingreso", "EMPRESA EJEMPLO S.A.S.", "Sueldo"),
    # De la categoría propia: al borrarla, hay que elegir a cuál pasa (ítem 15).
    ("compra", "VETERINARIA EJEMPLO", "Mascotas"),
]
# Ítem 17 (solo con /e2e/datos/buses): (hora, cuenta destino); las dos de $3.200.
BUSES = [("06:30", "*3000000002"), ("06:10", "*3000000003")]
MONTO_BUS = 320_000

# Ítem 38 (solo con /e2e/datos/grupos): 20 compras iguales y pendientes, de $3.200 cada una.
VIAJES_DEL_GRUPO = 20
DESCRIPCION_DEL_GRUPO = "COBRO VIAJE TRANSPORTE MASIVO"
MONTO_VIAJE = 320_000

# Categorizados sin origen guardado ("desconocido"), además de todo el mes anterior.
SIN_ORIGEN = {"PAPELERIA EJEMPLO"}


def _insertar_no_reconocidos(conn) -> None:
    hoy = hora.hoy_colombia()
    with db.transaccion(conn):
        conn.execute(db.correos_no_reconocidos.delete())
        for gmail_id, dias, hh_mm, asunto in NO_RECONOCIDOS:
            momento = datetime.combine(hoy - timedelta(days=dias), datetime.strptime(hh_mm, "%H:%M").time())
            conn.execute(
                db.correos_no_reconocidos.insert().values(
                    gmail_id=gmail_id, fecha=momento.isoformat(timespec="seconds"), asunto=asunto
                )
            )


def _fecha_de(gmail_id: str) -> datetime:
    for id_, dias, hh_mm, _ in NO_RECONOCIDOS:
        if id_ == gmail_id:
            dia = hora.hoy_colombia() - timedelta(days=dias)
            return datetime.combine(dia, datetime.strptime(hh_mm, "%H:%M").time(), tzinfo=ZONA_COLOMBIA)
    raise AssertionError(f"Correo desconocido: {gmail_id}")


class GmailFalso:
    """Sin correos nuevos; o, en modo "revocado", Gmail rechaza el permiso.

    Al reprocesar, ``obtener`` devuelve un aviso válido solo para
    ``RECONOCIBLE``; los demás siguen sin reconocerse.
    """

    def __init__(self) -> None:
        self.modo = "ok"

    def __call__(self) -> "GmailFalso":
        if self.modo == "revocado":
            raise ErrorAutorizacionGmail("Permiso de Gmail revocado (prueba e2e, inventado).")
        return self

    def listar_ids(self, desde: date) -> list[str]:
        return []

    def obtener(self, gmail_id: str) -> CorreoGmail:
        fecha = _fecha_de(gmail_id)
        if gmail_id == RECONOCIBLE:
            # El aviso dice "hoy, 00:01": el movimiento cae en el mes actual, donde Movimientos lo muestra.
            texto = (
                f"Bancolombia: Compraste $52.300,00 en {DESCRIPCION_RECONOCIDO} con tu T.Deb *1234, "
                f"el {hora.hoy_colombia():%d/%m/%Y} a las 00:01. Correo inventado para pruebas."
            )
        else:
            texto = "Texto inventado que el lector no reconoce como aviso."
        return CorreoGmail(
            gmail_id=gmail_id,
            fecha=fecha,
            asunto="Aviso inventado",
            texto=texto,
            remitente=REMITENTE_OFICIAL,
            autenticacion=AUTENTICACION_LEGITIMA,
        )


def _id_categoria(conn, nombre: str) -> int:
    ids = dict(conn.execute(select(db.categorias.c.nombre, db.categorias.c.id)).all())
    if nombre not in ids:
        # Desde la migración 0005 (ítem 15) todas las del prototipo ya existen.
        raise KeyError(f"Categoría inventada desconocida: {nombre}")
    return ids[nombre]


def _reglas(conn) -> dict[tuple[str, str], tuple[int, str]]:
    """Crea las reglas inventadas: (campo, texto) -> (id de la regla, categoría)."""
    reglas = {}
    for tipo, descripcion, categoria in REGLAS:
        campo, texto = CAMPO_POR_TIPO[tipo], normalizar(descripcion)
        regla_id = conn.execute(
            db.reglas.insert().values(campo=campo, texto=texto, categoria_id=_id_categoria(conn, categoria))
        ).inserted_primary_key[0]
        reglas[(campo, texto)] = (regla_id, categoria)
    return reglas


def _movimiento(
    conn, momento: datetime, tipo: str, descripcion: str, centavos: int, categoria, numero: int,
    reglas: dict[tuple[str, str], tuple[int, str]], con_origen: bool,
):
    de_gmail = tipo != "ajuste" and descripcion != "Efectivo venta bicicleta"
    origen_categoria, regla_id = None, None
    if categoria is not None:
        regla = reglas.get((CAMPO_POR_TIPO.get(tipo, ""), normalizar(descripcion)))
        if regla is not None and regla[1] == categoria:
            origen_categoria, regla_id = "regla", regla[0]
        elif con_origen and descripcion not in SIN_ORIGEN:
            origen_categoria = "manual"
    conn.execute(
        db.movimientos.insert().values(
            fecha_hora=momento.isoformat(timespec="seconds"),
            monto_centavos=centavos,
            tipo=tipo,
            descripcion=descripcion,
            categoria_id=None if categoria is None else _id_categoria(conn, categoria),
            origen_categoria=origen_categoria,
            regla_id=regla_id,
            origen="gmail" if de_gmail else "manual",
            gmail_id=f"e2e-movimiento-{numero}" if de_gmail else None,
        )
    )


def _momento_mes_actual(dias: int, hh_mm: str, hoy: date, primero: date) -> datetime:
    """Instante de un movimiento "``dias`` días antes de hoy a las ``hh_mm``", dentro del mes.

    Si el mes ya tiene días suficientes para el movimiento más antiguo, es
    exactamente eso. Si no (primeros días del mes), TODOS se comprimen con una
    escala lineal al rango [día 1 00:00, hoy 23:59:59]: así el orden relativo es
    siempre el mismo, ninguno cae en el mes anterior y ninguno se empata.
    """
    medianoche = datetime.min.time()
    real = datetime.combine(hoy - timedelta(days=dias), datetime.strptime(hh_mm, "%H:%M").time())
    maximo = max(d for d, *_ in MES_ACTUAL)
    ideal_inicio = datetime.combine(hoy - timedelta(days=maximo), medianoche)
    if ideal_inicio >= datetime.combine(primero, medianoche):
        return real
    ideal_fin = datetime.combine(hoy, datetime.max.time()).replace(microsecond=0)
    inicio = datetime.combine(primero, medianoche)
    fraccion = (real - ideal_inicio) / (ideal_fin - ideal_inicio)
    return (inicio + (ideal_fin - inicio) * fraccion).replace(microsecond=0)


def _poblar(conn) -> None:
    """Datos inventados de Inicio, relativos al mes actual de Colombia."""
    hoy = _hoy_de_datos()
    primero = hoy.replace(day=1)
    anterior = (primero - timedelta(days=1)).replace(day=1)
    componer_saldo(conn).configurar(SALDO_INICIAL, anterior)
    numero = 0
    with db.transaccion(conn):
        for nombre, clase, color, icono in CATEGORIAS_PROPIAS:
            conn.execute(db.categorias.insert().values(nombre=nombre, clase=clase, color=color, icono=icono))
        reglas = _reglas(conn)
        for dias, hh_mm, tipo, descripcion, centavos, categoria in MES_ACTUAL:
            momento = _momento_mes_actual(dias, hh_mm, hoy, primero)
            numero += 1
            _movimiento(conn, momento, tipo, descripcion, centavos, categoria, numero, reglas, True)
        for dia, hh_mm, tipo, descripcion, centavos, categoria in MES_ANTERIOR:
            momento = datetime.combine(anterior.replace(day=dia), datetime.strptime(hh_mm, "%H:%M").time())
            numero += 1
            _movimiento(conn, momento, tipo, descripcion, centavos, categoria, numero, reglas, False)
    # La última sincronización salió bien (la hace "el temporizador", ahora).
    sincronizacion.guardar_estado(
        conn, "comando", resultado=sincronizacion.ResultadoSincronizacion(nuevos=3)
    )


def _ingresos_de_saldo(conn) -> None:
    """Saldo (ítem 16): dos ingresos a mano del mes actual, uno a cada lado del último ajuste.

    El anterior va a medio camino entre el día 1 y el ajuste (así queda en el
    mes aunque los datos se compriman): la API no deja borrarlo, porque el
    ajuste ya lo contó. El borrable va a medio camino entre el ajuste y ahora,
    y se inserta al final (id mayor que el de todo ajuste).
    """
    primero = datetime.combine(_hoy_de_datos().replace(day=1), datetime.min.time())
    texto_ajuste = conn.execute(
        select(db.movimientos.c.fecha_hora)
        .where(db.movimientos.c.tipo == "ajuste")
        .order_by(db.movimientos.c.fecha_hora.desc())
        .limit(1)
    ).scalar_one()
    ajuste = datetime.fromisoformat(texto_ajuste)
    ahora = hora.ahora_colombia().replace(tzinfo=None)
    despues = ajuste + (ahora - ajuste) / 2 if ahora > ajuste else ajuste + timedelta(minutes=1)
    otros_ingresos = _id_categoria(conn, "Otros ingresos")
    with db.transaccion(conn):
        for (descripcion, centavos), momento in (
            (INGRESO_ANTERIOR_AL_AJUSTE, primero + (ajuste - primero) / 2),
            (INGRESO_BORRABLE, despues),
        ):
            conn.execute(
                db.movimientos.insert().values(
                    fecha_hora=momento.replace(microsecond=0).isoformat(timespec="seconds"),
                    monto_centavos=centavos,
                    tipo="ingreso",
                    descripcion=descripcion,
                    categoria_id=otros_ingresos,
                    origen_categoria="manual",
                    origen="manual",
                )
            )


def crear(directorio: Path, dist: Path):
    ruta_db = directorio / "e2e.db"
    db.preparar(str(ruta_db))
    conn = db.conectar(str(ruta_db))
    try:
        # Las categorías iniciales (de la migración), para volver a ellas al reiniciar.
        iniciales = [dict(c) for c in conn.execute(select(db.categorias)).mappings().all()]
        _insertar_no_reconocidos(conn)
        _poblar(conn)
    finally:
        conn.close()
    config = Config(
        db_path=str(ruta_db),
        app_password_hash=seguridad.generar_hash(CONTRASENA_E2E),
        session_secret=SECRETO_E2E,
        cookie_secure=False,  # http://127.0.0.1 en las pruebas
        gmail_token="token-gmail-e2e-inventado",  # solo para `debe_sincronizar_al_abrir` (ítem 38)
        max_intentos=50,  # las pruebas se equivocan a propósito; que no se bloqueen
        bloqueo_minutos=1,
    )
    gmail = GmailFalso()
    app = crear_app(config, fabrica_cliente_gmail=gmail, directorio_frontend=dist)

    @app.get("/e2e/gmail/{modo}", include_in_schema=False)
    def elegir_modo_gmail(modo: str) -> dict[str, str]:
        """Solo en este servidor de pruebas: cómo responde Gmail en la próxima sincronización."""
        if modo not in ("ok", "revocado"):
            raise HTTPException(404)
        gmail.modo = modo
        return {"modo": modo}

    def limpiar_importaciones(conn) -> None:
        # Solo datos inventados del servidor e2e: primero las filas hijas.
        for tabla in (db.reversiones_importacion, db.candidatos_pregunta,
                      db.preguntas_conciliacion, db.cambios_importacion,
                      db.descartes_movimientos, db.importaciones):
            conn.execute(tabla.delete())

    def reiniciar(conn) -> None:
        with db.transaccion(conn):
            limpiar_importaciones(conn)
            conn.execute(db.movimientos.delete())
            conn.execute(db.reglas.delete())
            conn.execute(db.configuracion_saldo.delete())
            conn.execute(db.categorias.delete())
            conn.execute(db.categorias.insert(), iniciales)
        _insertar_no_reconocidos(conn)
        _poblar(conn)

    @app.get("/e2e/datos/reiniciar", include_in_schema=False)
    def reiniciar_datos() -> dict[str, str]:
        """Solo en este servidor de pruebas: los movimientos y reglas como al arrancar."""
        conn = db.conectar(str(ruta_db))
        try:
            reiniciar(conn)
        finally:
            conn.close()
        return {"datos": "reiniciados"}

    @app.get("/e2e/datos/importacion", include_in_schema=False)
    def datos_importacion() -> dict[str, str]:
        """Escenario bancario inventado estable: preguntas y una ausencia."""
        conn = db.conectar(str(ruta_db))
        try:
            reiniciar(conn)
            with db.transaccion(conn):
                conn.execute(db.movimientos.delete())
                conn.execute(db.reglas.delete())
                conn.execute(db.configuracion_saldo.delete())
            componer_saldo(conn).configurar(100_000_000, date(2026, 8, 1))
            with db.transaccion(conn):
                for ident, descripcion, monto, dia in (
                    ("e2e-banco-parecido", "CAFE INVENTADO", 3650000, 10),
                    ("e2e-banco-ausente", "TIENDA AUSENTE EJEMPLO", 8990000, 11),
                ):
                    conn.execute(db.movimientos.insert().values(
                        fecha_hora=f"2026-08-{dia:02d}T10:00:00", tipo="compra",
                        descripcion=descripcion, monto_centavos=monto,
                        origen="gmail", gmail_id=ident))
        finally:
            conn.close()
        return {"datos": "importacion"}

    @app.get("/e2e/datos/importacion-candidatos", include_in_schema=False)
    def datos_importacion_candidatos() -> dict[str, str]:
        """Dos candidatos inventados visualmente iguales, con claves distintas."""
        datos_importacion()
        conn = db.conectar(str(ruta_db))
        try:
            with db.transaccion(conn):
                conn.execute(db.movimientos.insert().values(
                    fecha_hora="2026-08-10T10:00:00", tipo="compra",
                    descripcion="CAFE INVENTADO", monto_centavos=3650000,
                    origen="gmail", gmail_id="e2e-banco-segundo-candidato"))
        finally:
            conn.close()
        return {"datos": "importacion-candidatos"}

    @app.get("/e2e/datos/importacion-confirmacion/{origen}", include_in_schema=False)
    def datos_importacion_confirmacion(origen: str, parecido: bool = False) -> dict[str, str]:
        """Un ingreso inventado que el banco confirma exactamente una vez."""
        if origen not in {"gmail", "manual"}:
            raise ValueError("Origen de prueba no permitido")
        datos_importacion_formatos()
        conn = db.conectar(str(ruta_db))
        try:
            with db.transaccion(conn):
                conn.execute(db.movimientos.delete())
                conn.execute(db.movimientos.insert().values(
                    fecha_hora="2026-08-10T10:00:00", tipo="ingreso",
                    descripcion="DEPOSITO A MANO EJEMPLO" if parecido else "INGRESO INVENTADO",
                    monto_centavos=520 if parecido else 500,
                    origen=origen,
                    gmail_id="e2e-confirmacion-inventada" if origen == "gmail" else None))
        finally:
            conn.close()
        return {"datos": "importacion-confirmacion"}

    @app.get("/e2e/datos/importacion-formatos", include_in_schema=False)
    def datos_importacion_formatos() -> dict[str, str]:
        """Ingreso bancario y ajuste negativo del mismo día, totalmente inventados."""
        conn = db.conectar(str(ruta_db))
        try:
            reiniciar(conn)
            with db.transaccion(conn):
                conn.execute(db.movimientos.delete())
                conn.execute(db.reglas.delete())
                conn.execute(db.configuracion_saldo.delete())
            componer_saldo(conn).configurar(100_000, date(2026, 8, 1))
            with db.transaccion(conn):
                conn.execute(db.movimientos.insert().values(
                    fecha_hora="2026-08-10T10:00:00", tipo="ajuste",
                    descripcion="", monto_centavos=-500, origen="manual"))
        finally:
            conn.close()
        return {"datos": "importacion-formatos"}

    @app.get("/e2e/datos/saldo", include_in_schema=False)
    def datos_saldo() -> dict[str, str]:
        """Solo en este servidor de pruebas: los datos de arranque más dos ingresos a mano (ítem 16)."""
        conn = db.conectar(str(ruta_db))
        try:
            reiniciar(conn)
            _ingresos_de_saldo(conn)
        finally:
            conn.close()
        return {"datos": "saldo"}

    @app.get("/e2e/datos/sin-saldo", include_in_schema=False)
    def datos_sin_saldo() -> dict[str, str]:
        """Solo en este servidor de pruebas: sin saldo configurado y sin movimientos (ítem 16).

        Para configurar el saldo desde cero. Idempotente; deja las categorías y
        reglas como están. ``/e2e/datos/reiniciar`` vuelve a los datos de arranque.
        """
        conn = db.conectar(str(ruta_db))
        try:
            with db.transaccion(conn):
                limpiar_importaciones(conn)
                conn.execute(db.movimientos.delete())
                conn.execute(db.configuracion_saldo.delete())
        finally:
            conn.close()
        return {"datos": "sin-saldo"}

    @app.get("/e2e/datos/movimiento-anterior", include_in_schema=False)
    def datos_movimiento_anterior() -> dict[str, str]:
        """Solo en este servidor de pruebas: saldo desde el día 1 de este mes y una
        sola compra inventada del día anterior (ítem 16).

        El desglose no la suma (es anterior a ``fecha_inicio``) y no sale en las
        filas del mes, pero la configuración queda fija: así se prueba que la
        pantalla usa ``configuracion_fija`` y no lo deduce. Idempotente;
        ``/e2e/datos/reiniciar`` vuelve a los datos de arranque.
        """
        inicio = _hoy_de_datos().replace(day=1)
        conn = db.conectar(str(ruta_db))
        try:
            with db.transaccion(conn):
                limpiar_importaciones(conn)
                conn.execute(db.movimientos.delete())
                conn.execute(db.configuracion_saldo.delete())
            componer_saldo(conn).configurar(SALDO_INICIAL, inicio)
            with db.transaccion(conn):
                conn.execute(
                    db.movimientos.insert().values(
                        fecha_hora=f"{(inicio - timedelta(days=1)).isoformat()}T18:30:00",
                        monto_centavos=4_550_000,
                        tipo="compra",
                        descripcion="TIENDA ANTERIOR EJEMPLO",
                        origen="gmail",
                        gmail_id="e2e-anterior-1",
                    )
                )
        finally:
            conn.close()
        return {"datos": "movimiento-anterior"}

    @app.get("/e2e/datos/buses", include_in_schema=False)
    def agregar_buses() -> dict[str, int]:
        """Solo en este servidor de pruebas: dos transferencias pendientes de $3.200 (ítem 17).

        Idempotente: si ya están (mismo ``gmail_id``), no las repite ni falla;
        ``/e2e/datos/reiniciar`` las quita.
        """
        hoy = _hoy_de_datos()
        agregados = 0
        conn = db.conectar(str(ruta_db))
        try:
            with db.transaccion(conn):
                for numero, (hh_mm, cuenta) in enumerate(BUSES, start=1):
                    gmail_id = f"e2e-bus-{numero}"
                    ya_esta = conn.execute(
                        select(db.movimientos.c.id).where(db.movimientos.c.gmail_id == gmail_id)
                    ).first()
                    if ya_esta is not None:
                        continue
                    agregados += 1
                    momento = _momento_mes_actual(0, hh_mm, hoy, hoy.replace(day=1))
                    conn.execute(
                        db.movimientos.insert().values(
                            fecha_hora=momento.isoformat(timespec="seconds"),
                            monto_centavos=MONTO_BUS,
                            tipo="transferencia",
                            descripcion=cuenta,
                            origen="gmail",
                            gmail_id=gmail_id,
                        )
                    )
        finally:
            conn.close()
        return {"agregados": agregados}

    @app.get("/e2e/datos/sincronizacion-vieja", include_in_schema=False)
    def sincronizacion_vieja() -> dict[str, str]:
        """Solo en este servidor de pruebas: la última sincronización fue hace 3 horas (ítem 38).

        Así el servidor responde ``debe_sincronizar_al_abrir: true``. Idempotente;
        al sincronizar, o con ``/e2e/datos/reiniciar``, vuelve a quedar reciente.
        """
        hace_tres_horas = (hora.ahora_colombia() - timedelta(hours=3)).isoformat(timespec="seconds")
        conn = db.conectar(str(ruta_db))
        try:
            with db.transaccion(conn):
                conn.execute(db.estado_sincronizacion.update().values(terminada_en=hace_tres_horas))
        finally:
            conn.close()
        return {"terminada_en": hace_tres_horas}

    @app.get("/e2e/datos/grupos", include_in_schema=False)
    def agregar_grupo() -> dict[str, int]:
        """Solo en este servidor de pruebas: 20 compras iguales pendientes de $3.200 (ítem 38).

        Idempotente: si ya están (mismo ``gmail_id``), no las repite;
        ``/e2e/datos/reiniciar`` las quita.
        """
        hoy = _hoy_de_datos()
        agregados = 0
        conn = db.conectar(str(ruta_db))
        try:
            with db.transaccion(conn):
                for numero in range(1, VIAJES_DEL_GRUPO + 1):
                    gmail_id = f"e2e-viaje-{numero}"
                    ya_esta = conn.execute(
                        select(db.movimientos.c.id).where(db.movimientos.c.gmail_id == gmail_id)
                    ).first()
                    if ya_esta is not None:
                        continue
                    agregados += 1
                    # Un minuto aparte cada uno, de las 04:00 en adelante, todos el mismo día.
                    momento = datetime.combine(hoy, datetime.min.time()) + timedelta(hours=4, minutes=numero)
                    conn.execute(
                        db.movimientos.insert().values(
                            fecha_hora=momento.isoformat(timespec="seconds"),
                            monto_centavos=MONTO_VIAJE,
                            tipo="compra",
                            descripcion=DESCRIPCION_DEL_GRUPO,
                            origen="gmail",
                            gmail_id=gmail_id,
                        )
                    )
        finally:
            conn.close()
        return {"agregados": agregados}

    # Las rutas de pruebas van antes que las demás (por si alguna atrapa todo).
    for _ in range(8):
        app.router.routes.insert(0, app.router.routes.pop())
    return app


def _hoy_de_datos() -> date:
    """"Hoy" para repartir los datos inventados.

    Solo para pruebas: ``FINANZAS_E2E_HOY=AAAA-MM-DD`` lo fija (debe ser del mes
    actual) y así se comprueba el orden de los datos en cualquier día del mes.
    Solo lo lee este servidor de pruebas; la app real no.
    """
    valor = os.environ.get("FINANZAS_E2E_HOY")
    return date.fromisoformat(valor) if valor else hora.hoy_colombia()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--puerto", type=int, default=8123)
    parser.add_argument("--dist", type=Path, default=RAIZ / "frontend" / "dist")
    args = parser.parse_args()
    if not (args.dist / "index.html").is_file():
        print(f"Falta la compilación en {args.dist}: corre antes npm run build.", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="finanzas-e2e-") as directorio:
        app = crear(Path(directorio), args.dist)
        uvicorn.run(app, host="127.0.0.1", port=args.puerto, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
