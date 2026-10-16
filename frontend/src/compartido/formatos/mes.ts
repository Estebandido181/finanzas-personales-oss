import type { Esquemas } from "@/compartido/http/cliente";
type Reporte = Esquemas["Reporte"];

/**
 * ¿Se ofrece "mes siguiente"? Nunca en el mes actual (ni en uno futuro, si
 * alguien escribe la dirección a mano). `mesActual` es "aaaa-mm" de Colombia.
 */
export function mesSiguienteVisible(reporte: Reporte, mesActual: string): string | null {
  if (reporte.es_mes_actual || !reporte.mes_siguiente) return null;
  return reporte.mes < mesActual ? reporte.mes_siguiente : null;
}
