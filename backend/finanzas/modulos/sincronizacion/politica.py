"""Decisión de sincronizar al abrir, con la misma hora y códigos vigentes."""
from datetime import datetime, timedelta
from finanzas.compartido import hora
from .contratos import EstadoSincronizacion

ANTIGUEDAD_PARA_SINCRONIZAR = timedelta(hours=1)
CODIGOS_QUE_NO_SE_ARREGLAN_SOLOS = frozenset({"gmail_no_configurado", "autorizacion_gmail"})

def debe_sincronizar_al_abrir(
    estado: EstadoSincronizacion | None,
    *,
    gmail_configurado: bool,
    fecha_configurada: bool,
    en_curso: bool,
    ahora: datetime | None = None,
) -> bool:
    """¿La app debe sincronizar sola al abrirse? (ítem 38)

    Sí, solo si se cumple todo:

    * Gmail está configurado en el servidor y hay fecha de inicio (si no,
      la sincronización fallaría seguro);
    * no hay una sincronización en curso;
    * la última terminó hace **más** de ``ANTIGUEDAD_PARA_SINCRONIZAR``, o
      nunca hubo una;
    * la última no falló por un error que no se arregla solo
      (``CODIGOS_QUE_NO_SE_ARREGLAN_SOLOS``): así la app no reintenta sin parar.

    ``ahora`` es la hora de Colombia (``hora.ahora_colombia`` por omisión), la
    misma con la que se guarda ``terminada_en``. Si ``terminada_en`` quedó en
    el futuro (reloj cambiado), cuenta como reciente; si no se puede leer,
    como si nunca hubiera habido una.
    """
    if not gmail_configurado or not fecha_configurada or en_curso:
        return False
    if estado is None:
        return True
    if estado.estado == "fallida" and estado.codigo_error in CODIGOS_QUE_NO_SE_ARREGLAN_SOLOS:
        return False
    try:
        terminada = datetime.fromisoformat(estado.terminada_en)
    except (TypeError, ValueError):
        return True
    momento = hora.ahora_colombia() if ahora is None else hora.a_hora_colombia(ahora)
    return momento - hora.a_hora_colombia(terminada) > ANTIGUEDAD_PARA_SINCRONIZAR
