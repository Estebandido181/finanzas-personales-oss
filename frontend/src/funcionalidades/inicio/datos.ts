import { cantidad } from "@/compartido/textos/cantidad";
/**
 * Lo que muestra Inicio, calculado a partir de las respuestas de la API.
 * Lógica pura (sin React), probada en datos.test.ts.
 *
 * La API decide qué es gasto, cuánto suma cada categoría y los porcentajes
 * (finanzas/reporte.py, lo mismo que la v1): aquí no se vuelve a sumar nada de
 * eso. Solo se decide cómo se ve (largo de las barras, tajadas de la dona,
 * textos de la sincronización).
 */
import type { Esquemas } from "@/compartido/http/cliente";
import { SIN_CATEGORIZAR } from "@/compartido/ui/categorias";

export type Reporte = Esquemas["Reporte"];
export type Movimiento = Esquemas["Movimiento"];
export type GastoCategoria = Esquemas["GastoCategoria"];

// --- Selector de mes ---------------------------------------------------------------

/** La dirección de Inicio para un mes ("/?mes=2026-08"). */
export function rutaDelMes(mes: string): string {
  return `/?mes=${mes}`;
}

// --- Gráfico -----------------------------------------------------------------------

/**
 * Largo de cada barra: proporcional a la categoría mayor, en porcentaje
 * entero de 0 a 100 (la CSP no deja poner un ancho arbitrario en línea: hay
 * una clase por cada entero, ver estilos.css). Un gasto mayor que cero nunca
 * queda en 0: la barra mínima se ve igual (2 px, como en el prototipo).
 */
export function anchoBarra(centavos: number, mayor: number): number {
  if (mayor <= 0 || centavos <= 0) return 0;
  return Math.max(1, Math.min(100, Math.round((centavos / mayor) * 100)));
}

export interface Tajada {
  nombre: string;
  /** Color e ícono; `null` en "Sin categorizar". */
  categoria: GastoCategoria["categoria"];
  /** El `d` del `path` SVG. */
  d: string;
}

const RADIO_EXTERIOR = 110;
const RADIO_INTERIOR = 78;

function punto(radio: number, angulo: number): string {
  // Ángulo 0 = las 12; crece en el sentido del reloj.
  const x = radio * Math.sin(angulo);
  const y = -radio * Math.cos(angulo);
  return `${redondear(x)} ${redondear(y)}`;
}

function redondear(n: number): string {
  const r = Math.round(n * 100) / 100;
  return String(Object.is(r, -0) ? 0 : r);
}

function arco(desde: number, hasta: number): string {
  const grande = hasta - desde > Math.PI ? 1 : 0;
  return [
    `M${punto(RADIO_EXTERIOR, desde)}`,
    `A${RADIO_EXTERIOR} ${RADIO_EXTERIOR} 0 ${grande} 1 ${punto(RADIO_EXTERIOR, hasta)}`,
    `L${punto(RADIO_INTERIOR, hasta)}`,
    `A${RADIO_INTERIOR} ${RADIO_INTERIOR} 0 ${grande} 0 ${punto(RADIO_INTERIOR, desde)}`,
    "Z",
  ].join("");
}

/**
 * Tajadas de la dona (viewBox -120 -120 240 240, anillo de 110 a 78), en el
 * mismo orden de la lista, empezando a las 12 y en el sentido del reloj. El
 * ángulo sale de los centavos (exactos), no del porcentaje redondeado.
 */
export function tajadasDona(categorias: readonly GastoCategoria[]): Tajada[] {
  const total = categorias.reduce((suma, c) => suma + Math.max(0, c.centavos), 0);
  if (total <= 0) return [];
  const tajadas: Tajada[] = [];
  let acumulado = 0;
  for (const { nombre, centavos, categoria } of categorias) {
    if (centavos <= 0) continue;
    const desde = (acumulado / total) * 2 * Math.PI;
    acumulado += centavos;
    const hasta = (acumulado / total) * 2 * Math.PI;
    // Una sola categoría es el anillo entero: un arco de 360° no se puede
    // dibujar, así que va en dos mitades dentro del mismo camino.
    const d =
      hasta - desde >= 2 * Math.PI - 1e-9
        ? arco(0, Math.PI) + arco(Math.PI, 2 * Math.PI)
        : arco(desde, hasta);
    tajadas.push({ nombre, categoria, d });
  }
  return tajadas;
}

export function esSinCategorizar(nombre: string): boolean {
  return nombre === SIN_CATEGORIZAR;
}

// --- Movimientos -------------------------------------------------------------------

/** "Últimos movimientos": 4 filas (SISTEMA.md, "Menos cosas por hoja"). */
export const FILAS_ULTIMOS = 4;

export function ultimosMovimientos(movimientos: readonly Movimiento[]): Movimiento[] {
  // La API ya los manda del más reciente al más antiguo.
  return movimientos.slice(0, FILAS_ULTIMOS);
}

/**
 * Lo que va antes de la hora en la fila: la categoría; si no tiene, "Sin
 * categorizar" (los pendientes: gastos e, ítem 15, ingresos), "Ingreso" o
 * "Ajuste" (lo que no se categoriza).
 */
export function queEs(movimiento: Movimiento): string {
  if (movimiento.categoria) return movimiento.categoria.nombre;
  if (movimiento.es_gasto || movimiento.pendiente) return SIN_CATEGORIZAR;
  return movimiento.tipo === "ingreso" ? "Ingreso" : "Ajuste";
}

export function tituloPendientes(n: number): string {
  return `${cantidad(n, "movimiento", "movimientos")} sin categorizar`;
}

/**
 * Los montos del aviso de pendientes (ítem 15). Lo que sale y lo que entra
 * no se mezclan en una sola cifra: los gastos y los ingresos pendientes van
 * en frases aparte, y una parte que no tiene nada no se menciona. Los montos
 * se dejan en centavos: la pantalla los escribe con `pesos()`.
 */
export type PartesPendientes =
  | { tipo: "gastos"; gastos: number }
  | { tipo: "ingresos"; ingresos: number }
  | { tipo: "ambos"; gastos: number; ingresos: number };

export function partesPendientes(reporte: Pick<Reporte, "pendientes_centavos" | "pendientes_ingresos_centavos">): PartesPendientes {
  const gastos = reporte.pendientes_centavos;
  const ingresos = reporte.pendientes_ingresos_centavos;
  if (ingresos > 0 && gastos > 0) return { tipo: "ambos", gastos, ingresos };
  if (ingresos > 0) return { tipo: "ingresos", ingresos };
  return { tipo: "gastos", gastos };
}
