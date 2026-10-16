"""Adaptación HTTP: categorias."""
from __future__ import annotations
from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import Connection
from dataclasses import asdict
from finanzas.modulos.categorias import publico as categorizacion
from finanzas.flujos import reporte
from finanzas.bootstrap.categorias import componer_administracion_categorias, componer_administracion_reglas, componer_asignacion_categorias, componer_catalogo_categorias
from finanzas.api import modelos as m
from finanzas.api.dependencias import conexion, usuario_actual
from finanzas.modulos.categorias.contratos import ConsultaCategorias
from finanzas.api.comun import IdCategoria, IdMovimiento, IdRegla, _CSRF, _ERROR_400, _ERROR_404, _ERROR_415, _datos_opcionales, _error
from finanzas.api.consultas_mes import _leer_mes
from finanzas.api.mapeadores_deshacer import _deshacer
from finanzas.api.mapeadores_movimientos import _condiciones, _regla_aplicada
from finanzas.api.comun import crear_router

router = crear_router()


def _categorizado(conn: Connection, asignacion: categorizacion.Asignacion, recordar: bool) -> m.Categorizado:
    regla = None
    if asignacion.regla_id is not None:
        fila = _datos_opcionales(componer_catalogo_categorias(conn).regla(asignacion.regla_id))
        if fila is not None:  # la borraron justo después: se informa sin ella
            regla = _regla_aplicada(fila["id"], fila["campo"], fila["texto"], fila["monto_centavos"], fila["modo_texto"], fila["origen_regla"], fila["texto_visible"])
    return m.Categorizado(categorizados=asignacion.total, regla_guardada=recordar, regla=regla)


@router.post(
    "/movimientos/categorizar-grupo",
    response_model=m.Categorizado,
    dependencies=_CSRF,
    responses={**_ERROR_400, **_ERROR_415},
    summary="Categorizar un grupo de pendientes iguales",
)
def categorizar_grupo(
    datos: m.CategorizarGrupoEntrada,
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.Categorizado:
    """Ítem 38: categoriza juntos los ``ids`` de un grupo de ``grupos`` y guarda su regla, todo o nada.

    Solo se tocan los ``ids`` que siguen pendientes y siguen siendo del grupo
    (``clave``); los demás no cuentan. Quedan con ``origen_categoria``
    ``manual``. La regla por texto del grupo se guarda (si ya había una igual,
    pasa a esta categoría) y alcanza también a otros pendientes iguales que
    hayan llegado después (con origen ``regla``). ``categorizados`` cuenta
    todos. Si ninguno seguía pendiente, no cambia nada: ``categorizados`` 0,
    ``regla_guardada`` ``false``. 400 si la clave no es válida o la categoría
    no existe o es de otra clase.
    """
    try:
        asignacion = componer_asignacion_categorias(conn).categorizar_grupo(datos.clave, datos.ids, datos.categoria_id, datos.modo_regla)
    except categorizacion.ErrorCategorizacion as error:
        raise _error(400, str(error)) from None
    return _categorizado(conn, asignacion, asignacion.regla_id is not None)


@router.put(
    "/movimientos/{movimiento_id}/categoria",
    response_model=m.Categorizado,
    dependencies=_CSRF,
    responses={**_ERROR_400, **_ERROR_404, **_ERROR_415},
    summary="Categorizar un movimiento",
)
def categorizar(
    datos: m.CategorizarEntrada,
    movimiento_id: int = IdMovimiento,
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.Categorizado:
    """Asigna o corrige la categoría en un paso; con ``recordar``, además guarda la regla.

    La categoría debe ser de la ``clase_categoria`` del movimiento (400 si
    no): un gasto, de gasto; un ingreso, de ingreso (regla por quien envía).
    El movimiento queda categorizado ``manual`` (también si lo había
    categorizado una regla). Con ``recordar``, en la misma llamada se guarda
    la regla y se aplica a los pendientes para los que esa regla es la que
    gana. ``condiciones`` (ítem 17) elige qué regla crear: ``texto`` (por
    omisión), ``monto`` o ``texto_y_monto``; solo con ``recordar: true`` (400
    si no). Para crear la regla después de categorizar, se repite la llamada
    con la misma categoría y ``recordar: true``.
    """
    if datos.condiciones is not None and not datos.recordar:
        raise _error(400, "Elegir la regla solo tiene sentido si se pide recordarla.")
    try:
        asignacion = componer_asignacion_categorias(conn).asignar(movimiento_id, datos.categoria_id, recordar=datos.recordar, condiciones=datos.condiciones or categorizacion.CONDICION_TEXTO)
    except categorizacion.MovimientoNoEncontrado as error:
        raise _error(404, str(error)) from None
    except categorizacion.ErrorCategorizacion as error:
        raise _error(400, str(error)) from None
    return _categorizado(conn, asignacion, datos.recordar)


def _categoria(fila) -> m.Categoria:
    return m.Categoria(
        id=fila["id"], nombre=fila["nombre"], clase=fila["clase"], color=fila["color"], icono=fila["icono"]
    )


def _error_categoria(error: categorizacion.ErrorCategorizacion) -> HTTPException:
    if isinstance(error, categorizacion.CategoriaNoEncontrada):
        return _error(404, str(error))
    return _error(400, str(error))


def _consulta_categorias(request: Request, conn: Connection = Depends(conexion)) -> ConsultaCategorias:
    return request.app.state.consulta_categorias(conn)


@router.get("/categorias", response_model=m.ListaCategorias, responses=_ERROR_400, summary="Categorías")
def ver_categorias(
    clase: m.ClaseCategoria | None = Query(None, description="Solo las de esta clase; sin ella, todas."),
    mes: str | None = Query(
        None,
        description="aaaa-mm del que se cuentan los movimientos (movimientos_mes); sin él, el mes actual en Colombia.",
        max_length=7,
    ),
    usuario: m.Usuario = Depends(usuario_actual),
    consulta: ConsultaCategorias = Depends(_consulta_categorias),
) -> m.ListaCategorias:
    """Las categorías, primero las de gasto y luego las de ingreso, con cuántos movimientos y reglas tienen."""
    anio, numero = _leer_mes(mes)
    desde, hasta = reporte.limites_del_mes(anio, numero)
    filas = consulta.ejecutar(desde, hasta, clase=clase)
    return m.ListaCategorias(
        mes=reporte.texto_mes(anio, numero),
        categorias=[
            m.CategoriaConUso(
                id=fila.categoria.id, nombre=fila.categoria.nombre, clase=fila.categoria.clase,
                color=fila.categoria.color, icono=fila.categoria.icono,
                movimientos_mes=fila.categoria.movimientos_mes,
                movimientos_total=fila.categoria.movimientos_total,
                reglas=fila.categoria.reglas,
                se_puede_deshacer_borrado=fila.se_puede_deshacer_borrado,
            )
            for fila in filas
        ],
    )


@router.post(
    "/categorias",
    status_code=201,
    response_model=m.Categoria,
    dependencies=_CSRF,
    responses={**_ERROR_400, **_ERROR_415},
    summary="Crear una categoría",
)
def crear_categoria(
    datos: m.CategoriaEntrada,
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.Categoria:
    """Nombre único en su clase (sin importar mayúsculas ni espacios de más); el par color + ícono, único entre todas."""
    try:
        nuevo_id = componer_administracion_categorias(conn).crear(datos.nombre, datos.clase, datos.color, datos.icono)
    except categorizacion.ErrorCategorizacion as error:
        raise _error_categoria(error) from None
    return _categoria(_datos_opcionales(componer_catalogo_categorias(conn).categoria(nuevo_id)))


@router.patch(
    "/categorias/{categoria_id}",
    response_model=m.Categoria,
    dependencies=_CSRF,
    responses={**_ERROR_400, **_ERROR_404, **_ERROR_415},
    summary="Renombrar una categoría o cambiar su color o su ícono",
)
def editar_categoria(
    datos: m.EditarCategoriaEntrada,
    categoria_id: int = IdCategoria,
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.Categoria:
    """Solo cambia lo que se envía (al menos un campo). Sus movimientos y reglas la siguen teniendo."""
    try:
        componer_administracion_categorias(conn).editar(categoria_id, nombre=datos.nombre, color=datos.color, icono=datos.icono)
    except categorizacion.ErrorCategorizacion as error:
        raise _error_categoria(error) from None
    fila = _datos_opcionales(componer_catalogo_categorias(conn).categoria(categoria_id))
    if fila is None:  # la borraron justo después
        raise _error(404, "La categoría no existe.")
    return _categoria(fila)


@router.delete(
    "/categorias/{categoria_id}",
    response_model=m.CategoriaBorrada,
    dependencies=_CSRF,
    responses={**_ERROR_400, **_ERROR_404},
    summary="Borrar una categoría",
)
def borrar_categoria(
    request: Request,
    categoria_id: int = IdCategoria,
    mover_a: int | None = Query(
        None,
        ge=1,
        le=m.MAXIMO_ID,
        description=(
            "Id de la categoría (de la misma clase) a la que pasan sus movimientos y reglas. "
            "Obligatorio si tiene alguno."
        ),
    ),
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.CategoriaBorrada:
    """Borra la categoría y pasa sus movimientos y reglas a ``mover_a``, todo o nada.

    400 si ``mover_a`` falta (y hay algo que pasar), es la misma, no existe o
    es de otra clase, o si es la última categoría de su clase. Los
    movimientos conservan cómo se categorizaron (a mano o por qué regla).

    ``deshacer`` (ítem 38): solo si no tenía movimientos ni reglas
    (``se_puede_deshacer_borrado``); con ellos, el borrado no se deshace.
    """
    try:
        borrada = componer_administracion_categorias(conn).borrar(categoria_id, mover_a)
    except categorizacion.ErrorCategorizacion as error:
        raise _error_categoria(error) from None
    destino = None if borrada.destino_id is None else _datos_opcionales(componer_catalogo_categorias(conn).categoria(borrada.destino_id))
    return m.CategoriaBorrada(
        movimientos_movidos=borrada.movimientos,
        reglas_movidas=borrada.reglas,
        destino=None if destino is None else _categoria(destino),
        deshacer=None if borrada.copia is None else _deshacer(request, borrada.copia),
    )


@router.get("/reglas", response_model=m.ListaReglas, summary="Reglas recordadas")
def ver_reglas(
    usuario: m.Usuario = Depends(usuario_actual), conn: Connection = Depends(conexion)
) -> m.ListaReglas:
    """Todas las reglas, de gasto y de ingreso, con su categoría y la regla en palabras (``frase``)."""
    return m.ListaReglas(reglas=[m.Regla(id=fila['id'], modo_texto=fila['modo_texto'], origen_regla=fila['origen_regla'], **_condiciones(fila['campo'], fila['texto'], fila['monto_centavos']), categoria=m.Categoria(id=fila['categoria_id'], nombre=fila['categoria'], clase=fila['categoria_clase'], color=fila['categoria_color'], icono=fila['categoria_icono']), frase=categorizacion.frase_regla(fila['campo'], fila['texto_visible'] or fila['texto'], fila['categoria'], fila['monto_centavos'], fila['modo_texto'])) for fila in [asdict(fila) for fila in componer_catalogo_categorias(conn).reglas()]])


@router.delete(
    "/reglas/{regla_id}",
    response_model=m.ReglaBorrada,
    dependencies=_CSRF,
    responses=_ERROR_404,
    summary="Borrar una regla",
)
def borrar_regla(
    request: Request,
    regla_id: int = IdRegla,
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.ReglaBorrada:
    """Los movimientos que la regla ya categorizó conservan su categoría.

    Siguen con ``origen_categoria`` ``regla``, pero con ``regla`` ``null``.
    Desde el ítem 38 responde 200 con ``deshacer`` (antes, 204 sin cuerpo):
    deshacerlo la vuelve a crear igual y esos movimientos le vuelven a apuntar.
    """
    try:
        copia = componer_administracion_reglas(conn).borrar(regla_id)
    except categorizacion.ReglaNoEncontrada as error:
        raise _error(404, str(error)) from None
    return m.ReglaBorrada(id=regla_id, deshacer=_deshacer(request, copia))
