/**
 * Lo que muestra "Categorías y reglas" (ítem 15), calculado a partir de las
 * respuestas de la API. Lógica pura (sin React), probada en datos.test.ts.
 *
 * La API decide las reglas de negocio (nombre único en su clase, par color +
 * ícono único, a qué se puede pasar lo de una categoría borrada, que no se
 * borre la última de su clase) y responde 400 con un texto para el dueño si
 * algo no se cumple. Aquí se comprueba lo mismo antes de enviar, solo para
 * avisar en el campo sin esperar a la API; la que manda es ella.
 */
import type { Esquemas } from "@/compartido/http/cliente";
import { COLORES, ICONOS, type ClaveColor, type ClaveIcono } from "@/compartido/ui/categorias";

export type CategoriaConUso = Esquemas["CategoriaConUso"];
export type Regla = Esquemas["Regla"];
export type Clase = CategoriaConUso["clase"];
export type CategoriaBorrada = Esquemas["CategoriaBorrada"];

/** Las de una clase, en el orden de la API ("Otros" al final). */
export function deLaClase<T extends { clase: Clase }>(categorias: readonly T[], clase: Clase): T[] {
  return categorias.filter((c) => c.clase === clase);
}

function cantidad(n: number, singular: string, plural: string): string {
  return `${n} ${n === 1 ? singular : plural}`;
}

/** "14 movimientos este mes", "1 movimiento este mes", "Sin movimientos este mes". */
export function textoUso(movimientosMes: number): string {
  if (movimientosMes === 0) return "Sin movimientos este mes";
  return `${cantidad(movimientosMes, "movimiento", "movimientos")} este mes`;
}

// --- Nombre, color e ícono -------------------------------------------------------------

/** Máximo de caracteres del nombre (finanzas/categorizacion.py, MAXIMO_NOMBRE). */
export const MAXIMO_NOMBRE = 40;

/**
 * Forma de comparar nombres, como la API (`normalizar`): sin mayúsculas,
 * Unicode NFC y espacios simples. "  antojos " y "Antojos" son el mismo.
 */
export function claveNombre(nombre: string): string {
  return nombre.normalize("NFC").toLocaleLowerCase("es").split(/\s+/).filter(Boolean).join(" ");
}

/** El nombre sin espacios de más (lo que se envía). */
export function limpiarNombre(nombre: string): string {
  return nombre.split(/\s+/).filter(Boolean).join(" ");
}

export interface Borrador {
  nombre: string;
  clase: Clase;
  color: ClaveColor;
  icono: ClaveIcono;
}

/** Qué está mal en el formulario, por campo (TEXTOS.md y los textos de la API). */
export interface ErroresBorrador {
  nombre?: string;
  icono?: string;
}

/**
 * Revisa una categoría nueva o editada contra las demás. `id` es el de la que
 * se edita (no choca consigo misma); `null` al crear.
 */
export function revisarBorrador(
  borrador: Borrador,
  categorias: readonly CategoriaConUso[],
  id: number | null,
): ErroresBorrador {
  const errores: ErroresBorrador = {};
  const nombre = limpiarNombre(borrador.nombre);
  const otras = categorias.filter((c) => c.id !== id);
  if (nombre === "") {
    errores.nombre = "Escribe el nombre de la categoría.";
  } else if (nombre.length > MAXIMO_NOMBRE) {
    errores.nombre = `El nombre puede tener hasta ${MAXIMO_NOMBRE} caracteres.`;
  } else {
    const repetida = otras.find(
      (c) => c.clase === borrador.clase && claveNombre(c.nombre) === claveNombre(nombre),
    );
    if (repetida) errores.nombre = `Ya existe una categoría «${repetida.nombre}». Usa otro nombre.`;
  }
  if (otras.some((c) => c.color === borrador.color && c.icono === borrador.icono)) {
    errores.icono = "Otra categoría ya tiene ese color con ese ícono; cambia uno de los dos.";
  }
  return errores;
}

export function hayErrores(errores: ErroresBorrador): boolean {
  return errores.nombre !== undefined || errores.icono !== undefined;
}

/**
 * El primer par color + ícono que nadie usa (en el orden de la paleta), para
 * que "Nueva categoría" empiece con algo válido. Si están todos (144 pares),
 * el primero: la revisión avisará.
 */
export function primerParLibre(categorias: readonly CategoriaConUso[]): { color: ClaveColor; icono: ClaveIcono } {
  const usados = new Set(categorias.map((c) => `${c.color} ${c.icono}`));
  for (const color of COLORES) {
    for (const icono of ICONOS) {
      if (!usados.has(`${color} ${icono}`)) return { color, icono };
    }
  }
  return { color: COLORES[0]!, icono: ICONOS[0]! };
}

/** Borrador de "Nueva categoría" (de gasto, con el primer par libre). */
export function borradorNuevo(categorias: readonly CategoriaConUso[], clase: Clase = "gasto"): Borrador {
  return { nombre: "", clase, ...primerParLibre(categorias) };
}

/** Lo que cambió al editar (la API pide al menos un campo). `null` si nada cambió. */
export function cambiosDe(
  original: CategoriaConUso,
  borrador: Borrador,
): Esquemas["EditarCategoriaEntrada"] | null {
  const cambios: Esquemas["EditarCategoriaEntrada"] = {};
  const nombre = limpiarNombre(borrador.nombre);
  if (nombre !== original.nombre) cambios.nombre = nombre;
  if (borrador.color !== original.color) cambios.color = borrador.color;
  if (borrador.icono !== original.icono) cambios.icono = borrador.icono;
  return Object.keys(cambios).length > 0 ? cambios : null;
}

// --- Borrar una categoría --------------------------------------------------------------

/**
 * Cómo es el diálogo de borrar:
 * - `ultima`: es la única de su clase; la API no deja borrarla.
 * - `vacia`: no tiene movimientos ni reglas; se borra sin elegir destino.
 * - `mover`: hay que elegir a qué categoría (de la misma clase) pasan.
 */
export type PlanBorrado =
  | { tipo: "ultima"; texto: string }
  | { tipo: "vacia"; texto: string }
  | { tipo: "mover"; texto: string; destinos: CategoriaConUso[]; destinoInicial: number };

/** El destino que se propone: "Otros" (u "Otros ingresos") si se puede; si no, la primera. */
const DESTINO_PREFERIDO: Record<Clase, string> = { gasto: "Otros", ingreso: "Otros ingresos" };

export function planBorrado(categoria: CategoriaConUso, categorias: readonly CategoriaConUso[]): PlanBorrado {
  const destinos = deLaClase(categorias, categoria.clase).filter((c) => c.id !== categoria.id);
  if (destinos.length === 0) {
    return {
      tipo: "ultima",
      texto: `No se puede borrar la última categoría de ${categoria.clase}: crea otra antes.`,
    };
  }
  const { movimientos_total: movimientos, reglas } = categoria;
  if (movimientos === 0 && reglas === 0) {
    return { tipo: "vacia", texto: `${categoria.nombre} no tiene movimientos ni reglas.` };
  }
  const partes = [
    movimientos > 0 ? cantidad(movimientos, "movimiento", "movimientos") : null,
    reglas > 0 ? cantidad(reglas, "regla", "reglas") : null,
  ].filter((p): p is string => p !== null);
  const verbo = movimientos + reglas === 1 ? "pasa" : "pasan";
  const cola = movimientos > 0 ? `; los movimientos no se borran.` : ".";
  const preferido = destinos.find((c) => c.nombre === DESTINO_PREFERIDO[categoria.clase]);
  return {
    tipo: "mover",
    texto: `${categoria.nombre} tiene ${partes.join(" y ")}. Elige a qué categoría ${verbo}${cola}`,
    destinos,
    destinoInicial: (preferido ?? destinos[0]!).id,
  };
}

/** El botón del diálogo: "Borrar y pasar a Otros" (cambia con lo elegido). */
export function botonBorrar(plan: PlanBorrado, destino: CategoriaConUso | undefined): string {
  return plan.tipo === "mover" && destino ? `Borrar y pasar a ${destino.nombre}` : "Borrar categoría";
}

/** "Categoría Antojos borrada: 12 movimientos y 1 regla pasaron a Otros." */
export function textoBorrada(nombre: string, resultado: CategoriaBorrada): string {
  const { movimientos_movidos: movimientos, reglas_movidas: reglas, destino } = resultado;
  const partes = [
    movimientos > 0 ? cantidad(movimientos, "movimiento", "movimientos") : null,
    reglas > 0 ? cantidad(reglas, "regla", "reglas") : null,
  ].filter((p): p is string => p !== null);
  if (!destino || partes.length === 0) return `Categoría ${nombre} borrada.`;
  const verbo = movimientos + reglas === 1 ? "pasó" : "pasaron";
  return `Categoría ${nombre} borrada: ${partes.join(" y ")} ${verbo} a ${destino.nombre}.`;
}

// --- Reglas --------------------------------------------------------------------------

/**
 * La frase de la API en partes, para escribirla como en el prototipo: el tipo
 * de movimiento en negrita y la categoría como chip al final.
 * "Si es una compra en «x», va a Mercado" → antes "Si es una ", tipo
 * "compra", resto " en «x»". Si la frase no tiene esa forma, va entera
 * (`chip: false`), sin perder nada de lo que dice la API.
 */
export type PartesFrase =
  | { chip: true; antes: string; tipo: string; resto: string }
  | { chip: false; frase: string };

export function partesFrase(regla: Regla): PartesFrase {
  const final = `, va a ${regla.categoria.nombre}`;
  const frase = fraseEnMayusculas(regla.frase);
  if (!regla.frase.endsWith(final)) return { chip: false, frase };
  const cuerpo = fraseEnMayusculas(regla.frase.slice(0, -final.length));
  const encontrado = /^(Si es una? )(compra|transferencia|ingreso)(.*)$/su.exec(cuerpo);
  if (!encontrado || encontrado[2] !== regla.tipo_movimiento) return { chip: false, frase };
  return { chip: true, antes: encontrado[1]!, tipo: encontrado[2]!, resto: encontrado[3]! };
}

/**
 * La API guarda el texto de la regla normalizado ("supermercado la
 * espiga"). Para mostrarlo como llega del banco (como en Movimientos y en el
 * prototipo), lo que va entre «…» se escribe en mayúsculas. Solo se muestra
 * así: el texto de la regla no cambia.
 */
export function fraseEnMayusculas(frase: string): string {
  return frase.replace(/«([^»]*)»/gu, (_, texto: string) => `«${texto.toLocaleUpperCase("es-CO")}»`);
}
