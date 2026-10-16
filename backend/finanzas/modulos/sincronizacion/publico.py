"""Contratos normalizados para recuperar y leer avisos."""
from .contratos import (ClienteGmail, CorreoGmail, MovimientoExtraido, ErrorGmail, ErrorAutorizacionGmail, REMITENTES_OFICIALES)

from .contratos import ResultadoSincronizacion, EstadoSincronizacion

from .contratos import RegistroAvisos

from .contratos import SincronizacionNoConfigurada, ResultadoReproceso
from .politica import debe_sincronizar_al_abrir
