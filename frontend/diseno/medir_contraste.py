"""Mide los contrastes WCAG 2.x de tokens.css y los imprime como tablas Markdown.

Uso: python3 frontend/diseno/medir_contraste.py

Lee los colores directamente de tokens.css (bloque claro y bloque oscuro
forzado), así que la tabla de SISTEMA.md siempre corresponde al archivo real.
Termina con código 1 si algún par exigido no cumple (texto < 4,5:1 o
elemento de interfaz < 3:1). Solo usa la biblioteca estándar de Python.
"""
import os
import re
import sys

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens.css")


def leer_modos(css):
    """Devuelve {"claro": {token: hex}, "oscuro": {token: hex}}."""
    claro_ini = css.index(':root[data-tema="claro"] {')
    claro = css[claro_ini:css.index("}", claro_ini)]
    oscuro_ini = css.index(':root[data-tema="oscuro"],')
    oscuro = css[oscuro_ini:css.index("}", oscuro_ini)]
    patron = re.compile(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})\s*;")
    return {"claro": dict(patron.findall(claro)), "oscuro": dict(patron.findall(oscuro))}


def _lineal(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminancia(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _lineal(r) + 0.7152 * _lineal(g) + 0.0722 * _lineal(b)


def contraste(a, b):
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# (primer plano, fondo, uso). Mínimo 4,5:1.
TEXTO = [
    ("foreground", "background", "Texto normal sobre el fondo"),
    ("foreground", "card", "Texto normal sobre una hoja"),
    ("foreground", "muted", "Texto sobre fondo apagado"),
    ("muted-foreground", "background", "Texto secundario (ayudas, detalles)"),
    ("muted-foreground", "card", "Texto secundario sobre una hoja"),
    ("muted-foreground", "muted", "Texto secundario sobre fondo apagado"),
    ("primary-foreground", "primary", "Botón principal"),
    ("destructive-foreground", "destructive", "Botón de borrar"),
    ("destructive", "card", "Texto de error y botón Borrar sin borde"),
    ("destructive", "background", "Error sobre el fondo"),
    ("monto-positivo", "card", "Monto que suma (ingresos)"),
    ("monto-negativo", "card", "Monto que resta (ajustes)"),
    ("foreground", "aviso-error-fondo", "Texto de un aviso de error"),
    ("destructive", "aviso-error-fondo", "Ícono y título de error dentro del aviso"),
    ("foreground", "aviso-advertencia-fondo", "Texto del aviso de pendientes"),
    ("muted-foreground", "aviso-advertencia-fondo", "Detalle en una fila pendiente"),
    ("foreground", "aviso-exito-fondo", "Texto de un aviso de éxito"),
    ("foreground", "aviso-info-fondo", "Texto de un aviso informativo"),
    ("sidebar-foreground", "sidebar", "Texto de la barra lateral"),
    ("muted-foreground", "sidebar", "Texto secundario en la barra lateral"),
    ("sidebar-foreground", "sidebar-accent", "Barra lateral al pasar el cursor"),
    ("foreground", "accent", "Botón al pasar el cursor"),
    ("monto-positivo", "background", "Monto que suma sobre el papel"),
    ("monto-negativo", "background", "Monto que resta sobre el papel"),
    ("muted-foreground", "aviso-error-fondo", "Texto secundario dentro de un aviso de error"),
]
# Elementos de interfaz (bordes de campos, foco, íconos). Mínimo 3:1.
INTERFAZ = [
    ("border", "background", "Borde de hojas y botones"),
    ("border", "card", "Borde de botones sobre una hoja"),
    ("input", "card", "Borde de campos y selectores"),
    ("input", "background", "Borde de campos sobre el fondo"),
    ("ring", "card", "Anillo de foco sobre una hoja"),
    ("ring", "background", "Anillo de foco sobre el fondo"),
    ("exito", "aviso-exito-fondo", "Ícono de éxito"),
    ("cat-sin-categorizar", "card", "Borde punteado de «Sin categorizar»"),
    ("ring", "sidebar", "Anillo de foco en la barra lateral"),
    ("ring", "secondary", "Anillo de foco sobre un botón secundario"),
    ("ring", "aviso-error-fondo", "Anillo de foco dentro de un aviso de error"),
    ("ring", "aviso-advertencia-fondo", "Anillo de foco dentro del aviso de pendientes"),
    ("input", "secondary", "Borde de campos sobre fondo apagado"),
]
CATEGORIAS = [
    ("cat-mercado", "Mercado"), ("cat-restaurantes", "Restaurantes"), ("cat-transporte", "Transporte"),
    ("cat-vivienda", "Vivienda y servicios"), ("cat-salud", "Salud"), ("cat-entretenimiento", "Entretenimiento"),
    ("cat-compras", "Compras"), ("cat-antojos", "Antojos"), ("cat-otros", "Otros"),
    ("cat-sueldo", "Sueldo"), ("cat-prestamos", "Préstamos"), ("cat-otros-ingresos", "Otros ingresos"),
    ("cat-sin-categorizar", "Sin categorizar"),
]


def fmt(v):
    return f"{v:.2f}".replace(".", ",")


def main():
    modos = leer_modos(open(RUTA, encoding="utf-8").read())
    fallas = []

    def tabla(pares, minimo, titulo):
        print(f"\n#### {titulo} (mínimo {fmt(minimo)}:1)\n")
        print("| Uso | Primer plano / fondo | Claro | Oscuro |")
        print("|---|---|---|---|")
        for a, b, uso in pares:
            celdas = []
            for modo in ("claro", "oscuro"):
                t = modos[modo]
                v = contraste(t[a], t[b])
                ok = v >= minimo
                if not ok:
                    fallas.append(f"{modo}: {a} sobre {b} = {fmt(v)}")
                celdas.append(f"{fmt(v)}:1 {'✓' if ok else '✗'}")
            print(f"| {uso} | `{a}` / `{b}` | {celdas[0]} | {celdas[1]} |")

    tabla(TEXTO, 4.5, "Textos")
    tabla(INTERFAZ, 3.0, "Elementos de interfaz")

    print("\n#### Categorías (mínimo 3,00:1 contra el fondo y la hoja; el ícono del chip usa `cat-icono`)\n")
    print("| Categoría | Claro | vs. fondo | vs. hoja | Oscuro | vs. fondo | vs. hoja |")
    print("|---|---|---|---|---|---|---|")
    for token, nombre in CATEGORIAS:
        fila = [nombre]
        for modo in ("claro", "oscuro"):
            t = modos[modo]
            c = t[token]
            v1, v2 = contraste(c, t["background"]), contraste(c, t["card"])
            for v, fondo in ((v1, "background"), (v2, "card")):
                if v < 3:
                    fallas.append(f"{modo}: {token} sobre {fondo} = {fmt(v)}")
            fila += [f"`{c}`", f"{fmt(v1)}:1", f"{fmt(v2)}:1"]
        print("| " + " | ".join(fila) + " |")

    if fallas:
        print("\nNO CUMPLE:\n" + "\n".join(fallas))
        return 1
    print("\nTodos los pares cumplen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
