"""Composición de flujos usando la conexión prestada por la petición."""
from finanzas.bootstrap.categorias import (
    componer_catalogo_categorias, componer_administracion_categorias, componer_administracion_reglas,
)
from finanzas.bootstrap.importaciones import componer_gestion_importaciones
from finanzas.bootstrap.saldo import componer_saldo
from finanzas.flujos import inicio, deshacer


class _DatosInicioSQLite:
    def __init__(self, conn):
        self._conn = conn

    def lectura(self):
        from finanzas.infraestructura import persistencia as db
        return db.lectura_consistente(self._conn)

    def cantidades(self):
        from finanzas.bootstrap.sincronizacion import componer_registro_avisos
        sincronizacion = componer_registro_avisos(self._conn)
        ultima = sincronizacion.leer_estado()
        pendientes, no_banco = componer_gestion_importaciones(self._conn).resumen_acciones()
        return (
            ("sin_categoria", "Sin categoría", componer_catalogo_categorias(self._conn).resumen_pendientes().cuantos, "/movimientos?vista=sin-categorizar"),
            ("no_reconocidos", "Correos no reconocidos", sincronizacion.contar_no_reconocidos(), "/no-reconocidos"),
            ("sincronizacion_fallida", "Sincronización fallida", int(ultima is not None and ultima.estado == "fallida"), "/"),
            ("preguntas", "Preguntas de conciliación", pendientes, "/conciliacion/preguntas"),
            ("no_en_banco", "No está en el banco", no_banco, "/conciliacion/no-esta-en-el-banco"),
        )


def componer_inicio(conn):
    return inicio.estado(_DatosInicioSQLite(conn))


def restaurar_borrado(conn, copia):
    return deshacer.restaurar(copia, componer_saldo(conn),
        componer_administracion_categorias(conn), componer_administracion_reglas(conn))
