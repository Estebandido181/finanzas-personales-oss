"""Pruebas del chequeo de datos reales (ítem 24).

Todos los datos son inventados. Los valores con forma de dato real se arman
por partes ("31" + "23456789") para que este mismo archivo no dispare el
chequeo cuando se revisa el repositorio.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "scripts"))

import revisar_datos as rd  # noqa: E402

# Valores inventados, armados por partes.
CELULAR = "31" + "23456789"
CELULAR_EJEMPLO = "300000000" + "1"
TARJETA_LUHN = "4539" + "1488" + "0343" + "6467"  # cumple Luhn, inventada
TARJETA_SIN_LUHN = "4539" + "1488" + "0343" + "6468"
CUENTA = "123" + "-456789-" + "01"
CORREO_REAL = "persona.inventada" + "@" + "correo-cualquiera.co"
CORREO_EJEMPLO = "persona" + "@" + "example.com"
TOKEN = "ya29" + ".a0AfH6SMBx-inventado-0123456789abcdef"
TERMINO_NOMBRE = "Zoraida Quintanilla"  # nombre inventado del "dueño"
TERMINO_DIGITOS = "8391"  # "últimos dígitos" inventados

ENTORNO_GIT = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Prueba",
    "GIT_AUTHOR_EMAIL": "prueba@example.com",
    "GIT_COMMITTER_NAME": "Prueba",
    "GIT_COMMITTER_EMAIL": "prueba@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def revisor(privados: str = "", permitidos: set[str] | None = None) -> rd.Revisor:
    patrones, _ = rd.compilar_lista_privada(privados)
    return rd.Revisor(patrones, permitidos or set())


# ---------------------------------------------------------------- reglas

@pytest.mark.parametrize(
    "linea, regla",
    [
        (f"llámame al {CELULAR}", "celular colombiano"),
        (f"+57 {CELULAR[:3]} {CELULAR[3:6]} {CELULAR[6:]}", "celular colombiano"),
        ("C.C. " + "1.023" + ".456.789", "cédula con rótulo"),
        ("cédula: " + "79" + "123456", "cédula con rótulo"),
        (f"tarjeta {TARJETA_LUHN}", "número de tarjeta"),
        (f"tarjeta {TARJETA_LUHN[:4]} {TARJETA_LUHN[4:8]} {TARJETA_LUHN[8:12]} {TARJETA_LUHN[12:]}",
         "número de tarjeta"),
        (f"cuenta {CUENTA}", "número de cuenta con guiones"),
        (f"escribe a {CORREO_REAL}", "correo fuera de los dominios de ejemplo"),
        (f'token = "{TOKEN}"', "token de acceso de Google"),
        ("GOCSPX" + "-abcdefghijklmnop", "secreto de cliente OAuth de Google"),
        ("-----BEGIN RSA " + "PRIVATE KEY-----", "clave privada"),
        ("sk-ant" + "-api03-abcdefghijklmnopqrstuv", "clave de API de Anthropic"),
    ],
)
def test_reglas_genericas_detectan(linea, regla):
    assert regla in revisor().revisar_linea(linea)


@pytest.mark.parametrize(
    "linea",
    [
        f"celular de ejemplo {CELULAR_EJEMPLO}",
        f"tarjeta {TARJETA_SIN_LUHN}",  # no cumple Luhn
        "4000" + "0000" + "0000" + "0000",  # relleno
        f"escribe a {CORREO_EJEMPLO}",
        "correo de prueba ana@dominio.test y bob@algo.example",
        "monto en centavos 350000000000 y 3500000000",  # montos largos
        "id de Gmail 18c2f3a4b5d6e7f8 e id 1923456789abcdef",
        "fecha compacta 20260929T225533 y 20260929225533",
        "hash abc3123456789def y commit 3d3c42e5aac5ba805825da76410c181273ba90b1",
        "línea 018000000000 de atención",
        "versión 3.123456789",
        "cc: sin número",
    ],
)
def test_reglas_genericas_no_dan_falsos_positivos(linea):
    assert revisor().revisar_linea(linea) == []


@pytest.mark.parametrize(
    "ruta",
    [".env", "config/.env.produccion", "finanzas.db", "datos.sqlite3", "token.json",
     "token_gmail.json", "client_secret_123.json", "respaldos/2026.tar.gz", "app.log"],
)
def test_nombres_prohibidos(ruta):
    assert revisor().revisar_ruta(ruta)


@pytest.mark.parametrize("ruta", [".env.example", "backend/finanzas/db.py", "backend/tests/fixtures/gmail/x.json"])
def test_nombres_permitidos(ruta):
    assert revisor().revisar_ruta(ruta) == []


def test_lista_de_permitidos_solo_valores_exactos():
    r = revisor(permitidos={CELULAR})
    assert r.revisar_linea(f"llave {CELULAR}") == []
    otro = CELULAR[:-1] + "0"
    assert r.revisar_linea(f"llave {otro}") == ["celular colombiano"]


# ---------------------------------------------------------------- lista privada

def test_lista_privada_sin_mayusculas_ni_tildes():
    r = revisor(TERMINO_NOMBRE)
    assert r.revisar_linea("hola ZORAIDA QUINTANÍLLA, compraste") == ["coincide con la lista privada"]
    assert r.revisar_linea("hola zoraida quintanilla") == ["coincide con la lista privada"]


def test_lista_privada_digitos_con_limite():
    r = revisor(TERMINO_DIGITOS)
    assert r.revisar_linea(f"desde tu cuenta *{TERMINO_DIGITOS}") == ["coincide con la lista privada"]
    assert r.revisar_linea(f"cuenta {TERMINO_DIGITOS}.") == ["coincide con la lista privada"]
    assert r.revisar_linea(f"monto 1{TERMINO_DIGITOS}0") == []
    assert r.revisar_linea(f"hash a{TERMINO_DIGITOS}f") == []


def test_lista_privada_gana_a_permitidos():
    termino = "rebote" + "@" + "correo-del-dueno.co"
    r = revisor(termino, permitidos={termino})
    assert r.revisar_linea(f"de {termino}") == ["coincide con la lista privada"]


def test_lista_privada_ignora_comentarios_vacios_y_cortos():
    patrones, ignorados = rd.compilar_lista_privada("# comentario\n\n  \nab\nZoraida\n")
    assert len(patrones) == 1
    assert ignorados == 1


def test_lista_privada_revisa_nombres_de_archivo(repo, monkeypatch, capsys):
    # Ronda 1, punto 2: la ruta que revela un término se imprime oculta en
    # TODOS los hallazgos de ese archivo (nombre y contenido).
    r = revisor("quintanilla")
    assert r.revisar_ruta("docs/extracto_quintanilla.txt")
    commit(repo, {"docs/secreto_quintanilla.txt": f"llama al {CELULAR[:-1]}9\n"})
    assert correr(repo, "--base", "develop", lista="Quintanilla", monkeypatch=monkeypatch) == 1
    salida = capsys.readouterr()
    todo = salida.out + salida.err
    assert "quintanilla" not in todo.casefold()
    assert "<ruta oculta> (commit" in todo
    assert "<ruta oculta>:1 (commit" in todo  # el celular, también con la ruta oculta


# ---------------------------------------------------------------- repos de prueba

def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=ENTORNO_GIT)


def commit(repo: Path, archivos: dict[str, str | None], mensaje: str = "cambio") -> None:
    for ruta, contenido in archivos.items():
        camino = repo / ruta
        if contenido is None:
            camino.unlink()
            git(repo, "rm", "-q", "--cached", ruta)
            continue
        camino.parent.mkdir(parents=True, exist_ok=True)
        camino.write_text(contenido, encoding="utf-8")
        git(repo, "add", "-f", ruta)
    git(repo, "commit", "-q", "-m", mensaje)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "develop")
    commit(tmp_path, {"README.md": f"base con {CELULAR} ya integrado antes\n"}, "base")
    git(tmp_path, "switch", "-q", "-c", "tarea/x")
    return tmp_path


def correr(repo: Path, *args: str, lista: str | None = None, monkeypatch=None) -> int:
    if lista is None:
        monkeypatch.delenv("DATOS_PROHIBIDOS", raising=False)
    else:
        monkeypatch.setenv("DATOS_PROHIBIDOS", lista)
    return rd.main(["--repo", str(repo), "--permitidos", str(repo / "no-existe.txt"), *args])


def test_rama_limpia_pasa(repo, monkeypatch, capsys):
    commit(repo, {"app.py": "print('hola')\n"})
    assert correr(repo, "--base", "develop", lista=TERMINO_NOMBRE, monkeypatch=monkeypatch) == 0
    assert "Sin datos reales" in capsys.readouterr().out


def test_solo_revisa_lo_que_agrega_la_rama(repo, monkeypatch):
    # El README de la base tiene un celular, pero la rama no lo tocó.
    commit(repo, {"app.py": "x = 1\n"})
    assert correr(repo, "--base", "develop", lista=TERMINO_NOMBRE, monkeypatch=monkeypatch) == 0


def test_lineas_borradas_no_cuentan(repo, monkeypatch):
    commit(repo, {"README.md": "base limpia\n"})
    assert correr(repo, "--base", "develop", lista=TERMINO_NOMBRE, monkeypatch=monkeypatch) == 0


def test_dato_privado_no_se_imprime(repo, monkeypatch, capsys):
    commit(repo, {"notas.txt": "uno\ndos\nHola Zoraida Quintanilla, tu saldo\n"})
    assert correr(repo, "--base", "develop", lista=TERMINO_NOMBRE, monkeypatch=monkeypatch) == 1
    salida = capsys.readouterr()
    todo = (salida.out + salida.err).casefold()
    assert "notas.txt:3" in todo
    assert "lista privada" in todo
    assert "zoraida" not in todo and "quintanilla" not in todo and "saldo" not in todo


def test_dato_generico_no_se_imprime(repo, monkeypatch, capsys):
    commit(repo, {"a.py": f"TEL = '{CELULAR[:-1]}9'\n"})
    assert correr(repo, "--base", "develop", lista=TERMINO_NOMBRE, monkeypatch=monkeypatch) == 1
    salida = capsys.readouterr()
    assert "a.py:1" in salida.out and "celular colombiano" in salida.out
    assert CELULAR[:-1] not in salida.out + salida.err


def test_dato_subido_y_borrado_en_otro_commit_igual_salta(repo, monkeypatch, capsys):
    commit(repo, {"a.txt": f"cuenta *{TERMINO_DIGITOS}\n"}, "se coló")
    commit(repo, {"a.txt": "cuenta *0000\n"}, "lo borro")
    assert correr(repo, "--base", "develop", lista=TERMINO_DIGITOS, monkeypatch=monkeypatch) == 1
    assert "a.txt:1 (commit" in capsys.readouterr().out


def test_archivo_env_en_la_rama_salta(repo, monkeypatch, capsys):
    commit(repo, {".env": "SESSION_SECRET=x\n", ".env.example": "SESSION_SECRET=\n"})
    assert correr(repo, "--base", "develop", lista=TERMINO_NOMBRE, monkeypatch=monkeypatch) == 1
    out = capsys.readouterr().out
    assert ".env (commit" in out
    assert ".env.example" not in out


def test_archivo_binario_se_revisa_por_nombre(repo, monkeypatch, capsys):
    (repo / "finanzas.db").write_bytes(b"\x00\x01SQLite")
    git(repo, "add", "-f", "finanzas.db")
    git(repo, "commit", "-q", "-m", "db")
    assert correr(repo, "--base", "develop", lista=TERMINO_NOMBRE, monkeypatch=monkeypatch) == 1
    assert "finanzas.db" in capsys.readouterr().out


def test_sin_lista_avisa_en_local(repo, monkeypatch, capsys):
    commit(repo, {"app.py": "x = 1\n"})
    assert correr(repo, "--base", "develop", monkeypatch=monkeypatch) == 0
    assert "AVISO" in capsys.readouterr().err


def test_sin_lista_falla_con_estricto(repo, monkeypatch, capsys):
    commit(repo, {"app.py": "x = 1\n"})
    assert correr(repo, "--estricto", "--base", "develop", monkeypatch=monkeypatch) == 2
    assert "DATOS_PROHIBIDOS" in capsys.readouterr().err


def test_lista_desde_archivo(repo, tmp_path_factory, monkeypatch):
    fuera = tmp_path_factory.mktemp("fuera") / "lista.txt"
    fuera.write_text(TERMINO_NOMBRE + "\n", encoding="utf-8")
    commit(repo, {"a.txt": "de zoraida quintanilla\n"})
    assert correr(repo, "--estricto", "--base", "develop", "--lista", str(fuera),
                  monkeypatch=monkeypatch) == 1


def test_base_inexistente_es_error(repo, monkeypatch):
    assert correr(repo, "--base", "no-existe", lista=TERMINO_NOMBRE, monkeypatch=monkeypatch) == 2


def test_modo_todo_revisa_el_arbol(repo, monkeypatch, capsys):
    # En modo --todo sí aparece el celular que ya estaba en la base.
    assert correr(repo, "--todo", lista=TERMINO_NOMBRE, monkeypatch=monkeypatch) == 1
    assert "README.md:1" in capsys.readouterr().out


# ---------------------------------------------------------------- el propio repositorio

def test_el_repositorio_actual_sale_limpio():
    """Reglas genéricas + datos_permitidos.txt sobre todo el repo: sin hallazgos.

    Si esta prueba falla por un falso positivo, se agrega el valor exacto y su
    motivo a scripts/datos_permitidos.txt; nunca se afloja una regla.
    """
    # Solo archivos con seguimiento: no los archivos locales del desarrollador.
    r = rd.Revisor([], rd.cargar_permitidos(rd.PERMITIDOS_POR_DEFECTO))
    hallazgos = rd.revisar_arbol(RAIZ, r, solo_seguidos=True)
    assert hallazgos == [], "\n".join(map(str, hallazgos))


# ---------------------------------------------------------------- ronda 1 del revisor

CELULAR_OTRO = "31" + "98765432"


def test_linea_agregada_que_empieza_por_mas_mas_no_es_cabecera(repo, monkeypatch, capsys):
    # Punto 1: "++ ..." agregada se ve en el diff como "+++ ...".
    commit(repo, {"notas.txt": f"++ hola Zoraida Quintanilla {CELULAR_OTRO}\n"})
    assert correr(repo, "--base", "develop", lista=TERMINO_NOMBRE, monkeypatch=monkeypatch) == 1
    salida = capsys.readouterr()
    todo = salida.out + salida.err
    assert "notas.txt:1 (commit" in todo
    assert "lista privada" in todo and "celular colombiano" in todo
    assert "zoraida" not in todo.casefold() and CELULAR_OTRO not in todo


def test_gitattributes_no_apaga_el_contenido(repo, monkeypatch, capsys):
    # Punto 3: "* -diff" haría que git dijera "Binary files differ".
    commit(repo, {".gitattributes": "* -diff\n", "a.txt": f"tel {CELULAR_OTRO}\n"})
    commit(repo, {".gitattributes": "* binary diff=nada\n", "b.txt": f"tel {CELULAR_OTRO}\n"})
    assert correr(repo, "--base", "develop", lista=TERMINO_NOMBRE, monkeypatch=monkeypatch) == 1
    out = capsys.readouterr().out
    assert "a.txt:1 (commit" in out and "b.txt:1 (commit" in out


def test_binario_de_verdad_solo_por_nombre(repo, monkeypatch):
    # Límite documentado: el contenido con bytes NUL no se revisa.
    (repo / "foto.png").write_bytes(b"\x89PNG\x00" + CELULAR_OTRO.encode())
    git(repo, "add", "foto.png")
    git(repo, "commit", "-q", "-m", "imagen")
    assert correr(repo, "--base", "develop", lista=TERMINO_NOMBRE, monkeypatch=monkeypatch) == 0


@pytest.mark.parametrize(
    "ruta",
    ["con espacio/mi archivo.txt", 'comillas "raras".txt', "tildes/ñandú árbol.txt", "tab\tal final.txt"],
)
def test_rutas_raras_se_revisan(repo, monkeypatch, capsys, ruta):
    # Punto 4: espacios (tab en "+++"), comillas y caracteres no ASCII.
    commit(repo, {ruta: f"tel {CELULAR_OTRO}\n"})
    assert correr(repo, "--base", "develop", lista=TERMINO_NOMBRE, monkeypatch=monkeypatch) == 1
    # Los caracteres de control del nombre se imprimen escapados (\t).
    mostrada = ruta.replace("\t", "\\t")
    assert f"{mostrada}:1 (commit" in capsys.readouterr().out


def test_archivo_vacio_prohibido_se_detecta(repo, monkeypatch, capsys):
    # Punto 4: un archivo vacío no tiene "+++" en el diff.
    commit(repo, {".env": ""})
    assert correr(repo, "--base", "develop", lista=TERMINO_NOMBRE, monkeypatch=monkeypatch) == 1
    assert ".env (commit" in capsys.readouterr().out


def test_renombre_puro_se_detecta(repo, monkeypatch, capsys):
    # Punto 4: un renombre sin cambios no trae contenido en el diff.
    commit(repo, {"notas.txt": "nada\n", "otra.txt": "otra\n"})
    git(repo, "mv", "notas.txt", ".env")
    git(repo, "mv", "otra.txt", "extracto_quintanilla.txt")
    git(repo, "commit", "-q", "-m", "renombres")
    assert correr(repo, "--base", "develop", lista="Quintanilla", monkeypatch=monkeypatch) == 1
    out = capsys.readouterr().out
    assert ".env (commit" in out
    assert "<ruta oculta> (commit" in out and "quintanilla" not in out.casefold()


def test_permitido_no_actua_como_patron():
    # Punto 5: el usuario antes del "=" es parte del correo.
    r = rd.Revisor([], rd.cargar_permitidos(rd.PERMITIDOS_POR_DEFECTO))
    real = "b-123-" + "fulano.real" + "=gmail.com" + "@" + "trans.an.notificacionesbancolombia.com"
    assert r.revisar_linea(f"<{real}>") == ["correo fuera de los dominios de ejemplo"]
    inventado = "b-000000001-dueno.ejemplo" + "=gmail.com" + "@" + "trans.an.notificacionesbancolombia.com"
    assert r.revisar_linea(f"<{inventado}>") == []
    for especial in "!#$%&'*+/=?^_{|}~":
        correo = f"fulano{especial}real" + "@" + "notificacionesbancolombia.com"
        assert r.revisar_linea(correo), especial


def test_permitidos_no_tiene_pedazos_de_correo():
    for valor in rd.cargar_permitidos(rd.PERMITIDOS_POR_DEFECTO):
        assert not valor.startswith("gmail.com@"), valor
        assert valor != "301" + "2345678"


def test_resolucion_de_fusion_se_revisa(repo, monkeypatch, capsys):
    # Punto 6: lo que agrega la resolución de un conflicto.
    commit(repo, {"a.txt": "rama\n"})
    git(repo, "switch", "-q", "develop")
    commit(repo, {"a.txt": "develop\n"})
    git(repo, "switch", "-q", "tarea/x")
    subprocess.run(["git", "-C", str(repo), "merge", "-q", "develop"],
                   capture_output=True, env=ENTORNO_GIT, check=False)
    (repo / "a.txt").write_text(f"resuelto {CELULAR_OTRO}\n", encoding="utf-8")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-q", "--no-edit")
    assert correr(repo, "--base", "develop", lista=TERMINO_NOMBRE, monkeypatch=monkeypatch) == 1
    assert "a.txt:1 (commit" in capsys.readouterr().out


def test_fusion_limpia_no_revisa_lo_que_ya_estaba_en_la_base(repo, monkeypatch, capsys):
    commit(repo, {"a.txt": "rama\n"})
    git(repo, "switch", "-q", "develop")
    commit(repo, {"b.txt": f"ya integrado {CELULAR_OTRO}\n"})
    git(repo, "switch", "-q", "tarea/x")
    git(repo, "merge", "-q", "--no-edit", "develop")
    assert correr(repo, "--base", "develop", lista=TERMINO_NOMBRE, monkeypatch=monkeypatch) == 0, (
        capsys.readouterr().out
    )


def test_mensaje_de_commit_se_revisa(repo, monkeypatch, capsys):
    # Punto 7.
    commit(repo, {"a.txt": "x\n"}, f"arreglo\n\npara Zoraida Quintanilla, tel {CELULAR_OTRO}")
    assert correr(repo, "--base", "develop", lista=TERMINO_NOMBRE, monkeypatch=monkeypatch) == 1
    salida = capsys.readouterr()
    todo = salida.out + salida.err
    assert "<mensaje del commit>:3 (commit" in todo
    assert "lista privada" in todo and "celular colombiano" in todo
    assert "zoraida" not in todo.casefold() and CELULAR_OTRO not in todo


def test_espacios_repetidos_se_colapsan():
    # Punto 8: en el texto y en la lista privada.
    assert revisor(TERMINO_NOMBRE).revisar_linea("Zoraida   \tQuintanilla")
    assert revisor("Zoraida    Quintanilla").revisar_linea("zoraida quintanilla")


def test_workflow_fija_versiones():
    # Punto 9, acciones fijadas por SHA y permisos mínimos.
    import re

    ci = (RAIZ / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "lts/" not in ci
    assert re.search(r'node-version: "\d+"', ci)
    usos = re.findall(r"uses: (\S+)", ci)
    assert usos and all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u) for u in usos), usos
    assert "permissions:\n  contents: read" in ci


def test_dato_generico_en_el_nombre_de_archivo_se_detecta_y_se_oculta(repo, monkeypatch, capsys):
    # Revisión, ronda 2: un celular en el nombre del archivo no debe salir en
    # el registro (ni pasar sin aviso si el contenido está limpio).
    nombre = f"cel_{CELULAR[:-1]}9.txt"
    commit(repo, {nombre: "nada que ver\n"})
    assert correr(repo, "--base", "develop", lista="Quintanilla", monkeypatch=monkeypatch) == 1
    salida = capsys.readouterr()
    todo = salida.out + salida.err
    assert CELULAR[:-1] not in todo
    assert "<ruta oculta> (commit" in todo


def test_ruta_con_salto_de_linea_no_escribe_lineas_falsas():
    r = revisor("quintanilla")
    assert "\n" not in r.mostrar("a\nSin datos reales a la vista.txt")
