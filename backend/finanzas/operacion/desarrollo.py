"""Preparación explícita SOLO de pruebas/desarrollo, nunca desde conectar."""
from finanzas.infraestructura.persistencia.conexion import conectar, ruta_de
from finanzas.infraestructura.persistencia.transacciones import transaccion, insertar, _cerrar_transaccion_vacia
from finanzas.infraestructura.persistencia.esquema import categorias, CATEGORIAS_INICIALES
from sqlalchemy import Connection

def preparar(ruta: str) -> None:
    """Solo para pruebas y desarrollo: base en la última migración y con las categorías iniciales.

    En el servidor se usa ``python -m finanzas.migrar``, que además hace el
    respaldo previo y no vuelve a crear categorías.
    """
    from finanzas import migrar

    migrar.aplicar(str(ruta))
    conn = conectar(ruta)
    try:
        with transaccion(conn):
            conn.execute(
                insertar(conn, categorias).on_conflict_do_nothing(index_elements=["nombre", "clase"]),
                [
                    {"nombre": nombre, "clase": clase, "color": color, "icono": icono}
                    for nombre, clase, color, icono in CATEGORIAS_INICIALES
                ],
            )
    finally:
        conn.close()


def inicializar(conn: Connection) -> None:
    """Solo para pruebas y desarrollo: ``preparar`` sobre la base de una conexión abierta.

    Aplica las migraciones pendientes y vuelve a cargar las categorías
    iniciales que falten (idempotente). La app, la sincronización y el
    servidor **nunca** la usan: allí la estructura la cambia solo ``python -m
    finanzas.migrar``, con respaldo previo, y el dueño borra categorías
    (ítem 15) que esto volvería a crear.
    """
    _cerrar_transaccion_vacia(conn)
    preparar(ruta_de(conn))
