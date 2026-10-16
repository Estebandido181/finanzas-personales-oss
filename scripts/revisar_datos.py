"""Busca datos reales del dueño antes de que lleguen al repositorio (ítem 24, D24).

Dos tipos de reglas:

1. Reglas genéricas, que viven aquí y no revelan nada: formas de celular
   colombiano, cédula con su rótulo, tarjeta que cumple la suma de Luhn, cuenta
   con guiones, correos fuera de los dominios reservados para ejemplos, tokens y
   claves con forma conocida, y nombres de archivo que nunca se suben (.env,
   bases de datos, tokens de Google, respaldos, registros).
2. Una lista privada de términos del dueño (nombre, últimos dígitos de cuentas
   y tarjetas, subdominio...). NO vive en el repositorio: publicarla sería
   publicar lo que se quiere proteger. Se lee de la variable de entorno
   DATOS_PROHIBIDOS (un término por línea; en GitHub Actions es un secreto) o de
   un archivo fuera del repo con --lista.

Nunca se imprime el valor encontrado ni la línea que lo contiene: solo el
archivo, el número de línea, el commit y la regla. Así el registro del CI no
filtra el dato que se quiere detener. Si la RUTA de un archivo coincide con la
lista privada, se muestra como "<ruta oculta>" en todos sus hallazgos.

Con --base se revisa cada commit de base..HEAD por separado (un dato que se
subió y luego se borró sigue en el historial):
  - el mensaje del commit;
  - las rutas que el commit agrega o cambia (git diff-tree -z, sin renombres);
  - las líneas agregadas, leídas del contenido real del archivo en ese commit.
    Del diff solo se toman los números de línea de las cabeceras de bloque, con
    --text --no-textconv --no-ext-diff, para que .gitattributes no pueda
    convertir un archivo en "binario" ni cambiar lo que se ve.
  - en las fusiones, las líneas que agrega la resolución (diff combinado --cc).

Límites conocidos (no los cubre este chequeo):
  - un dato partido en dos líneas o escrito con otro separador (por ejemplo
    "312.345.6789" o "Zoraida_Quintanilla") no coincide;
  - los archivos binarios (imágenes, PDF, UTF-16 y cualquier archivo con un
    byte NUL) solo se revisan por nombre. Por eso las capturas de pantalla de
    los PR las revisa una persona;
  - un PR que no recibe el secreto (desde un fork o de Dependabot) queda en
    rojo con --estricto, porque no se puede revisar la lista privada.

Los falsos positivos conocidos (datos inventados de las pruebas, el remitente
público del banco...) se permiten con valores EXACTOS en
scripts/datos_permitidos.txt, cada uno con su motivo. La lista privada tiene
prioridad: un término del dueño salta aunque esté en la lista de permitidos.

Uso:
    python scripts/revisar_datos.py --base origin/develop   # commits de la rama
    python scripts/revisar_datos.py --todo                   # árbol completo
    DATOS_PROHIBIDOS="$(cat ~/.config/finanzas/datos_prohibidos.txt)" \\
        python scripts/revisar_datos.py --base origin/develop
    python scripts/revisar_datos.py --base origin/develop \\
        --lista ~/.config/finanzas/datos_prohibidos.txt

Códigos de salida: 0 limpio, 1 hay hallazgos, 2 error de uso o falta la lista
privada con --estricto.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PERMITIDOS_POR_DEFECTO = RAIZ / "scripts" / "datos_permitidos.txt"
VARIABLE_LISTA = "DATOS_PROHIBIDOS"
LARGO_MINIMO_TERMINO = 3


@dataclass(frozen=True)
class Hallazgo:
    archivo: str
    linea: int | None  # None: el problema es el nombre del archivo
    regla: str
    commit: str | None = None

    def __str__(self) -> str:
        lugar = self.archivo if self.linea is None else f"{self.archivo}:{self.linea}"
        extra = f" (commit {self.commit[:9]})" if self.commit else ""
        return f"{lugar}{extra}: {self.regla}"


# --------------------------------------------------------------------------
# Reglas genéricas de contenido
# --------------------------------------------------------------------------

def _digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto)


def _luhn(numero: str) -> bool:
    total = 0
    for i, c in enumerate(reversed(numero)):
        d = int(c)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _celular_valido(valor: str) -> bool:
    d = _digitos(valor)
    if len(d) == 12:  # con el prefijo 57
        d = d[2:]
    # 300000000x son los números de ejemplo acordados en las pruebas.
    if re.fullmatch(r"300000000\d", d):
        return False
    # Terminado en cinco ceros es un monto redondo (p. ej. $35.000.000,00 en
    # centavos = 3500000000), no un celular: uno real así es casi imposible.
    return not d.endswith("00000")


def _tarjeta_valida(valor: str) -> bool:
    d = _digitos(valor)
    if not 13 <= len(d) <= 19 or d[0] not in "3456":
        return False
    if len(set(d)) <= 2:  # 4000000000000000 y similares: relleno, no tarjeta
        return False
    return _luhn(d)


DOMINIOS_RESERVADOS = re.compile(
    r"(^|\.)(example\.(com|org|net)|example|test|invalid|localhost)$", re.IGNORECASE
)


def _correo_valido(valor: str) -> bool:
    dominio = valor.rsplit("@", 1)[1].rstrip(".")
    return not DOMINIOS_RESERVADOS.search(dominio)


# (nombre de la regla, patrón, filtro opcional que confirma el hallazgo)
REGLAS_CONTENIDO: list[tuple[str, re.Pattern[str], object]] = [
    (
        "celular colombiano",
        re.compile(r"(?<![\w.])(?:\+?57[ -]?)?3\d{2}[ -]?\d{3}[ -]?\d{4}(?![\w])"),
        _celular_valido,
    ),
    (
        "cédula con rótulo",
        re.compile(
            r"(?i)(?<!\w)(?:c\.\s?c\.?|cc|c[ée]dula(?:\s+de\s+ciudadan[íi]a)?)"
            r"\s*(?:n[°º.o]*\s*|:\s*|#\s*)?\d{1,3}(?:[.\s]?\d{3}){1,3}(?!\d)"
        ),
        None,
    ),
    (
        "número de tarjeta",
        re.compile(r"(?<![\w.])\d(?:[ -]?\d){12,18}(?![\w.])"),
        _tarjeta_valida,
    ),
    (
        "número de cuenta con guiones",
        re.compile(r"(?<![\w-])\d{3}-\d{6}-\d{2}(?![\w-])"),
        None,
    ),
    (
        "correo fuera de los dominios de ejemplo",
        # Parte local con los caracteres válidos (RFC 5322), incluido "=": así
        # "algo=gmail.com@dominio" se ve completo y no pasa por un permitido
        # que solo coincide con el final. Se excluye la comilla invertida (es
        # el código de Markdown) y la parte local no empieza por "'" ni ".".
        re.compile(
            r"[A-Za-z0-9!#$%&*+/=?^_{|}~-][A-Za-z0-9!#$%&'*+/=?^_{|}~.-]*"
            r"@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}"
        ),
        _correo_valido,
    ),
    ("token de acceso de Google", re.compile(r"ya29\.[\w-]{20,}"), None),
    ("token de renovación de Google", re.compile(r"(?<![\w/])1//0[\w-]{20,}"), None),
    ("secreto de cliente OAuth de Google", re.compile(r"GOCSPX-[\w-]{10,}"), None),
    ("clave de API de Google", re.compile(r"AIza[\w-]{35}"), None),
    ("token de GitHub", re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_\w{20,})"), None),
    ("clave de API de Anthropic", re.compile(r"sk-ant-[\w-]{20,}"), None),
    ("clave privada", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----"), None),
]

# Nombres de archivo que nunca se suben (refleja .gitignore).
ARCHIVOS_PROHIBIDOS = [
    ".env",
    ".env.*",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "token*.json",
    "*.token.json",
    "client_secret*.json",
    "credenciales*.json",
    "*.log",
]
ARCHIVOS_ENV_PERMITIDOS = {".env.example"}


def revisar_nombre(ruta: str) -> str | None:
    """Devuelve la regla que incumple el nombre del archivo, o None."""
    partes = ruta.split("/")
    base = partes[-1]
    if "respaldos" in partes[:-1]:
        return "archivo dentro de respaldos/"
    if base in ARCHIVOS_ENV_PERMITIDOS:
        return None
    for patron in ARCHIVOS_PROHIBIDOS:
        if fnmatch.fnmatchcase(base, patron):
            return f"archivo prohibido ({patron})"
    return None


# --------------------------------------------------------------------------
# Lista privada y lista de permitidos
# --------------------------------------------------------------------------

def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y con los espacios repetidos colapsados.

    'Núñez  Díaz' y 'NUNEZ DIAZ' coinciden. Los tabuladores cuentan como
    espacio.
    """
    descompuesto = unicodedata.normalize("NFKD", texto.casefold())
    sin_tildes = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes)


def compilar_lista_privada(texto: str) -> tuple[list[re.Pattern[str]], int]:
    """Convierte la lista privada en patrones. Devuelve (patrones, ignorados).

    Cada término debe aparecer entero: ni una letra ni un dígito pegados a los
    lados. Así "5821" salta en "*5821" o "cuenta 5821", pero no en "158210" ni
    en un hash "a5821f". Los términos muy cortos se ignoran (darían falsos
    positivos en todo el repo) y se cuentan para avisar, sin mostrarlos.
    """
    patrones = []
    ignorados = 0
    for linea in texto.splitlines():
        termino = normalizar(linea.strip())
        if not termino or termino.startswith("#"):
            continue
        if len(termino) < LARGO_MINIMO_TERMINO:
            ignorados += 1
            continue
        patrones.append(
            re.compile(r"(?<![0-9a-z])" + re.escape(termino) + r"(?![0-9a-z])")
        )
    return patrones, ignorados


def cargar_permitidos(ruta: Path) -> set[str]:
    """Valores exactos permitidos. Formato: 'valor  # motivo' por línea."""
    permitidos: set[str] = set()
    if not ruta.exists():
        return permitidos
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        valor = linea.split(" #", 1)[0].strip()
        if valor and not valor.startswith("#"):
            permitidos.add(valor)
    return permitidos


# --------------------------------------------------------------------------
# Revisión de una línea y de una ruta
# --------------------------------------------------------------------------

RUTA_OCULTA = "<ruta oculta>"
MENSAJE_COMMIT = "<mensaje del commit>"


@dataclass
class Revisor:
    privados: list[re.Pattern[str]]
    permitidos: set[str]

    def revisar_linea(self, texto: str) -> list[str]:
        """Reglas que incumple la línea (sin repetir y sin el valor)."""
        reglas: list[str] = []
        normal = normalizar(texto)
        if any(p.search(normal) for p in self.privados):
            reglas.append("coincide con la lista privada")
        for nombre, patron, confirma in REGLAS_CONTENIDO:
            for m in patron.finditer(texto):
                valor = m.group(0)
                if valor in self.permitidos:
                    continue
                if confirma is not None and not confirma(valor):
                    continue
                reglas.append(nombre)
                break
        return reglas

    def ruta_privada(self, ruta: str) -> bool:
        normal = normalizar(ruta)
        return any(p.search(normal) for p in self.privados)

    def _reglas_genericas_en_ruta(self, ruta: str) -> list[str]:
        """Reglas genéricas de contenido (celular, cédula, correo...) que
        incumple el propio nombre del archivo."""
        privada = "coincide con la lista privada"
        # "_" es carácter de palabra para \b: "cel_3123456789.txt" no
        # coincidiría con la regla de celular. Se separan las partes del nombre.
        partes = re.sub(r"[_/\\]", " ", ruta)
        return [r for r in self.revisar_linea(partes) if r != privada]

    def mostrar(self, ruta: str) -> str:
        """La ruta tal como se puede imprimir: oculta si revela un término
        privado o un dato de las reglas genéricas (p. ej. un celular en el
        nombre); si no, con los caracteres de control escapados para que un
        nombre con saltos de línea no pueda escribir líneas falsas."""
        if self.ruta_privada(ruta) or self._reglas_genericas_en_ruta(ruta):
            return RUTA_OCULTA
        return "".join(
            c if c.isprintable() else repr(c)[1:-1] for c in ruta
        )

    def revisar_ruta(self, ruta: str) -> list[str]:
        reglas = []
        if self.ruta_privada(ruta):
            reglas.append("el nombre del archivo coincide con la lista privada")
        reglas += [f"el nombre del archivo incumple: {r}" for r in self._reglas_genericas_en_ruta(ruta)]
        regla = revisar_nombre(ruta)
        if regla and ruta not in self.permitidos:
            reglas.append(regla)
        return reglas

    def revisar_texto(self, ruta: str, texto: str, lineas: set[int] | None,
                      commit: str | None = None) -> list[Hallazgo]:
        """Revisa las líneas pedidas de un texto (todas si lineas es None)."""
        hallazgos = []
        mostrada = self.mostrar(ruta) if ruta != MENSAJE_COMMIT else ruta
        # split("\n") y no splitlines(): splitlines() también corta en \x1c-\x1e,
        # \x85 y otros, y los números de línea dejarían de coincidir con git.
        for numero, linea in enumerate(texto.split("\n"), 1):
            if lineas is not None and numero not in lineas:
                continue
            for regla in self.revisar_linea(linea):
                hallazgos.append(Hallazgo(mostrada, numero, regla, commit))
        return hallazgos

    def hallazgos_de_ruta(self, ruta: str, commit: str | None = None) -> list[Hallazgo]:
        mostrada = self.mostrar(ruta)
        return [Hallazgo(mostrada, None, regla, commit) for regla in self.revisar_ruta(ruta)]


# --------------------------------------------------------------------------
# Git
# --------------------------------------------------------------------------

class ErrorGit(RuntimeError):
    pass


def _git_bytes(repo: Path, *args: str, mostrar_error: bool = False) -> bytes:
    """Corre git. El error solo se muestra si se pide: git puede citar rutas."""
    resultado = subprocess.run(
        ["git", "-C", str(repo), "--literal-pathspecs", "-c", "core.quotepath=off", *args],
        capture_output=True,
        check=False,
    )
    if resultado.returncode != 0:
        detalle = resultado.stderr.decode("utf-8", "replace").strip() if mostrar_error else ""
        raise ErrorGit(f"git {args[0]} falló{': ' + detalle if detalle else ''}")
    return resultado.stdout


def _git(repo: Path, *args: str, mostrar_error: bool = False) -> str:
    return _git_bytes(repo, *args, mostrar_error=mostrar_error).decode("utf-8", "replace")


def _es_binario(datos: bytes) -> bool:
    return b"\x00" in datos


# Opciones del diff que ignoran .gitattributes y la configuración local: todo se
# trata como texto, sin conversiones ni programas externos, y sin renombres.
OPCIONES_DIFF = ("--text", "--no-textconv", "--no-ext-diff", "--no-renames", "--no-color")

CABECERA_SIMPLE = re.compile(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@")
CABECERA_COMBINADA = re.compile(r"^(@{3,}) (?:-\S+ )+\+(\d+)(?:,(\d+))? @{3,}")


def _lineas_agregadas(repo: Path, commit: str, ruta: str, fusion: bool) -> set[int]:
    """Números de línea (en el archivo del commit) que el commit agrega.

    En un diff normal con -U0 cada bloque "@@ -a,b +c,d @@" agrega las líneas
    c..c+d-1, y basta leer las cabeceras: ninguna línea de contenido empieza
    por "@@" (todas llevan antes " ", "+", "-" o "\\"). En una fusión (--cc)
    las líneas llevan un prefijo por padre; cuentan las que tienen algún "+"
    y ningún "-".
    """
    args = ["diff-tree", "-p", "-U0", "--root", "--no-commit-id", *OPCIONES_DIFF]
    args += ["--cc"] if fusion else []
    salida = _git(repo, *args, commit, "--", ruta)
    agregadas: set[int] = set()
    if not fusion:
        for linea in salida.split("\n"):
            m = CABECERA_SIMPLE.match(linea)
            if m:
                inicio, cuantas = int(m.group(1)), int(m.group(2) or 1)
                agregadas.update(range(inicio, inicio + cuantas))
        return agregadas
    numero = None
    padres = 0
    for linea in salida.split("\n"):
        m = CABECERA_COMBINADA.match(linea)
        if m:
            padres = len(m.group(1)) - 1
            numero = int(m.group(2))
            continue
        if numero is None or not linea or linea.startswith("\\"):
            continue
        prefijo = linea[:padres]
        if "-" in prefijo:
            continue  # la línea no está en el resultado
        if "+" in prefijo:
            agregadas.add(numero)
        numero += 1
    return agregadas


def _rutas_del_commit(repo: Path, commit: str, fusion: bool) -> list[str]:
    """Rutas que el commit agrega o cambia (no las borradas), con -z."""
    args = ["diff-tree", "-r", "-z", "--root", "--no-commit-id", "--name-only",
            "--no-renames", "--diff-filter=d"]
    args += ["--cc"] if fusion else []
    salida = _git(repo, *args, commit)
    return [r for r in salida.split("\x00") if r]


def revisar_commits(repo: Path, base: str, revisor: Revisor) -> list[Hallazgo]:
    """Revisa CADA commit de base..HEAD: mensaje, rutas y líneas agregadas."""
    commits = _git(repo, "rev-list", "--reverse", "--parents", f"{base}..HEAD",
                   mostrar_error=True).split("\n")
    hallazgos: list[Hallazgo] = []
    for fila in filter(None, commits):
        commit, *padres = fila.split()
        fusion = len(padres) > 1
        mensaje = _git(repo, "log", "-1", "--format=%B", commit)
        hallazgos += revisor.revisar_texto(MENSAJE_COMMIT, mensaje, None, commit)
        for ruta in _rutas_del_commit(repo, commit, fusion):
            hallazgos += revisor.hallazgos_de_ruta(ruta, commit)
            try:
                datos = _git_bytes(repo, "cat-file", "blob", f"{commit}:{ruta}")
            except ErrorGit:
                continue  # submódulo u objeto que no es un archivo
            if _es_binario(datos):
                continue  # solo por nombre (límite documentado)
            lineas = _lineas_agregadas(repo, commit, ruta, fusion)
            if lineas:
                texto = datos.decode("utf-8", "replace")
                hallazgos += revisor.revisar_texto(ruta, texto, lineas, commit)
    return _sin_repetidos(hallazgos)


def revisar_arbol(repo: Path, revisor: Revisor, solo_seguidos: bool = False) -> list[Hallazgo]:
    """Revisa el árbol de trabajo: archivos con seguimiento y, salvo que se
    pida solo_seguidos, también los nuevos que no están ignorados."""
    args = ["ls-files", "-z", "--cached"]
    if not solo_seguidos:
        args += ["--others", "--exclude-standard"]
    salida = _git(repo, *args)
    hallazgos: list[Hallazgo] = []
    for ruta in sorted(set(filter(None, salida.split("\x00")))):
        hallazgos += revisor.hallazgos_de_ruta(ruta)
        camino = repo / ruta
        if camino.is_symlink() or not camino.is_file():
            continue  # borrado sin confirmar, enlace o submódulo
        datos = camino.read_bytes()
        if _es_binario(datos):
            continue
        hallazgos += revisor.revisar_texto(ruta, datos.decode("utf-8", "replace"), None)
    return hallazgos


def _sin_repetidos(hallazgos: list[Hallazgo]) -> list[Hallazgo]:
    return list(dict.fromkeys(hallazgos))


# --------------------------------------------------------------------------
# Programa
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Busca datos reales del dueño en los cambios (ítem 24)."
    )
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument("--base", help="rama base; revisa cada commit de base..HEAD")
    modo.add_argument("--todo", action="store_true", help="revisa el árbol completo")
    parser.add_argument("--lista", type=Path, help="archivo con la lista privada (fuera del repo)")
    parser.add_argument("--permitidos", type=Path, default=PERMITIDOS_POR_DEFECTO)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--estricto", action="store_true",
        help="falla si no hay lista privada (así corre en el CI)",
    )
    args = parser.parse_args(argv)

    texto_lista = os.environ.get(VARIABLE_LISTA, "")
    if args.lista:
        try:
            texto_lista += "\n" + args.lista.expanduser().read_text(encoding="utf-8")
        except OSError as error:
            print(f"No se pudo leer la lista privada: {error.strerror}", file=sys.stderr)
            return 2
    privados, ignorados = compilar_lista_privada(texto_lista)

    if not privados:
        mensaje = (
            f"Falta la lista privada: configura el secreto {VARIABLE_LISTA} "
            "(o usa --lista con un archivo fuera del repositorio)."
        )
        if args.estricto:
            print(f"ERROR: {mensaje}", file=sys.stderr)
            return 2
        print(f"AVISO: {mensaje} Solo se aplican las reglas genéricas.", file=sys.stderr)
    if ignorados:
        print(
            f"AVISO: {ignorados} término(s) de la lista privada tienen menos de "
            f"{LARGO_MINIMO_TERMINO} caracteres y se ignoraron.",
            file=sys.stderr,
        )

    revisor = Revisor(privados, cargar_permitidos(args.permitidos))
    repo = args.repo.resolve()
    try:
        if args.todo:
            hallazgos = revisar_arbol(repo, revisor)
        else:
            hallazgos = revisar_commits(repo, args.base, revisor)
    except ErrorGit as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    if hallazgos:
        print(f"Se encontraron {len(hallazgos)} posible(s) dato(s) real(es):")
        for h in hallazgos:
            print(f"  {h}")
        print(
            "Quita el dato (y reescribe los commits si quedó en el historial). "
            "Si es un falso positivo, agrega el valor exacto y su motivo a "
            "scripts/datos_permitidos.txt."
        )
        return 1
    print("Sin datos reales a la vista.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
