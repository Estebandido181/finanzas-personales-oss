"""Configuración de la app, leída de variables de entorno.

Los mensajes de error nombran la variable que falla, pero nunca muestran
su valor (pueden ser secretos).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from finanzas.modulos.sincronizacion.contratos import REMITENTES_OFICIALES
from finanzas.seguridad import hash_bien_formado

LARGO_MINIMO_SECRETO = 32
# Marcador publicado en versiones anteriores del ejemplo: nunca es una clave.
_SECRETO_DE_EJEMPLO = "reemplazar-con-una-clave-aleatoria-de-al-menos-32-caracteres"

# Desde el ítem 27 (D30) los remitentes son exactamente los dos oficiales
# (``gmail.REMITENTES_OFICIALES``) y no se configuran. La variable antigua
# GMAIL_REMITENTE solo se tolera vacía o con una de esas dos direcciones (no
# cambia nada: se usan las dos); cualquier otro valor detiene la app con un
# error claro en vez de ignorarse en silencio.
_MENSAJE_GMAIL_REMITENTE = (
    "GMAIL_REMITENTE ya no se usa: la app lee solo los dos remitentes oficiales de "
    "Bancolombia (D30). Borra esa variable del archivo de entorno."
)


class ErrorConfiguracion(Exception):
    """La configuración del entorno es inválida o incompleta."""


@dataclass(frozen=True)
class Config:
    db_path: str
    app_password_hash: str
    session_secret: str
    cookie_secure: bool = True
    max_intentos: int = 5
    bloqueo_minutos: int = 15
    # Gmail es opcional: sin token la app arranca, pero sincronizar da un error claro.
    gmail_token: str | None = None
    gmail_remitentes: tuple[str, ...] = REMITENTES_OFICIALES

    def __repr__(self) -> str:  # evita que los secretos aparezcan en logs o trazas
        return (
            f"Config(db_path={self.db_path!r}, app_password_hash='***', "
            f"session_secret='***', cookie_secure={self.cookie_secure}, "
            f"max_intentos={self.max_intentos}, bloqueo_minutos={self.bloqueo_minutos}, "
            f"gmail_token={self.gmail_token!r}, gmail_remitentes={self.gmail_remitentes!r})"
        )

    @classmethod
    def desde_entorno(cls, entorno: Mapping[str, str] | None = None) -> "Config":
        """Construye la configuración; lanza ``ErrorConfiguracion`` si algo falta o es inválido."""
        env = os.environ if entorno is None else entorno

        def obligatoria(nombre: str) -> str:
            valor = env.get(nombre, "").strip()
            if not valor:
                raise ErrorConfiguracion(
                    f"Falta la variable de entorno obligatoria {nombre}. "
                    "Revisa .env.example y el README."
                )
            return valor

        def entero_positivo(nombre: str, defecto: int) -> int:
            crudo = env.get(nombre, "").strip()
            if not crudo:
                return defecto
            try:
                valor = int(crudo)
            except ValueError:
                raise ErrorConfiguracion(f"{nombre} debe ser un número entero.") from None
            if valor <= 0:
                raise ErrorConfiguracion(f"{nombre} debe ser mayor que 0.")
            return valor

        password_hash = obligatoria("APP_PASSWORD_HASH")
        if not hash_bien_formado(password_hash):
            # Falla al arrancar y no al hacer login: un hash roto (p. ej. con los
            # "$" expandidos por la shell) bloquearía al dueño sin explicación.
            raise ErrorConfiguracion(
                "APP_PASSWORD_HASH no tiene el formato esperado "
                "(scrypt:n:r:p:sal_hex:hash_hex). Genéralo de nuevo con "
                "python -m finanzas.seguridad y pégalo completo."
            )
        secreto = obligatoria("SESSION_SECRET")
        if secreto.casefold() == _SECRETO_DE_EJEMPLO:
            raise ErrorConfiguracion(
                "SESSION_SECRET conserva un valor de ejemplo. Genera una clave aleatoria propia."
            )
        if len(secreto) < LARGO_MINIMO_SECRETO:
            raise ErrorConfiguracion(
                f"SESSION_SECRET debe tener al menos {LARGO_MINIMO_SECRETO} caracteres."
            )

        crudo_secure = env.get("COOKIE_SECURE", "").strip().lower() or "true"
        if crudo_secure not in ("true", "false"):
            raise ErrorConfiguracion("COOKIE_SECURE debe ser 'true' o 'false'.")

        antiguo = env.get("GMAIL_REMITENTE", "").strip().casefold()
        if antiguo and antiguo not in {r.casefold() for r in REMITENTES_OFICIALES}:
            raise ErrorConfiguracion(_MENSAJE_GMAIL_REMITENTE)

        return cls(
            db_path=env.get("DB_PATH", "").strip() or "finanzas.db",
            app_password_hash=password_hash,
            session_secret=secreto,
            cookie_secure=crudo_secure == "true",
            max_intentos=entero_positivo("MAX_INTENTOS", 5),
            bloqueo_minutos=entero_positivo("BLOQUEO_MINUTOS", 15),
            gmail_token=env.get("GMAIL_TOKEN", "").strip() or None,
            gmail_remitentes=REMITENTES_OFICIALES,
        )
