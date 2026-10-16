"""Pruebas del lector del Excel de movimientos de Bancolombia (ítem 28).

Todos los archivos se generan aquí con openpyxl y datos inventados: no hay
binarios en el repositorio y nunca un archivo real del banco.
"""

from __future__ import annotations

import io
import time as reloj
import zipfile
from datetime import date, datetime

import pytest
from openpyxl import Workbook

from finanzas.modulos.importaciones.adaptadores.archivos import excel_bancolombia as eb
from tests.soporte import excel_inventado
from finanzas.modulos.importaciones.adaptadores.archivos.excel_bancolombia import (
    ExcelNoReconocido,
    MovimientoExcel,
    leer_excel_movimientos,
    monto_a_centavos,
)
from tests.soporte.excel_bancolombia import reescribir  # ayudas compartidas

ENCABEZADOS = ["Fecha", "Descripción", "Referencia", "Valor"]

# Movimientos inventados con la forma del reporte real: descripciones en
# mayúsculas recortadas a unos 30 caracteres, referencias con celulares o
# cuentas inventadas, valores con signo y centavos.
FILAS_EJEMPLO = [
    [datetime(2026, 9, 1), "PAGO TRANSMILENIO TARJETA DEB", "", -8850],
    [datetime(2026, 9, 2), "COMPRA EN MERPAGO*TIENDA EJEMP", "0000001234", -68630.0],
    [datetime(2026, 9, 3), "TRANSFERENCIA A 3000001234 NEQ", "3000001234", -6000.5],
    [datetime(2026, 9, 4), "ABONO INTERESES AHORROS", None, 0.37],
    [date(2026, 9, 5), "TRANSF DE EMPRESA EJEMPLO S.A.", "000000005678", 160000],
    [datetime(2026, 9, 6), "CUOTA MANEJO TARJ DEB & CIA ÑÚ", "", -1234.56],
    [datetime(2026, 9, 7), "IMPTO GOBIERNO 4X1000", "", -0.01],
]


def libro(filas=None, *, encabezados=None, hoja="Hoja 1", fila_encabezados=1,
          antes=None, extra_hojas=()):
    """Arma un .xlsx inventado en memoria y devuelve sus bytes."""
    wb = Workbook()
    ws = wb.active
    ws.title = hoja
    for _ in range(fila_encabezados - 1):
        ws.append(antes or [])
    ws.append(ENCABEZADOS if encabezados is None else encabezados)
    for fila in FILAS_EJEMPLO if filas is None else filas:
        ws.append(fila)
    for nombre in extra_hojas:
        wb.create_sheet(nombre)
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()




HOJA_XML = "xl/worksheets/sheet1.xml"


def rechazo(contenido, *textos, **kwargs):
    with pytest.raises(ExcelNoReconocido) as error:
        leer_excel_movimientos(contenido, **kwargs)
    for texto in textos:
        assert texto in error.value.motivo
    return error.value.motivo


# ---------------------------------------------------------------------------
# Archivo con la estructura esperada
# ---------------------------------------------------------------------------


def test_lee_movimientos_con_signo_y_centavos():
    movimientos = leer_excel_movimientos(libro(), nombre_archivo="Movimientos.xlsx")
    assert movimientos == [
        MovimientoExcel(date(2026, 9, 1), -885000, "PAGO TRANSMILENIO TARJETA DEB"),
        MovimientoExcel(date(2026, 9, 2), -6863000, "COMPRA EN MERPAGO*TIENDA EJEMP", "*1234"),
        MovimientoExcel(date(2026, 9, 3), -600050, "TRANSFERENCIA A 3000001234 NEQ", "*1234"),
        MovimientoExcel(date(2026, 9, 4), 37, "ABONO INTERESES AHORROS"),
        MovimientoExcel(date(2026, 9, 5), 16000000, "TRANSF DE EMPRESA EJEMPLO S.A.", "*5678"),
        MovimientoExcel(date(2026, 9, 6), -123456, "CUOTA MANEJO TARJ DEB & CIA ÑÚ"),
        MovimientoExcel(date(2026, 9, 7), -1, "IMPTO GOBIERNO 4X1000"),
    ]
    for m in movimientos:
        assert type(m.monto_centavos) is int
        assert type(m.fecha) is date


def test_de_la_referencia_solo_devuelve_los_ultimos_4_digitos():
    """D37: nunca el número completo, ni como campo ni dentro de lo devuelto."""
    movimientos = leer_excel_movimientos(libro())
    assert set(vars(movimientos[0])) == {
        "fecha", "monto_centavos", "descripcion", "referencia", "referencia_sin_formato"}
    assert [m.referencia for m in movimientos] == [None, "*1234", "*1234", None, "*5678", None, None]
    assert not any(m.referencia_sin_formato for m in movimientos)
    texto = repr(movimientos)
    for completo in ("0000001234", "000000005678", "0005678"):
        assert completo not in texto


def test_referencia_puede_ser_numero_o_vacia():
    filas = [
        [datetime(2026, 9, 1), "PAGO EJEMPLO", 3000004567, -100],
        [datetime(2026, 9, 2), "PAGO EJEMPLO", None, -100],
        [datetime(2026, 9, 3), "PAGO EJEMPLO", "  3000000002 ", -100],
        [datetime(2026, 9, 4), "PAGO EJEMPLO", "0001", -100],
    ]
    movimientos = leer_excel_movimientos(libro(filas))
    assert [(m.referencia, m.referencia_sin_formato) for m in movimientos] == [
        ("*4567", False), (None, False), ("*0002", False), ("*0001", False)]


@pytest.mark.parametrize(
    "referencia",
    ["123", "12", "ABC123456", "300 000 0002", "3000-000002", "PSE0000001", "１２３４５",
     -3000000003, 1234.5, "*1234", "0" * 41],
)
def test_referencia_sin_formato_entra_sin_destino_y_no_rechaza(referencia):
    """D45: letras, signos o menos de 4 dígitos -> la fila entra sin destino."""
    filas = [
        [datetime(2026, 9, 1), "PAGO EJEMPLO", referencia, -100],
        [datetime(2026, 9, 2), "PAGO EJEMPLO", "3000000009", -200],
    ]
    movimientos = leer_excel_movimientos(libro(filas))
    assert movimientos[0] == MovimientoExcel(date(2026, 9, 1), -10000, "PAGO EJEMPLO", None, True)
    assert movimientos[1] == MovimientoExcel(date(2026, 9, 2), -20000, "PAGO EJEMPLO", "*0009", False)
    assert str(referencia).strip("*-") not in repr(movimientos).replace("PAGO EJEMPLO", "")


def test_un_error_de_otra_columna_no_muestra_la_referencia():
    filas = [[datetime(2026, 9, 1), "PAGO EJEMPLO", "3000000007", "texto"]]
    motivo = rechazo(libro(filas), "Fila 2")
    assert "3000000007" not in motivo and "0007" not in motivo


def test_solo_encabezados_devuelve_lista_vacia():
    assert leer_excel_movimientos(libro([])) == []


def test_filas_vacias_al_final_se_ignoran():
    filas = [[datetime(2026, 9, 1), "PAGO EJEMPLO", "", -100], [], [None, "  ", None, None]]
    assert len(leer_excel_movimientos(libro(filas))) == 1


def test_descripcion_sin_espacios_externos_y_conserva_especiales():
    filas = [[datetime(2026, 9, 1), "  MERPAGO*TIENDA #12 (BOG)/ÑU  ", "", -100]]
    assert leer_excel_movimientos(libro(filas))[0].descripcion == "MERPAGO*TIENDA #12 (BOG)/ÑU"


def test_encabezados_con_espacios_o_tilde_combinada():
    encabezados = [" Fecha ", "Descripción", "Referencia", "Valor "]
    assert len(leer_excel_movimientos(libro(encabezados=encabezados))) == len(FILAS_EJEMPLO)


def test_extension_xlsx_en_mayusculas():
    assert leer_excel_movimientos(libro(), nombre_archivo="REPORTE.XLSX")


def test_acepta_bytearray():
    assert leer_excel_movimientos(bytearray(libro()))


# ---------------------------------------------------------------------------
# Montos: centavos sin floats, signos y límites
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("valor", "centavos"),
    [
        (1, 100),
        (-1, -100),
        (0.01, 1),
        (-0.01, -1),
        (0.1, 10),
        (1234.56, 123456),  # 1234.56 * 100 en float da 123455.99999999999
        (-1234.56, -123456),
        (4.35, 435),  # 4.35 * 100 en float da 434.99999999999994
        (-68630.0, -6863000),
        (160000, 16000000),
        (999999.99, 99999999),
        (10_000_000_000, eb.MONTO_MAXIMO_CENTAVOS),
        (-10_000_000_000, -eb.MONTO_MAXIMO_CENTAVOS),
        (9_999_999_999.99, eb.MONTO_MAXIMO_CENTAVOS - 1),
    ],
)
def test_monto_a_centavos_exacto(valor, centavos):
    assert monto_a_centavos(valor) == centavos


@pytest.mark.parametrize(
    "valor",
    [
        0, 0.0, -0.0,
        0.001, 1.005, -12.345,
        0.1 + 0.2,  # 0.30000000000000004: no se redondea
        10_000_000_000.01, -10_000_000_001, 1e300,
        float("nan"), float("inf"), float("-inf"),
        True, False,
        "-5,000.00", "100", None, b"100",
    ],
)
def test_monto_a_centavos_rechaza(valor):
    assert monto_a_centavos(valor) is None


def test_valores_desde_el_archivo_con_signos_y_centavos():
    valores = [-0.01, 0.01, -99.99, 99.99, -1234567.89, 7, -7]
    filas = [[datetime(2026, 9, 1), "MOV EJEMPLO", "", v] for v in valores]
    obtenidos = [m.monto_centavos for m in leer_excel_movimientos(libro(filas))]
    assert obtenidos == [-1, 1, -9999, 9999, -123456789, 700, -700]


@pytest.mark.parametrize(
    "valor", [0, "-5,000.00", "100", 1.005, True, None, 10_000_000_000.5, 20_000_000_000]
)
def test_valor_invalido_rechaza_el_archivo(valor):
    filas = [
        [datetime(2026, 9, 1), "PAGO EJEMPLO", "", -100],
        [datetime(2026, 9, 2), "PAGO EJEMPLO", "", valor],
    ]
    rechazo(libro(filas), "Fila 3", "Valor")


# ---------------------------------------------------------------------------
# Fechas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fecha", "texto"),
    [
        (datetime(2026, 9, 1, 14, 30), "hora inesperada"),
        (datetime(2026, 9, 1, 0, 0, 1), "hora inesperada"),
        (datetime(2026, 9, 1, 5, 0, 1), "hora inesperada"),
        (datetime(2026, 9, 1, 4, 59), "hora inesperada"),
        (datetime(2026, 9, 1, 19, 0), "hora inesperada"),  # otro desfase: el día podría correrse
        (datetime(2026, 9, 1, 23, 59, 59), "hora inesperada"),
        ("01/09/2026", "no es una fecha"),
        ("2026-09-01", "no es una fecha"),
        (46266, "no es una fecha"),  # número de serie sin formato de fecha
        (None, "no es una fecha"),
        (datetime(1999, 12, 31), "rango de años"),
        (datetime(2100, 1, 1), "rango de años"),
    ],
)
def test_fecha_invalida_rechaza(fecha, texto):
    rechazo(libro([[fecha, "PAGO EJEMPLO", "", -100]]), "Fila 2", "Fecha", texto)


def test_fecha_limite_de_rango_aceptada():
    filas = [
        [datetime(2000, 1, 1), "PAGO EJEMPLO", "", -100],
        [datetime(2099, 12, 31), "PAGO EJEMPLO", "", -100],
        [datetime(2028, 2, 29), "PAGO EJEMPLO", "", -100],
    ]
    fechas = [m.fecha for m in leer_excel_movimientos(libro(filas))]
    assert fechas == [date(2000, 1, 1), date(2099, 12, 31), date(2028, 2, 29)]


def test_fecha_en_sistema_1904():
    wb = Workbook()
    wb.epoch = datetime(1904, 1, 1)
    ws = wb.active
    ws.title = "Hoja 1"
    ws.append(ENCABEZADOS)
    ws.append([datetime(2026, 9, 1), "PAGO EJEMPLO", "", -100])
    salida = io.BytesIO()
    wb.save(salida)
    assert leer_excel_movimientos(salida.getvalue())[0].fecha == date(2026, 9, 1)


# ---------------------------------------------------------------------------
# Descripción
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("descripcion", "texto"),
    [
        (None, "vacía o no es texto"),
        ("   ", "vacía o no es texto"),
        (12345, "vacía o no es texto"),
        ("X" * (eb.LONGITUD_MAXIMA_DESCRIPCION + 1), "demasiado larga"),
        ("PAGO\tEJEMPLO", "caracteres de control"),
    ],
)
def test_descripcion_invalida(descripcion, texto):
    rechazo(libro([[datetime(2026, 9, 1), descripcion, "", -100]]), "Fila 2", texto)


def test_descripcion_en_el_limite():
    texto = "Y" * eb.LONGITUD_MAXIMA_DESCRIPCION
    assert leer_excel_movimientos(libro([[datetime(2026, 9, 1), texto, "", -1]]))[0].descripcion == texto


# ---------------------------------------------------------------------------
# Estructura que no coincide
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "encabezados",
    [
        ["Fecha", "Descripcion", "Referencia", "Valor"],  # sin tilde
        ["fecha", "Descripción", "Referencia", "Valor"],  # minúscula
        ["Fecha", "Referencia", "Descripción", "Valor"],  # otro orden
        ["Fecha", "Descripción", "Valor"],  # falta una columna
        ["Fecha", "Descripción", "Referencia", "Valor", "Saldo"],  # sobra una
        ["Fecha", "Descripción", "Referencia", "Monto"],
        [],
    ],
)
def test_encabezado_distinto(encabezados):
    contenido = libro(encabezados=encabezados)
    motivo = rechazo(contenido)
    assert "encabezados" in motivo or "fuera de las 4 columnas" in motivo


def test_encabezados_en_otra_fila():
    rechazo(libro(fila_encabezados=2), "fila 1")
    rechazo(libro(fila_encabezados=2, antes=["Movimientos de la cuenta"]), "fila 1")


def test_hoja_con_otro_nombre():
    rechazo(libro(hoja="Hoja1"), "una sola hoja", "Hoja 1")
    rechazo(libro(hoja="Movimientos"), "una sola hoja", "Hoja 1")
    rechazo(libro(hoja="hoja 1"), "una sola hoja")


def test_hoja_faltante_por_tener_otra_hoja_extra():
    rechazo(libro(extra_hojas=["Resumen"]), "una sola hoja")


def test_datos_fuera_de_las_columnas():
    filas = [[datetime(2026, 9, 1), "PAGO EJEMPLO", "", -100, "SALDO"]]
    rechazo(libro(filas), "Fila 2", "fuera de las 4 columnas")


def test_dato_en_una_columna_lejana():
    wb = Workbook()
    ws = wb.active
    ws.title = "Hoja 1"
    ws.append(ENCABEZADOS)
    ws.append([datetime(2026, 9, 1), "PAGO EJEMPLO", "", -100])
    ws["XFD2"] = "OCULTO"
    salida = io.BytesIO()
    wb.save(salida)
    rechazo(salida.getvalue(), "Fila 2", "fuera de las 4 columnas")


def test_fila_vacia_entre_movimientos():
    filas = [
        [datetime(2026, 9, 1), "PAGO EJEMPLO", "", -100],
        [],
        [datetime(2026, 9, 2), "PAGO EJEMPLO", "", -100],
    ]
    rechazo(libro(filas), "Fila 3", "fila vacía entre movimientos")


def test_fila_de_totales_al_final():
    filas = [[datetime(2026, 9, 1), "PAGO EJEMPLO", "", -100], [None, "TOTAL", None, -100]]
    rechazo(libro(filas), "Fila 3", "Fecha")


def test_demasiadas_filas():
    filas = [[datetime(2026, 9, 1), "PAGO EJEMPLO", "", -1]] * eb.FILAS_MAXIMAS
    rechazo(libro(filas), f"más de {eb.FILAS_MAXIMAS} filas")


def test_maximo_de_filas_permitido():
    filas = [[datetime(2026, 9, 1), "PAGO EJEMPLO", "", -1]] * (eb.FILAS_MAXIMAS - 1)
    assert len(leer_excel_movimientos(libro(filas))) == eb.FILAS_MAXIMAS - 1


def test_fila_muy_lejana_no_se_ignora():
    wb = Workbook()
    ws = wb.active
    ws.title = "Hoja 1"
    ws.append(ENCABEZADOS)
    ws.append([datetime(2026, 9, 1), "PAGO EJEMPLO", "", -100])
    ws["A1000000"] = "OCULTO"
    salida = io.BytesIO()
    wb.save(salida)
    rechazo(salida.getvalue(), "más de")


def test_dimensiones_falsas_no_disparan_millones_de_celdas():
    def dimension_gigante(xml):
        inicio = xml.index(b"<dimension")
        fin = xml.index(b"/>", inicio) + 2
        return xml[:inicio] + b'<dimension ref="A1:XFD1048576"/>' + xml[fin:]

    contenido = reescribir(libro(), cambiar={HOJA_XML: dimension_gigante})
    t0 = reloj.monotonic()
    assert len(leer_excel_movimientos(contenido)) == len(FILAS_EJEMPLO)
    assert reloj.monotonic() - t0 < 5


# ---------------------------------------------------------------------------
# Formato del archivo y seguridad
# ---------------------------------------------------------------------------


def test_archivo_enorme_se_rechaza_antes_de_abrirlo(monkeypatch):
    def no_abrir(*_a, **_k):
        raise AssertionError("no debía abrir el archivo")

    monkeypatch.setattr(eb.zipfile, "ZipFile", no_abrir)
    contenido = b"PK\x03\x04" + b"\x00" * eb.TAMANO_MAXIMO_BYTES
    rechazo(contenido, "demasiado grande")


@pytest.mark.parametrize(
    "contenido",
    [
        b"",
        b"Fecha;Descripcion;Referencia;Valor\n01/09/2026;PAGO;;-100\n",  # CSV
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100,  # .xls antiguo (OLE)
        b"%PDF-1.7\n",
    ],
)
def test_no_es_xlsx(contenido):
    rechazo(contenido, "no es un Excel .xlsx")


def test_no_son_bytes():
    rechazo("texto", "No se recibió")


def test_zip_danado():
    rechazo(b"PK\x03\x04" + b"basura" * 50, "dañado")
    rechazo(libro()[:-200], "dañado")


@pytest.mark.parametrize("nombre", ["movimientos.xlsm", "movimientos.xls", "movimientos.csv",
                                    "movimientos.xlsx.exe", "movimientos"])
def test_extension_distinta_de_xlsx(nombre):
    motivo = rechazo(libro(), "Solo se aceptan archivos .xlsx", nombre_archivo=nombre)
    assert nombre not in motivo


def test_xlsm_por_tipo_de_contenido():
    def a_xlsm(xml):
        return xml.replace(
            b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
            b"application/vnd.ms-excel.sheet.macroEnabled.main+xml",
        )

    rechazo(reescribir(libro(), cambiar={"[Content_Types].xml": a_xlsm}), ".xlsm")


def test_xlsm_con_proyecto_de_macros():
    contenido = reescribir(libro(), agregar={"xl/vbaProject.bin": b"\x00macro inventada"})
    rechazo(contenido, "macros")


def test_vinculos_externos():
    contenido = reescribir(libro(), agregar={"xl/externalLinks/externalLink1.xml": b"<x/>"})
    rechazo(contenido, "vínculos externos")


def test_sin_tipos_de_contenido():
    rechazo(reescribir(libro(), quitar=("[Content_Types].xml",)), "no es un libro .xlsx normal")


def test_formula_se_rechaza_aunque_tenga_valor_guardado():
    filas = [[datetime(2026, 9, 1), "PAGO EJEMPLO", "", "=-100-1"]]
    rechazo(libro(filas), "fórmulas")


def test_formula_con_prefijo_de_espacio_de_nombres():
    def con_formula(xml):
        return xml.replace(b"<v>-100</v>", b'<x:f xmlns:x="urn:ejemplo">1+1</x:f><v>-100</v>', 1)

    filas = [[datetime(2026, 9, 1), "PAGO EJEMPLO", "", -100]]
    contenido = reescribir(libro(filas), cambiar={HOJA_XML: con_formula})
    rechazo(contenido, "fórmulas")


@pytest.mark.parametrize(
    "declaracion",
    [
        b'<!DOCTYPE x [<!ENTITY a "aaaaaaaaaa">]>',
        b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>',
    ],
)
def test_declaraciones_xml_se_rechazan(declaracion):
    def con_doctype(xml):
        return b'<?xml version="1.0" encoding="UTF-8"?>' + declaracion + xml

    contenido = reescribir(libro(), cambiar={HOJA_XML: con_doctype})
    rechazo(contenido, "declaraciones XML")


def test_xml_en_utf16_se_rechaza():
    def a_utf16(xml):
        return ('<?xml version="1.0" encoding="UTF-16"?>' + xml.decode("utf-8")).encode("utf-16")

    contenido = reescribir(libro(), cambiar={HOJA_XML: a_utf16})
    rechazo(contenido, "codificación")


def test_bomba_zip_por_tamano_declarado():
    relleno = b" " * (eb.DESCOMPRIMIDO_MAXIMO_BYTES + 1)
    contenido = reescribir(libro(), agregar={"docProps/relleno.xml": relleno})
    assert len(contenido) < eb.TAMANO_MAXIMO_BYTES  # comprime muy bien
    rechazo(contenido, "descomprimido es demasiado grande")


def test_bomba_zip_por_tamano_real(monkeypatch):
    # Se cuenta lo descomprimido de verdad, parte por parte: con un presupuesto
    # menor que el libro, se rechaza aunque cada parte sea pequeña.
    contenido = libro()
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        total = sum(i.file_size for i in z.infolist())
    monkeypatch.setattr(eb, "DESCOMPRIMIDO_MAXIMO_BYTES", total - 1)
    rechazo(contenido, "descomprimido es demasiado grande")


def test_demasiadas_partes():
    extra = {f"docProps/extra{i}.xml": b"<x/>" for i in range(eb.PARTES_MAXIMAS)}
    rechazo(reescribir(libro(), agregar=extra), "demasiadas partes")


def test_mensajes_sin_datos_del_archivo():
    filas = [[datetime(2026, 9, 1), "COMERCIO SECRETO EJEMPLO", "3000005678", "-5,000.00"]]
    motivo = rechazo(libro(filas), "Fila 2", nombre_archivo="reporte_inventado.xlsx")
    for dato in ("COMERCIO SECRETO", "3000005678", "5,000", "reporte_inventado"):
        assert dato not in motivo


def test_el_error_es_value_error_y_no_encadena_la_causa():
    with pytest.raises(ValueError) as error:
        leer_excel_movimientos(b"PK\x03\x04" + b"basura" * 50)
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__


# ---------------------------------------------------------------------------
# Partes con extensiones distintas de .xml y .rels (ronda 1 de revisión)
# ---------------------------------------------------------------------------


def hoja_con_otra_extension(contenido, extension, cambiar_hoja=None):
    """Mueve la hoja a xl/worksheets/sheet1.<extension> y ajusta rels y tipos."""
    nueva = f"xl/worksheets/sheet1.{extension}"
    viejo = b"worksheets/sheet1.xml"
    nuevo = f"worksheets/sheet1.{extension}".encode()
    cambiar = {
        "[Content_Types].xml": lambda x: x.replace(viejo, nuevo),
        "xl/_rels/workbook.xml.rels": lambda x: x.replace(viejo, nuevo),
    }
    if cambiar_hoja:
        cambiar[HOJA_XML] = cambiar_hoja
    return reescribir(contenido, cambiar=cambiar, renombrar={HOJA_XML: nueva})


def test_hoja_renombrada_con_formula_se_rechaza():
    # Caso del revisor: la hoja como .dat, con rels y tipos ajustados y una
    # fórmula adentro. openpyxl la leería igual; debe rechazarse.
    def con_formula(xml):
        return xml.replace(b"<v>-100</v>", b"<f>1+1</f><v>-100</v>", 1)

    filas = [[datetime(2026, 9, 1), "PAGO EJEMPLO", "", -100]]
    contenido = hoja_con_otra_extension(libro(filas), "dat", con_formula)
    rechazo(contenido, "tipo no permitido")


@pytest.mark.parametrize("extension", ["dat", "bin", "txt", "XML.bak"])
def test_hoja_renombrada_sin_formula_tambien_se_rechaza(extension):
    rechazo(hoja_con_otra_extension(libro(), extension), "tipo no permitido")


def test_hoja_renombrada_con_doctype_se_rechaza():
    def con_doctype(xml):
        return b'<!DOCTYPE x [<!ENTITY a "aaaa">]>' + xml

    rechazo(hoja_con_otra_extension(libro(), "dat", con_doctype), "tipo no permitido")


@pytest.mark.parametrize("nombre", ["docProps/extra", "xl/printerSettings/printerSettings1.bin",
                                    "xl/media/datos.dat"])
def test_parte_no_xml_se_rechaza(nombre):
    rechazo(reescribir(libro(), agregar={nombre: b"<f>1+1</f>"}), "tipo no permitido")


@pytest.mark.parametrize(
    ("nombre", "datos"),
    [
        ("xl/media/image1.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 40),
        ("xl/media/image2.jpeg", b"\xff\xd8\xff\xe0" + b"\x00" * 40),
        ("xl/media/image3.JPG", b"\xff\xd8\xff\xe0" + b"\x00" * 40),
        ("xl/media/image4.gif", b"GIF89a" + b"\x00" * 40),
    ],
)
def test_imagen_con_firma_real_se_acepta(nombre, datos):
    contenido = reescribir(libro(), agregar={nombre: datos})
    assert len(leer_excel_movimientos(contenido)) == len(FILAS_EJEMPLO)


@pytest.mark.parametrize("datos", [b"<f>1+1</f>", b"<worksheet/>", b""])
def test_imagen_falsa_se_rechaza(datos):
    contenido = reescribir(libro(), agregar={"xl/media/image1.png": datos})
    rechazo(contenido, "imagen que no corresponde")


def test_hoja_disfrazada_de_imagen_se_rechaza():
    # Una "imagen" que es XML no tiene la firma de la imagen.
    rechazo(hoja_con_otra_extension(libro(), "png"), "imagen que no corresponde")


# ---------------------------------------------------------------------------
# Estructura confirmada: hora 05:00, dobles espacios y el Excel de ejemplo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hora", [(0, 0), (5, 0)])
def test_fecha_con_hora_permitida_usa_solo_el_dia(hora):
    filas = [[datetime(2026, 8, 30, *hora), "ABONO INTERESES AHORROS", None, 1.35]]
    assert leer_excel_movimientos(libro(filas))[0].fecha == date(2026, 8, 30)


def test_dobles_espacios_internos_se_conservan():
    filas = [[datetime(2026, 8, 3, 5), "COMPRA EN  TIENDA EJEMPLO", None, -25900]]
    assert leer_excel_movimientos(libro(filas))[0].descripcion == "COMPRA EN  TIENDA EJEMPLO"


def test_excel_de_ejemplo_inventado_completo():
    """Excel INVENTADO con la forma exacta del reporte del banco, generado por
    código (tests/soporte/excel_inventado.py): desde D43 no se suben .xlsx."""
    contenido = excel_inventado.generar_excel()
    movimientos = leer_excel_movimientos(contenido, nombre_archivo="Movimientos.xlsx")

    assert len(movimientos) == 63
    # Suma calculada aparte, con Decimal sobre el texto de las celdas del XML.
    assert sum(m.monto_centavos for m in movimientos) == -33180181 == excel_inventado.TOTAL_CENTAVOS
    assert sum(m.monto_centavos for m in movimientos if m.monto_centavos < 0) == -74183000
    assert sum(m.monto_centavos for m in movimientos if m.monto_centavos > 0) == 41002819
    assert all(type(m.monto_centavos) is int for m in movimientos)

    assert movimientos[0] == MovimientoExcel(date(2026, 8, 30), 135, "ABONO INTERESES AHORROS")
    assert movimientos[6] == MovimientoExcel(date(2026, 8, 27), -620000, "TRANSFERENCIAS A NEQUI", "*0004")
    assert movimientos[3] == MovimientoExcel(date(2026, 8, 28), -710000, "COBRO VIAJE TRANSPORTE MASIVO")
    assert movimientos[-1] == MovimientoExcel(date(2026, 8, 3), -2590000, "COMPRA EN  TIENDA EJEMPLO")
    assert min(m.fecha for m in movimientos) == date(2026, 8, 3)
    assert max(m.fecha for m in movimientos) == date(2026, 8, 30)

    # De la Referencia solo los últimos 4 dígitos (D37), nunca el número completo.
    assert sorted(m.referencia for m in movimientos if m.referencia) == [
        "*0001", "*0001", "*0002", "*0002", "*0003", "*0004"]
    texto = repr(movimientos)
    for referencia in ("3000000001", "3000000002", "3000000003", "3000000004",
                       "00000000001", "00000000002"):
        assert referencia not in texto
