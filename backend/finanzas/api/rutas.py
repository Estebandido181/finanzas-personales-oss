"""Composición de routers por capacidad y compatibilidad de imports anteriores."""
from fastapi import APIRouter
from finanzas.api.comun import logger, PREFIJO, RUTA_SESION, _ERRORES, _ERROR_400, _ERROR_404, _ERROR_409, _ERROR_415, _id_operacion, _CSRF, IdMovimiento, IdRegla, IdCategoria, _error, ParametroMes, _datos_opcionales
from finanzas.api.rutas_sesion import MENSAJE_LOGIN_FALLIDO
from finanzas.api.rutas_sesion import MENSAJE_BLOQUEO
from finanzas.api.rutas_sincronizacion import MENSAJE_SINCRONIZACION_EN_CURSO
from finanzas.api.rutas_sincronizacion import MENSAJE_NO_RECONOCIDO_INEXISTENTE
from finanzas.api.rutas_saldo import MENSAJE_TOKEN_INGRESO_INVALIDO
from finanzas.api.rutas_saldo import MENSAJE_INGRESO_REPETIDO
from finanzas.api.rutas_sincronizacion import MENSAJES_ERROR_SINCRONIZACION
from finanzas.api.mapeadores_movimientos import TIPO_POR_CAMPO
from finanzas.api.rutas_deshacer import MENSAJE_YA_NO_SE_PUEDE_DESHACER
from finanzas.api.rutas_sesion import (
    _revocar_bancarios,
    _ip_cliente,
    iniciar_sesion,
    ver_sesion,
    cerrar_sesion,
)
from finanzas.api.rutas_sesion import router as rutas_sesion
from finanzas.api.consultas_mes import (
    _leer_mes,
    _mes_vecino,
)
from finanzas.api.rutas_inicio import (
    ver_estado_inicio,
    ver_reporte,
)
from finanzas.api.rutas_inicio import router as rutas_inicio
from finanzas.api.mapeadores_movimientos import (
    _condiciones,
    _regla_aplicada,
    _regla_posible,
    _reglas_posibles,
    _origen_categoria,
    _movimiento,
    _grupo,
)
from finanzas.api.rutas_movimientos import (
    ver_movimientos,
    ver_sin_categorizar,
    ver_descartados,
    _cambiar_descarte,
    descartar_movimiento,
    restaurar_movimiento,
)
from finanzas.api.rutas_movimientos import router as rutas_movimientos
from finanzas.api.rutas_categorias import (
    _categorizado,
    categorizar_grupo,
    categorizar,
    _categoria,
    _error_categoria,
    _consulta_categorias,
    ver_categorias,
    crear_categoria,
    editar_categoria,
    borrar_categoria,
    ver_reglas,
    borrar_regla,
)
from finanzas.api.rutas_categorias import router as rutas_categorias
from finanzas.api.rutas_saldo import (
    _hora_iso,
    ver_saldo,
    configurar_saldo,
    registrar_ingreso,
    ajustar_saldo,
    borrar_ingreso,
)
from finanzas.api.rutas_saldo import router as rutas_saldo
from finanzas.api.mapeadores_deshacer import (
    _deshacer,
)
from finanzas.api.rutas_deshacer import (
    deshacer_borrado,
)
from finanzas.api.rutas_deshacer import router as rutas_deshacer
from finanzas.api.rutas_sincronizacion import (
    _resultado_sincronizacion,
    sincronizar_ahora,
    ver_sincronizacion,
    ver_no_reconocidos,
    _reprocesar,
    reprocesar_no_reconocidos,
    reprocesar_no_reconocido,
)
from finanzas.api.rutas_sincronizacion import router as rutas_sincronizacion

router = APIRouter()
router.include_router(rutas_sesion)
router.include_router(rutas_inicio)
router.include_router(rutas_movimientos)
router.include_router(rutas_categorias)
router.include_router(rutas_saldo)
router.include_router(rutas_deshacer)
router.include_router(rutas_sincronizacion)
