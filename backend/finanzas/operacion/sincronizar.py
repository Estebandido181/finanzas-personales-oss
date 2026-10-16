"""Comando de sincronización existente; sin migraciones automáticas."""
import logging
import sys
from collections.abc import Callable
from finanzas.compartido.config import Config, ErrorConfiguracion
from finanzas.infraestructura import persistencia as db
from finanzas.bootstrap.sincronizacion import componer_sincronizacion, cliente_desde_config
from finanzas.modulos.sincronizacion.publico import ClienteGmail, ErrorAutorizacionGmail
from finanzas.modulos.sincronizacion.contratos import SincronizacionNoConfigurada

logger = logging.getLogger("finanzas.sincronizacion")

def main(
    argv: list[str] | None = None,
    fabrica_cliente: Callable[[Config], ClienteGmail] = cliente_desde_config,
) -> int:
    """Punto de entrada de ``python -m finanzas.sincronizacion``."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        config = Config.desde_entorno()
    except ErrorConfiguracion as error:
        print(f"Error de configuración: {error}", file=sys.stderr)
        return 2

    try:
        # Nunca crea ni cambia tablas: exige la base migrada (python -m finanzas.migrar).
        from finanzas.bootstrap.persistencia import exigir_al_dia
        exigir_al_dia(config.db_path)
    except db.BaseNoMigrada as error:
        print(f"No se pudo sincronizar: {error}", file=sys.stderr)
        return 2

    conn = db.conectar(config.db_path)
    try:
        resultado = componer_sincronizacion(conn).ejecutar( lambda: fabrica_cliente(config), config.gmail_remitentes)
    except (SincronizacionNoConfigurada, ErrorAutorizacionGmail) as error:
        print(f"No se pudo sincronizar: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        # Solo el tipo: el mensaje de una excepción podría traer datos del correo.
        logger.error("La sincronización falló (%s)", type(error).__name__)
        print(f"La sincronización falló ({type(error).__name__}).", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print(f"Sincronización terminada: {resultado.resumen()}.")
    return 1 if resultado.errores else 0
