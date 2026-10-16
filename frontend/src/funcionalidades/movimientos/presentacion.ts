import type { Movimiento } from "./datos";
import { pesos } from "@/compartido/formatos/formato";

/** ¿Lleva la fila el cuadro de categoría? Sí si tiene una o la espera (pendiente). */
export function llevaMarcaDeCategoria(movimiento: Movimiento): boolean {
  return movimiento.categoria !== null || movimiento.es_gasto || movimiento.pendiente;
}

/** El monto de la fila: los gastos en tinta; ingresos con "+", ajustes con su signo. */
export function montoDeFila(movimiento: Movimiento): { texto: string; clase: "gasto" | "suma" | "resta" } {
  if (movimiento.es_gasto) return { texto: pesos(movimiento.monto_centavos), clase: "gasto" };
  const texto = pesos(movimiento.monto_centavos, { conSigno: true });
  return { texto, clase: movimiento.monto_centavos < 0 ? "resta" : "suma" };
}
