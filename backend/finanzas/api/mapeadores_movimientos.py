"""Adaptación HTTP: mapeadores_movimientos."""
from __future__ import annotations
from sqlalchemy import Connection
from finanzas.modulos.categorias import publico as categorizacion
from finanzas.flujos import reporte
from finanzas.bootstrap.descartes import componer_descartes
from finanzas.api import modelos as m


TIPO_POR_CAMPO = {campo: tipo for tipo, campo in categorizacion.CAMPO_POR_TIPO.items()}



def _condiciones(campo: str, texto: str | None, monto_centavos: int | None) -> dict:
    """Los campos comunes de una regla en la API (``texto`` ``null`` si no mira el texto)."""
    return {
        "tipo_movimiento": TIPO_POR_CAMPO[campo],
        "campo": campo,
        "texto": texto,
        "monto_centavos": monto_centavos,
        "condiciones": categorizacion.condiciones_de(texto, monto_centavos),
    }


def _regla_aplicada(
    regla_id: int | None, campo: str | None, texto: str | None, monto_centavos: int | None,
    modo_texto: str = "exacta", origen_regla: str = "todos", texto_visible: str | None = None
) -> m.ReglaAplicada | None:
    if regla_id is None or campo is None or (texto is None and monto_centavos is None):
        return None
    return m.ReglaAplicada(
        id=regla_id,
        **_condiciones(campo, texto, monto_centavos),
        frase=categorizacion.frase_condiciones(campo, texto_visible or texto, monto_centavos, modo_texto),
        modo_texto=modo_texto, origen_regla=origen_regla,
    )


def _regla_posible(tipo: str, descripcion: str) -> m.ReglaPosible | None:
    posible = categorizacion.regla_posible(tipo, descripcion)
    return None if posible is None else m.ReglaPosible(campo=posible[0], texto=posible[1])


def _reglas_posibles(tipo: str, descripcion: str, monto_centavos: int) -> list[m.OpcionRegla]:
    return [
        m.OpcionRegla(
            **_condiciones(p.campo, p.texto, p.monto_centavos),
            frase=categorizacion.frase_condiciones(p.campo, p.texto, p.monto_centavos),
        )
        for p in categorizacion.reglas_posibles(tipo, descripcion, monto_centavos)
    ]


def _origen_categoria(mov: reporte.MovimientoReporte) -> str | None:
    if mov.categoria_id is None:
        return None
    return mov.origen_categoria or "desconocido"


def _movimiento(mov: reporte.MovimientoReporte, conn: Connection) -> m.Movimiento:
    """Un movimiento con el esquema de la API (lista del mes y bandeja)."""
    return m.Movimiento(**componer_descartes(conn).elegibilidad(mov.id), id=mov.id, fecha_hora=mov.fecha_hora, tipo=mov.tipo, descripcion=mov.descripcion, monto_centavos=mov.monto_centavos, es_gasto=mov.es_gasto, categoria=m.Categoria(id=mov.categoria_id, nombre=mov.categoria, clase=mov.categoria_clase, color=mov.categoria_color, icono=mov.categoria_icono) if mov.categoria_id is not None else None, origen=mov.origen, origen_categoria=_origen_categoria(mov), regla=_regla_aplicada(mov.regla_id, mov.regla_campo, mov.regla_texto, mov.regla_monto_centavos, mov.regla_modo_texto, mov.regla_origen_regla, mov.regla_texto_visible), pendiente=mov.pendiente, categorizable=categorizacion.es_categorizable(mov.tipo), clase_categoria=categorizacion.clase_para_tipo(mov.tipo), regla_posible=_regla_posible(mov.tipo, mov.descripcion), reglas_posibles=_reglas_posibles(mov.tipo, mov.descripcion, mov.monto_centavos))


def _grupo(grupo: categorizacion.GrupoPendientes) -> m.GrupoPendientes:
    regla = grupo.regla
    return m.GrupoPendientes(
        clave=grupo.clave,
        tipo=grupo.tipo,
        descripcion=grupo.descripcion,
        clase_categoria=grupo.clase_categoria,
        es_gasto=reporte.es_gasto(grupo.tipo),
        cuantos=grupo.cuantos,
        suma_centavos=grupo.suma_centavos,
        ids=list(grupo.ids),
        regla=m.OpcionRegla(
            **_condiciones(regla.campo, regla.texto, regla.monto_centavos),
            frase=categorizacion.frase_condiciones(regla.campo, regla.texto, regla.monto_centavos),
        ),
    )
