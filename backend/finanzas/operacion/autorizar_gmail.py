"""Comando de autorización conservado por python -m finanzas.gmail."""
from __future__ import annotations
import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from finanzas.modulos.sincronizacion.contratos import ErrorAutorizacionGmail
from finanzas.modulos.sincronizacion.adaptadores.gmail.oauth import autorizar, autorizar_sin_navegador

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m finanzas.gmail",
        description="Herramientas de Gmail (solo lectura).",
    )
    subcomandos = parser.add_subparsers(dest="comando", required=True)
    autorizar_cmd = subcomandos.add_parser(
        "autorizar",
        help="Autoriza el acceso de solo lectura a Gmail y guarda el token.",
    )
    autorizar_cmd.add_argument(
        "--credenciales", required=True,
        help="JSON del cliente OAuth ('App de escritorio') descargado de Google Cloud.",
    )
    autorizar_cmd.add_argument(
        "--token", required=True, help="Ruta donde guardar el token (queda con permisos 0600).",
    )
    autorizar_cmd.add_argument(
        "--sin-navegador", action="store_true",
        help="No abre un navegador en este equipo: muestra un enlace para abrir en cualquier "
        "navegador y pide pegar la dirección http://localhost:1/... a la que redirige Google. "
        "Sirve para autorizar desde el servidor.",
    )
    autorizar_cmd.add_argument(
        "--borrar-credenciales", action="store_true",
        help="Borra el JSON del cliente OAuth al terminar, solo si el token se guardó bien. "
        "El token ya incluye lo necesario para renovarse.",
    )
    args = parser.parse_args(argv)

    if not Path(args.credenciales).is_file():
        print(f"No existe el archivo de credenciales {args.credenciales}.", file=sys.stderr)
        return 2
    # Nunca se imprime el token, el código ni el secreto del cliente; solo dónde quedó el token.
    try:
        if args.sin_navegador:
            autorizar_sin_navegador(args.credenciales, args.token)
        else:
            autorizar(args.credenciales, args.token)
    except ErrorAutorizacionGmail as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        # Ctrl+C: salida limpia, sin traza. guardar_token ya borra su
        # temporal si se interrumpe, así que no queda nada a medias.
        print("\nSe canceló la autorización. No se guardó nada.", file=sys.stderr)
        return 130
    print(f"Token guardado en {args.token} con permisos 0600.")
    if not args.sin_navegador:
        print("Cópialo al servidor, déjalo con 'chmod 600' y apunta GMAIL_TOKEN a esa ruta.")

    if args.borrar_credenciales:
        try:
            os.unlink(args.credenciales)
        except OSError as error:
            print(
                f"El token está bien, pero no se pudo borrar {args.credenciales} "
                f"({type(error).__name__}). Bórralo a mano con 'rm'.",
                file=sys.stderr,
            )
            return 1
        print(f"Se borró el archivo de credenciales {args.credenciales}.")
    return 0



if __name__ == "__main__":
    sys.exit(main())
