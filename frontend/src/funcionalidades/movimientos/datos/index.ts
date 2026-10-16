/**
 * Lo que muestra Movimientos (ítem 14), calculado a partir de las respuestas
 * de la API. Lógica pura (sin React), probada en datos.test.ts.
 *
 * La API decide las reglas de negocio: qué es gasto (`es_gasto`), qué es
 * pendiente (`pendiente`), qué se puede categorizar (`categorizable`), qué
 * regla se podría crear (`regla_posible`), qué pasa cada filtro y cómo se
 * categorizó cada movimiento (`origen_categoria` y `regla`). Aquí solo se
 * decide cómo se ve. Lo único que se suma es el "Gastado" de cada día (la API
 * no lo trae): enteros en centavos, sin pasar por decimales.
 */
import type { Movimiento, Categoria, ReglaAplicada, GrupoPendientes, OpcionRegla, Condiciones } from "./tipos";
import { esBandeja, hayFiltro, type Filtros } from "./filtros";
import { grupoCategorizado, TEXTOS } from "@/compartido/textos/textos";
export * from "./tipos";
export * from "./filtros";
export * from "./dias";

// --- Filas visibles ------------------------------------------------------------------

/**
 * Qué filas se muestran: las que devolvió la API con el filtro, más las que
 * se acaban de categorizar aquí (`retenidas`). Así, en "Sin categorizar", la
 * fila recién categorizada no desaparece antes de que el dueño vea el
 * resultado y pueda crear la regla. En un mes, los datos de cada fila salen
 * de la lista completa del mes (recién leída), en su mismo orden.
 */
export function filasVisibles(
  delMes: readonly Movimiento[],
  filtradas: readonly Movimiento[] | null,
  retenidas: ReadonlyMap<number, Movimiento>,
): Movimiento[] {
  if (filtradas === null) return [...delMes];
  const ids = new Set(filtradas.map((m) => m.id));
  return delMes.filter((m) => ids.has(m.id) || retenidas.has(m.id));
}

/**
 * La bandeja (todos los meses) más las filas recién categorizadas aquí, que
 * ya no vienen en ella: se muestran como estaban, del más reciente al más
 * antiguo (el orden de la API).
 */
export function filasBandeja(
  pendientes: readonly Movimiento[],
  retenidas: ReadonlyMap<number, Movimiento>,
): Movimiento[] {
  const ids = new Set(pendientes.map((m) => m.id));
  const filas = [...pendientes, ...[...retenidas.values()].filter((m) => !ids.has(m.id))];
  return filas.sort((a, b) =>
    a.fecha_hora === b.fecha_hora ? b.id - a.id : a.fecha_hora < b.fecha_hora ? 1 : -1,
  );
}

/** "Otros" va siempre al final de las opciones (decisión de `disenador-ui`); las demás, en el orden de la API. */
export function ordenarCategorias(categorias: readonly Categoria[]): Categoria[] {
  return [...categorias.filter((c) => c.nombre !== "Otros"), ...categorias.filter((c) => c.nombre === "Otros")];
}

/**
 * Las opciones para categorizar un movimiento: solo las de la clase que
 * acepta (`clase_categoria`, lo decide la API). Un gasto, las de gasto; un
 * ingreso, las de ingreso (ítem 15). Sin clase, ninguna.
 */
export function opcionesPara(movimiento: Movimiento, categorias: readonly Categoria[]): Categoria[] {
  const clase = movimiento.clase_categoria;
  if (clase === null) return [];
  return ordenarCategorias(categorias.filter((c) => c.clase === clase));
}

// --- Grupos de pendientes iguales (ítem 38) ---------------------------------------------

/**
 * Las categorías que admite un grupo: solo las de su clase (`clase_categoria`,
 * que manda el servidor: un grupo nunca mezcla gastos con ingresos).
 */
export function categoriasDeGrupo(grupo: Pick<GrupoPendientes, "clase_categoria">, categorias: readonly Categoria[]): Categoria[] {
  return ordenarCategorias(categorias.filter((c) => c.clase === grupo.clase_categoria));
}

/**
 * Los pendientes que no están en ningún grupo: siguen como hoy, uno por uno.
 * Qué es un grupo lo decide el servidor (`grupos`); aquí solo se separan.
 */
export function sinGrupo(pendientes: readonly Movimiento[], grupos: readonly GrupoPendientes[]): Movimiento[] {
  const enGrupos = new Set(grupos.flatMap((g) => g.ids));
  return pendientes.filter((m) => !enGrupos.has(m.id));
}

/**
 * El orden de los grupos en pantalla: los que ya se veían, en su sitio (aunque
 * ya no vengan del servidor porque se acaban de categorizar, y el aviso de su
 * resultado siga ahí); los nuevos, al final y en el orden del servidor.
 */
export function ordenarGrupos<T extends { clave: string }>(
  grupos: readonly T[],
  clavesVistas: readonly string[],
): T[] {
  const lugar = (g: T) => {
    const i = clavesVistas.indexOf(g.clave);
    return i === -1 ? Number.MAX_SAFE_INTEGER : i;
  };
  return [...grupos].sort((a, b) => lugar(a) - lugar(b));
}

/** Antes de elegir: qué regla se guarda junto con la categoría ("compras en X van a la que elijas"). */
export function textoReglaDelGrupo(grupo: GrupoPendientes): string {
  return `Se categorizan juntos y se guarda la regla: ${alcancePorTexto(grupo.regla.campo, grupo.descripcion)} van a la categoría que elijas.`;
}

/**
 * Lo que dice el aviso al categorizar un grupo. `categorizados` y
 * `reglaGuardada` son lo que respondió el servidor (puede haber menos que
 * `cuantos`, si algo ya no estaba pendiente).
 */
export function textoGrupoCategorizado(
  grupo: GrupoPendientes,
  categoria: string,
  respuesta: { categorizados: number; regla_guardada: boolean },
): { titulo: string; regla: string | null } {
  if (respuesta.categorizados === 0) return { titulo: TEXTOS.movimientos.grupos.yaNoHay, regla: null };
  return {
    titulo: grupoCategorizado(respuesta.categorizados, categoria),
    regla: respuesta.regla_guardada
      ? `Regla creada: ${alcancePorTexto(grupo.regla.campo, grupo.descripcion)} van a ${categoria}.`
      : null,
  };
}

// --- Filas -------------------------------------------------------------------------------

const NOMBRE_TIPO: Record<Movimiento["tipo"], string> = {
  compra: "Compra",
  transferencia: "Transferencia",
  ingreso: "Ingreso",
  ajuste: "Ajuste",
};

/** "Compra", "Transferencia", "Ingreso" o "Ajuste" (antes de la hora en la fila). */
export function nombreTipo(tipo: Movimiento["tipo"]): string {
  return NOMBRE_TIPO[tipo];
}

/**
 * El texto de la regla como lo reconoce el dueño. La API guarda la regla
 * normalizada ("supermercado la espiga"); si es la misma regla que la API
 * propone para este movimiento (`regla_posible`: la API decide si coinciden),
 * se muestra la descripción tal como llegó del banco ("SUPERMERCADO LA ESPIGA").
 */
export function textoDeRegla(regla: ReglaAplicada, movimiento: Movimiento): string {
  const posible = movimiento.regla_posible;
  return posible && posible.campo === regla.campo && posible.texto === regla.texto
    ? movimiento.descripcion
    : (regla.texto ?? "");
}

const FRASE: Record<ReglaAplicada["campo"], (texto: string) => string> = {
  comercio: (texto) => `compra en «${texto}»`,
  cuenta_destino: (texto) => `transferencia a «${texto}»`,
  // Ítem 15: reglas de ingreso por quien envía.
  quien_envia: (texto) => `ingreso de «${texto}»`,
};

/**
 * Pone la descripción del movimiento, tal como llegó del banco, en lugar del
 * texto normalizado de la regla («laura gómez ejemplo» → «LAURA GÓMEZ
 * EJEMPLO»). Solo cambia lo que va entre «…»; el resto es la frase de la API.
 */
function conDescripcion(frase: string, texto: string | null, descripcion: string): string {
  return texto === null ? frase : frase.replace(`«${texto}»`, `«${descripcion}»`);
}

/** "compra en «X»", "transferencia de $3.200"… (la regla en una frase). */
export function fraseRegla(regla: ReglaAplicada, movimiento: Movimiento): string {
  if (regla.modo_texto !== "exacta" || regla.origen_regla === "extracto") return regla.frase;
  if (regla.condiciones === "texto") return FRASE[regla.campo](textoDeRegla(regla, movimiento));
  // Ítem 17: por monto, o por texto y monto, se lee con la frase de la API; el
  // texto, como en las de texto, con la descripción si es la regla de este movimiento.
  const posible = movimiento.regla_posible;
  const suya = posible !== null && posible.campo === regla.campo && posible.texto === regla.texto;
  return suya ? conDescripcion(regla.frase, regla.texto, movimiento.descripcion) : regla.frase;
}

/** Cómo se categorizó un movimiento (la línea de abajo de la fila). */
export type Origen =
  /** Lo que no se categoriza (los ajustes): la API dice `categorizable: false`. */
  | { tipo: "no-aplica" }
  | { tipo: "sin-categorizar" }
  | { tipo: "manual"; categoria: string }
  | { tipo: "regla"; categoria: string; frase: string; montoCentavos: number | null }
  /** Lo categorizó una regla que ya se borró. */
  | { tipo: "regla-borrada"; categoria: string }
  /** Ya estaba categorizado cuando se empezó a guardar cómo. */
  | { tipo: "desconocido"; categoria: string };

export function origenDe(movimiento: Movimiento): Origen {
  const { categoria, regla } = movimiento;
  if (categoria === null) return movimiento.pendiente ? { tipo: "sin-categorizar" } : { tipo: "no-aplica" };
  if (movimiento.origen_categoria === "manual") return { tipo: "manual", categoria: categoria.nombre };
  if (movimiento.origen_categoria === "regla") {
    return regla
      ? {
          tipo: "regla",
          categoria: categoria.nombre,
          frase: fraseRegla(regla, movimiento),
          montoCentavos: regla.monto_centavos,
        }
      : { tipo: "regla-borrada", categoria: categoria.nombre };
  }
  return { tipo: "desconocido", categoria: categoria.nombre };
}

// --- Categorizar y crear la regla ------------------------------------------------------

/**
 * ¿Se ofrece crear la regla? Solo si la API ofrece alguna (`reglas_posibles`)
 * y no lo categorizaba una regla: al corregir uno categorizado por regla, "la
 * regla sigue igual para los demás" (TEXTOS.md); ofrecerla ahí cambiaría la
 * regla de todos.
 */
export function ofrecerRegla(movimiento: Movimiento, origenAntes: Origen["tipo"]): boolean {
  return movimiento.reglas_posibles.length > 0 && origenAntes !== "regla" && origenAntes !== "regla-borrada";
}

const PLURAL: Record<OpcionRegla["tipo_movimiento"], string> = {
  compra: "compras",
  transferencia: "transferencias",
  ingreso: "ingresos",
};

/** "compras en X", "transferencias a X" o "ingresos de X": a quién alcanza la regla por texto. */
export function alcancePorTexto(campo: OpcionRegla["campo"], descripcion: string): string {
  switch (campo) {
    case "comercio":
      return `compras en ${descripcion}`;
    case "quien_envia":
      return `ingresos de ${descripcion}`;
    default:
      return `transferencias a ${descripcion}`;
  }
}

/**
 * A quién alcanza una regla, en plural: "transferencias de $6.200",
 * "ingresos de «CARLOS RUIZ EJEMPLO» por $400.000". Por monto (o texto y
 * monto) es la frase de la API ("transferencia de $6.200") con el tipo en
 * plural, como en el prototipo; por texto, como en el ítem 14.
 */
function alcance(opcion: OpcionRegla, movimiento: Movimiento): string {
  if (opcion.condiciones === "texto") return alcancePorTexto(opcion.campo, movimiento.descripcion);
  const frase = conDescripcion(opcion.frase, opcion.texto, movimiento.descripcion);
  const tipo = opcion.tipo_movimiento;
  return frase.startsWith(`${tipo} `) ? PLURAL[tipo] + frase.slice(tipo.length) : frase;
}

function conMayusculaInicial(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

/** Un botón para crear una regla (ítem 17: una por cada opción que ofrece la API). */
export interface OfertaRegla {
  /** Lo que se manda en el PUT (`condiciones`). */
  condiciones: Condiciones;
  /** Lo que dice el botón: "Transferencias de $6.200", "Las dos cosas juntas"… */
  boton: string;
  /**
   * Lo que el botón no dice pero un lector de pantalla necesita: en "Las dos
   * cosas juntas", cuáles son ("transferencias a X por $6.200"). `null` si el
   * botón ya lo dice todo.
   */
  detalle: string | null;
  /** El monto de la regla (o `null`), para escribirlo en la letra de los montos. */
  montoCentavos: number | null;
  /** "transferencias de $6.200": a quién alcanza (para "Regla creada: …"). */
  alcance: string;
}

/**
 * Las reglas que se ofrecen crear, en el orden de la API (`reglas_posibles`:
 * la API decide cuáles; aquí solo cómo se leen). Como en el prototipo:
 * "Transferencias a LAURA GÓMEZ EJEMPLO", "Transferencias de $6.200" y "Las
 * dos cosas juntas". "Las dos cosas juntas" solo tiene sentido junto a las
 * otras dos; si no, el botón dice la regla completa.
 */
export function ofertasRegla(movimiento: Movimiento): OfertaRegla[] {
  const opciones = movimiento.reglas_posibles;
  const hay = (c: Condiciones) => opciones.some((o) => o.condiciones === c);
  const juntas = hay("texto") && hay("monto");
  return opciones.map((opcion) => {
    const a = alcance(opcion, movimiento);
    const comoJuntas = opcion.condiciones === "texto_y_monto" && juntas;
    return {
      condiciones: opcion.condiciones,
      boton: comoJuntas ? TEXTOS.movimientos.lasDosCosasJuntas : conMayusculaInicial(a),
      detalle: comoJuntas ? a : null,
      montoCentavos: opcion.monto_centavos,
      alcance: a,
    };
  });
}

/**
 * El botón de la regla por texto: "Compras en PANADERIA EL TRIGAL",
 * "Transferencias a LAURA GÓMEZ EJEMPLO", "Ingresos de EMPRESA EJEMPLO S.A.S.".
 */
export function botonRegla(movimiento: Movimiento): string {
  const campo = movimiento.regla_posible?.campo ?? "cuenta_destino";
  return conMayusculaInicial(alcancePorTexto(campo, movimiento.descripcion));
}

/**
 * "Regla creada: compras en PANADERIA EL TRIGAL van a Mercado." o, con una
 * oferta del ítem 17, "Regla creada: transferencias de $6.200 van a Restaurantes."
 */
export function textoReglaCreada(movimiento: Movimiento, categoria: string, oferta?: OfertaRegla): string {
  const quien = oferta
    ? oferta.alcance
    : alcancePorTexto(movimiento.regla_posible?.campo ?? "cuenta_destino", movimiento.descripcion);
  return `Regla creada: ${quien} van a ${categoria}.`;
}

/** Resultado de categorizar o corregir (TEXTOS.md, "Movimientos"). */
export function textoGuardado(categoria: string, origenAntes: Origen["tipo"]): { titulo: string; texto: string } {
  if (origenAntes === "regla" || origenAntes === "regla-borrada") {
    return {
      titulo: `Cambiado a ${categoria}.`,
      texto: "Ahora está categorizado a mano; la regla sigue igual para los demás.",
    };
  }
  return {
    titulo: `Guardado en ${categoria}.`,
    texto: "¿Categorizar igual las siguientes? Crea una regla con un toque:",
  };
}

// --- Estados vacíos ----------------------------------------------------------------------

/**
 * La lista quedó vacía (TEXTOS.md, "Estados vacíos"). `categoria` es el
 * nombre de la del filtro. `null`: el mes no tiene movimientos (sin filtro).
 */
export function textosVacio(
  filtros: Filtros,
  categoria: string | null,
  nombreMes: string,
): { titulo: string; texto: string; verTodos: boolean } | null {
  if (esBandeja(filtros)) {
    // La bandeja es de todos los meses: la frase no nombra un mes.
    return { titulo: "Todo categorizado", texto: "Cada movimiento tiene su categoría.", verTodos: false };
  }
  if (!hayFiltro(filtros)) return null;
  const que =
    categoria !== null
      ? `movimientos de ${categoria}`
      : filtros.vista === "ingresos"
        ? "ingresos"
        : "gastos";
  return { titulo: "Nada con este filtro", texto: `No hay ${que} en ${nombreMes}.`, verTodos: true };
}
