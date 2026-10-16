"""Persistencia del reporte; participante de la conexión prestada, sin commits.

Los colaboradores se reciben del propietario de la composición.
"""
from __future__ import annotations
from collections.abc import Sequence
from datetime import date, timedelta
from sqlalchemy import Connection, text
from finanzas.infraestructura import persistencia as db
from .colaboradores import ColaboradoresImportacion
from . import elecciones_sqlite as elecciones_banco
from finanzas.infraestructura.esquema_compatible import columnas as _columnas
from finanzas.modulos.movimientos.publico import MovimientoNuevo
from . import motor as c
from .contratos import (Conteos, EstadoParaConciliar, ErrorConciliacion, SinConfiguracion, MENSAJE_CANDIDATO_USADO)


def _fecha(valor: object) -> date:
    return date.fromisoformat(str(valor)[:10])


def _reservas_descartes(conn: Connection, reservados: set[int], *, colaboradores: ColaboradoresImportacion) -> list[c.ReservaDescarte]:
    """Compatibilidad con bases históricas y adaptación de datos primitivos."""
    if not _columnas(conn, "descartes_movimientos"):
        return []
    resultado = []
    for r in colaboradores.descartes.listar_reservas():
        m, b = r["movimiento"], r["banco"]
        movimiento = c.MovimientoApp(
            id=m["id"], fecha=_fecha(m["fecha_hora"]), tipo=m["tipo"], monto_centavos=m["monto_centavos"],
            descripcion=m["descripcion"] or "", origen=m["origen"], estado=m["estado"], referencia=m["referencia"],
            fecha_banco=None if m["fecha_banco"] is None else _fecha(m["fecha_banco"]),
            no_en_banco=bool(m["no_en_banco"]), reservado=m["id"] in reservados,
        )
        banco = None if b is None else c.FilaBanco(_fecha(b["fecha"]), b["monto_centavos"], "", b["referencia"])
        resultado.append(c.ReservaDescarte(movimiento, banco, r["gmail_id"]))
    return resultado


def _elecciones_banco(conn: Connection) -> list[c.EleccionBanco]:
    if "movimiento_elegido_id" not in _columnas(conn, "preguntas_conciliacion"):
        return []
    return [c.EleccionBanco(_fecha(d["fecha"]), d["monto_centavos"], d["referencia"],
                           d["ocurrencia_banco"], d["movimiento_elegido_id"])
            for d in elecciones_banco.listar_elecciones_banco(conn)]


def leer_estado(conn: Connection, filas: Sequence[c.FilaBanco], *, colaboradores: ColaboradoresImportacion) -> EstadoParaConciliar:
    """Lo que el motor necesita para estas filas. Solo lee.

    Movimientos (no ajustes) con fecha dentro de las del reporte ±1 día, o
    respaldados por una fila del banco de esas fechas. Lanza
    ``SinConfiguracion`` si no hay fecha de inicio.
    """
    fila = conn.execute(text("SELECT fecha_inicio FROM configuracion_saldo WHERE id = 1")).first()
    if fila is None:
        raise SinConfiguracion("Todavía no has configurado el saldo inicial ni la fecha de inicio.")
    fecha_inicio = _fecha(fila[0])
    columnas = _columnas(conn, "movimientos")
    con_0008 = "estado" in columnas

    def col(nombre: str, defecto: str = "NULL") -> str:
        return nombre if nombre in columnas else f"{defecto} AS {nombre}"

    movimientos: list[c.MovimientoApp] = []
    ajuste = None
    pendientes: list[c.PreguntaPendiente] = []
    reservados: set[int] = set()
    if con_0008:
        reservados = {
            int(f[0]) for f in conn.execute(text(
                "SELECT k.movimiento_id FROM candidatos_pregunta k "
                "JOIN preguntas_conciliacion p ON p.id = k.pregunta_id WHERE p.respuesta IS NULL"
            ))
        }
        pendientes = [
            c.PreguntaPendiente(int(f[0]), _fecha(f[1]), int(f[2]), f[3], f[4])
            for f in conn.execute(text(
                "SELECT id, fecha, monto_centavos, referencia, "
                + ("ocurrencia_banco" if "ocurrencia_banco" in _columnas(conn, "preguntas_conciliacion") else "NULL")
                + " FROM preguntas_conciliacion "
                "WHERE fuente = 'banco' AND respuesta IS NULL ORDER BY id"
            ))
        ]
    if filas:
        desde = min(f.fecha for f in filas) - timedelta(days=1)
        hasta = max(f.fecha for f in filas) + timedelta(days=1)
        consulta = (
            "SELECT id, fecha_hora, tipo, monto_centavos, descripcion, origen, "
            f"{col('estado')}, {col('referencia')}, {col('fecha_banco')}, {col('no_en_banco', '0')} "
            "FROM movimientos WHERE tipo <> 'ajuste' AND (substr(fecha_hora, 1, 10) BETWEEN :desde AND :hasta"
            + (" OR fecha_banco BETWEEN :desde AND :hasta" if con_0008 else "")
            + ")" + (" AND borrado_en IS NULL" if "borrado_en" in columnas else "") + " ORDER BY id"
        )
        for f in conn.execute(text(consulta), {"desde": desde.isoformat(), "hasta": hasta.isoformat()}):
            movimientos.append(c.MovimientoApp(
                id=int(f[0]), fecha=_fecha(f[1]), tipo=str(f[2]), monto_centavos=int(f[3]),
                descripcion=str(f[4] or ""), origen=str(f[5]), estado=f[6], referencia=f[7],
                fecha_banco=None if f[8] is None else _fecha(f[8]), no_en_banco=bool(f[9]),
                reservado=int(f[0]) in reservados,
            ))
    ultimo = conn.execute(text(
        "SELECT id, fecha_hora, monto_centavos FROM movimientos WHERE tipo = 'ajuste' "
        "ORDER BY fecha_hora DESC, id DESC LIMIT 1"
    )).first()
    if ultimo is not None:
        ajuste = c.AjusteApp(int(ultimo[0]), _fecha(ultimo[1]), int(ultimo[2]))
    return EstadoParaConciliar(fecha_inicio, movimientos, ajuste, pendientes,
                              _reservas_descartes(conn, reservados, colaboradores=colaboradores), _elecciones_banco(conn))


def _registrar_cambio(conn: Connection, importacion_id: int | None, movimiento_id: int, accion: str,
                      anterior=None) -> None:
    if importacion_id is None:
        return
    valores = {"monto_anterior": None, "estado_anterior": None, "no_en_banco_anterior": None,
               "fecha_banco_anterior": None, "referencia_anterior": None}
    if anterior is not None:
        valores.update(zip(valores, anterior))
    conn.execute(db.insertar(conn, db.cambios_importacion).values(
        importacion_id=importacion_id, movimiento_id=movimiento_id, accion=accion, **valores,
    ).on_conflict_do_nothing())


def _confirmar(conn: Connection, importacion_id: int | None, fila: c.FilaBanco, movimiento_id: int,
               corregir: bool, *, colaboradores: ColaboradoresImportacion) -> None:
    anterior = colaboradores.bancario.estado_actual(movimiento_id)
    colaboradores.bancario.confirmar(movimiento_id, fila.fecha.isoformat(), fila.referencia,
        abs(fila.monto_centavos), corregir)
    _registrar_cambio(conn, importacion_id, movimiento_id, "corregido" if corregir else "confirmado", anterior)


def _confirmar_descarte(conn: Connection, fila: c.FilaBanco, ident: int,
                       importacion_id: int | None = None, *, colaboradores: ColaboradoresImportacion) -> None:
    """Confirma la misma fila excluida; su efecto y el del ajuste son cero."""
    reserva = next((r for r in _reservas_descartes(conn, set(), colaboradores=colaboradores) if r.movimiento.id == ident), None)
    if reserva is None or not c._mismo_sentido(fila, reserva.movimiento) or c._destinos(fila, reserva.movimiento) == "distinto":
        raise ErrorConciliacion(MENSAJE_CANDIDATO_USADO)
    referencia = reserva.movimiento.referencia or fila.referencia
    estado = c.ESTADO_CONFIRMADO if reserva.gmail_id else c.ESTADO_SIN_AVISO
    anterior = colaboradores.bancario.estado_actual(ident)
    esperado = (abs(fila.monto_centavos), estado, 0, fila.fecha.isoformat(), referencia)
    if anterior == esperado:
        return
    if not colaboradores.bancario.confirmar_descartado(ident, abs(fila.monto_centavos), estado,
            fila.fecha.isoformat(), referencia):
        raise ErrorConciliacion(MENSAJE_CANDIDATO_USADO)
    colaboradores.descartes.actualizar_respaldo_banco( ident, fecha=fila.fecha,
                                      monto_centavos=fila.monto_centavos, referencia=referencia)
    _registrar_cambio(conn, importacion_id, ident,
                     "corregido" if anterior[0] != esperado[0] else "confirmado", anterior)


def _agregar(conn: Connection, importacion_id: int | None, fila: c.FilaBanco, *, colaboradores: ColaboradoresImportacion) -> int:
    nuevo = colaboradores.normalizado.registrar(MovimientoNuevo(
        fecha_hora=f"{fila.fecha.isoformat()}T00:00:00",
        monto_centavos=abs(fila.monto_centavos),
        tipo=c.tipo_de_fila(fila),
        descripcion=fila.descripcion,
        origen=c.ORIGEN_EXTRACTO,
        gmail_id=None,
        estado=c.ESTADO_SIN_AVISO,
        referencia=fila.referencia,
        fecha_banco=fila.fecha.isoformat(),
    ))
    _registrar_cambio(conn, importacion_id, nuevo, "agregado")
    return nuevo


def _reducir_ajuste(conn: Connection, importacion_id: int | None, ajuste_id: int, efecto: int, *, colaboradores: ColaboradoresImportacion) -> None:
    if not efecto:
        return
    anterior = colaboradores.bancario.estado_actual(ajuste_id)
    colaboradores.bancario.reducir_ajuste(ajuste_id, efecto)
    _registrar_cambio(conn, importacion_id, ajuste_id, "ajuste_reducido", anterior)


def _crear_pregunta(conn: Connection, importacion_id: int | None, pregunta: c.Pregunta,
                    ajuste_id: int | None) -> None:
    fila = pregunta.fila
    ocurrencia = {"ocurrencia_banco": pregunta.ocurrencia_banco} if "ocurrencia_banco" in _columnas(conn, "preguntas_conciliacion") else {}
    resultado = conn.execute(db.preguntas_conciliacion.insert().values(
        tipo=pregunta.tipo, fuente="banco", importacion_id=importacion_id,
        fecha=fila.fecha.isoformat(), monto_centavos=fila.monto_centavos,
        descripcion=fila.descripcion, referencia=fila.referencia,
        ajuste_id=ajuste_id if pregunta.tipo == c.PREGUNTA_YA_ESTABA else None,
        **ocurrencia,
    ))
    pregunta_id = int(resultado.inserted_primary_key[0])
    for movimiento_id in pregunta.candidatos:
        conn.execute(db.candidatos_pregunta.insert().values(pregunta_id=pregunta_id, movimiento_id=movimiento_id))


class ReportesSQLite:
    def __init__(self, conn: Connection, *, colaboradores: ColaboradoresImportacion):
        self._colaboradores = colaboradores
        self._conn = conn

    def leer_estado(self, filas: Sequence[c.FilaBanco]) -> EstadoParaConciliar:
        return leer_estado(self._conn, filas, colaboradores=self._colaboradores)

    def crear_resumen(self, plan: c.Plan, resumen: Conteos, sin_formato: int) -> int:
        return int(self._conn.execute(db.importaciones.insert().values(
            desde=None if plan.desde is None else plan.desde.isoformat(),
            hasta=None if plan.hasta is None else plan.hasta.isoformat(),
            filas=resumen.filas, ya_estaban=resumen.ya_estaban + resumen.ya_preguntadas,
            agregados=resumen.agregados, confirmados=resumen.confirmados,
            corregidos=resumen.corregidos, preguntas=resumen.preguntas,
            no_en_banco=resumen.no_en_banco, anteriores=resumen.anteriores,
            sin_formato=sin_formato,
        )).inserted_primary_key[0])

    def confirmar(self, importacion_id: int, fila: c.FilaBanco, movimiento_id: int, corregir: bool) -> None:
        _confirmar(self._conn, importacion_id, fila, movimiento_id, corregir, colaboradores=self._colaboradores)

    def confirmar_descarte(self, importacion_id: int, fila: c.FilaBanco, movimiento_id: int) -> None:
        _confirmar_descarte(self._conn, fila, movimiento_id, importacion_id, colaboradores=self._colaboradores)

    def agregar(self, importacion_id: int, fila: c.FilaBanco) -> int:
        return _agregar(self._conn, importacion_id, fila, colaboradores=self._colaboradores)

    def crear_pregunta(self, importacion_id: int, pregunta: c.Pregunta, ajuste_id: int | None) -> None:
        _crear_pregunta(self._conn, importacion_id, pregunta, ajuste_id)

    def marcar_ausencia(self, importacion_id: int, movimiento_id: int) -> None:
        anterior = self._colaboradores.bancario.estado_actual(movimiento_id)
        self._colaboradores.bancario.marcar_ausencia(movimiento_id)
        _registrar_cambio(self._conn, importacion_id, movimiento_id, "marcado", anterior)

    def reducir_ajuste(self, importacion_id: int, ajuste_id: int, efecto: int) -> None:
        _reducir_ajuste(self._conn, importacion_id, ajuste_id, efecto, colaboradores=self._colaboradores)
