"""API de persistencia: esquema, conexiones y fronteras; nunca migra al abrir."""
from .esquema import (
    CATEGORIAS_FIJAS,
    CLASE_GASTO,
    CLASE_INGRESO,
    CLASES_CATEGORIA,
    CATEGORIAS_INICIALES,
    AhoraIso,
    REFERENCIA_VALIDA,
    metadata,
    categorias,
    movimientos,
    reglas,
    configuracion_saldo,
    correos_no_reconocidos,
    ESTADOS_SINCRONIZACION,
    ORIGENES_SINCRONIZACION,
    CODIGOS_ERROR_SINCRONIZACION,
    CONTADORES_SINCRONIZACION,
    estado_sincronizacion,
    importaciones,
    ACCIONES_IMPORTACION,
    cambios_importacion,
    preguntas_conciliacion,
    candidatos_pregunta,
    reversiones_importacion,
    descartes_movimientos,
)
from .conexion import (
    ESPERA_POR_DEFECTO,
    crear_motor,
    conectar,
    ruta_de,
)
from .transacciones import (
    en_transaccion,
    transaccion,
    lectura_consistente,
    insertar,
)
from .revision import (
    BaseNoMigrada,
    revision_actual,
)
