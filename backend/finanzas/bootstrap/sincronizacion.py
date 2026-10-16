"""Composición del correo, sus participantes y la barrera de autenticidad."""
from dataclasses import dataclass
from finanzas.compartido.config import Config
from finanzas.modulos.sincronizacion.publico import ClienteGmail, REMITENTES_OFICIALES
from finanzas.modulos.sincronizacion.contratos import SincronizacionNoConfigurada
from finanzas.modulos.movimientos.publico import RegistroNormalizado
from finanzas.modulos.importaciones.publico import IncorporarAviso
from finanzas.modulos.categorias.publico import ClasificarEntrada
from finanzas.modulos.sincronizacion.adaptadores.gmail.cliente import ClienteGmailReal
from finanzas.modulos.sincronizacion.adaptadores.avisos import evaluacion
from finanzas.modulos.sincronizacion.registro_sqlite import AvisosRegistradosSQLite, RegistroSincronizacionSQLite
from finanzas.modulos.sincronizacion.aplicacion import Sincronizar
from finanzas.bootstrap.movimientos import componer_registro_normalizado
from finanzas.bootstrap.importaciones import componer_incorporacion_aviso
from finanzas.bootstrap.categorias import componer_clasificacion_entrada


@dataclass(frozen=True)
class _ColaboradoresSincronizacion:
    normalizado: RegistroNormalizado
    incorporacion: IncorporarAviso
    clasificacion: ClasificarEntrada


def componer_colaboradores_sincronizacion(conn):
    return _ColaboradoresSincronizacion(componer_registro_normalizado(conn),
        componer_incorporacion_aviso(conn), componer_clasificacion_entrada(conn))


def componer_registro_avisos(conn):
    return AvisosRegistradosSQLite(conn, colaboradores=componer_colaboradores_sincronizacion(conn))


def componer_registro_sincronizacion(conn):
    return RegistroSincronizacionSQLite(conn, colaboradores=componer_colaboradores_sincronizacion(conn))


def componer_sincronizacion(conn):
    return Sincronizar(componer_registro_sincronizacion(conn), evaluacion.evaluar_correo)


def gmail_configurado(config: Config) -> bool:
    """``True`` si el servidor tiene con qué conectarse a Gmail (``GMAIL_TOKEN``).

    La misma condición con la que ``cliente_desde_config`` decide si puede
    crear el cliente.
    """
    return bool(config.gmail_token)

def cliente_desde_config(config: Config) -> ClienteGmail:
    """Crea el cliente real de Gmail a partir de la configuración."""
    if not gmail_configurado(config):
        raise SincronizacionNoConfigurada(
            "Gmail no está configurado: falta la variable GMAIL_TOKEN con la ruta del token. "
            "Revisa la sección 'Conectar Gmail' del README."
        )
    return ClienteGmailReal.desde_token(config.gmail_token, config.gmail_remitentes)
