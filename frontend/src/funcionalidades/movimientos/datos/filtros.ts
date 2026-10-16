import type { ConsultaMovimientos } from "./tipos";

// --- Filtros (van en la dirección, como el mes) ------------------------------------

/** Los segmentos de arriba: "Todos", "Gastos", "Ingresos", "Sin categorizar (N)". */
export const VISTAS = ["todos", "gastos", "ingresos", "sin-categorizar", "descartados"] as const;
export type Vista = (typeof VISTAS)[number];

export interface Filtros {
  vista: Vista;
  /** `id` de la categoría del selector "Categoría", o `null` para todas. */
  categoria: number | null;
}

export const SIN_FILTROS: Filtros = { vista: "todos", categoria: null };

/**
 * ¿Admite la vista un filtro de categoría? La API filtra por categoría solo
 * los gastos, y "Sin categorizar" y una categoría se contradicen (la API
 * responde 400 si se piden juntos).
 */
export function admiteCategoria(vista: Vista): boolean {
  return vista === "todos" || vista === "gastos";
}

/** Los filtros de la dirección (`?ver=gastos&categoria=3`). Lo que no se entiende se ignora. */
export function leerFiltros(busqueda: string): Filtros {
  const parametros = new URLSearchParams(busqueda);
  const ver = parametros.get("ver");
  const vista: Vista = (VISTAS as readonly string[]).includes(ver ?? "") ? (ver as Vista) : "todos";
  const texto = parametros.get("categoria") ?? "";
  const numero = /^[1-9]\d{0,8}$/.test(texto) ? Number(texto) : null;
  return { vista, categoria: admiteCategoria(vista) ? numero : null };
}

/** "Sin categorizar" es una sola bandeja, de todos los meses (especificación): no va por mes. */
export function esBandeja(filtros: Filtros): boolean {
  return filtros.vista === "sin-categorizar";
}

/**
 * La dirección de Movimientos para un mes (o el actual, `null`) y unos
 * filtros. La bandeja no lleva mes.
 */
export function rutaMovimientos(mes: string | null, filtros: Filtros = SIN_FILTROS): string {
  const parametros = new URLSearchParams();
  if (mes && !esBandeja(filtros) && filtros.vista !== "descartados") parametros.set("mes", mes);
  if (filtros.vista !== "todos") parametros.set("ver", filtros.vista);
  if (filtros.categoria !== null && admiteCategoria(filtros.vista)) {
    parametros.set("categoria", String(filtros.categoria));
  }
  const texto = parametros.toString();
  return texto ? `/movimientos?${texto}` : "/movimientos";
}

/**
 * Elegir un segmento. "Ingresos" y "Sin categorizar" no admiten categoría:
 * el selector vuelve a "Todas las categorías".
 */
export function conVista(filtros: Filtros, vista: Vista): Filtros {
  return { vista, categoria: admiteCategoria(vista) ? filtros.categoria : null };
}

/**
 * Elegir una categoría. Si el segmento no la admite ("Ingresos", "Sin
 * categorizar"), vuelve a "Todos".
 */
export function conCategoria(filtros: Filtros, categoria: number | null): Filtros {
  if (categoria === null) return { ...filtros, categoria };
  return { vista: admiteCategoria(filtros.vista) ? filtros.vista : "todos", categoria };
}

export function hayFiltro(filtros: Filtros): boolean {
  return filtros.vista !== "todos" || filtros.categoria !== null;
}

/** Los parámetros de GET /api/movimientos para un mes y unos filtros (la bandeja va aparte). */
export function consultaApi(mes: string | null, filtros: Filtros): ConsultaMovimientos {
  const consulta: ConsultaMovimientos = {};
  if (mes) consulta.mes = mes;
  if (filtros.vista === "gastos") consulta.tipo = "gasto";
  if (filtros.vista === "ingresos") consulta.tipo = "ingreso";
  if (filtros.categoria !== null && admiteCategoria(filtros.vista)) consulta.categoria_id = filtros.categoria;
  return consulta;
}
