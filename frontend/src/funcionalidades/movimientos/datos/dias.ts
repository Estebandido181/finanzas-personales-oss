import { leerFechaHora } from "@/compartido/formatos/formato";
import type { Movimiento } from "./tipos";

// --- Días --------------------------------------------------------------------------------

const DIAS_SEMANA = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"] as const;
const MESES = [
  "enero",
  "febrero",
  "marzo",
  "abril",
  "mayo",
  "junio",
  "julio",
  "agosto",
  "septiembre",
  "octubre",
  "noviembre",
  "diciembre",
] as const;

function conMayuscula(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

/** Día de la semana de una fecha "aaaa-mm-dd" (calendario, sin zona horaria). */
function diaSemana(fecha: string): string {
  const { anio, mes, dia } = leerFechaHora(fecha);
  return DIAS_SEMANA[new Date(Date.UTC(anio, mes - 1, dia)).getUTCDay()]!;
}

function diaAnterior(fecha: string): string {
  const { anio, mes, dia } = leerFechaHora(fecha);
  return new Date(Date.UTC(anio, mes - 1, dia - 1)).toISOString().slice(0, 10);
}

/**
 * Encabezado de día (TEXTOS.md, "Fechas y horas"): "Martes 29 de septiembre",
 * "Hoy, miércoles 30 de septiembre", "Ayer, martes 29 de septiembre"; de otro
 * año, con el año.
 */
export function tituloDia(fecha: string, hoy: string): string {
  const { anio, mes, dia } = leerFechaHora(fecha);
  const anioActual = leerFechaHora(hoy).anio;
  const base = `${diaSemana(fecha)} ${dia} de ${MESES[mes - 1]}${anio === anioActual ? "" : ` de ${anio}`}`;
  if (fecha === hoy) return `Hoy, ${base}`;
  if (fecha === diaAnterior(hoy)) return `Ayer, ${base}`;
  return conMayuscula(base);
}

export interface Dia {
  fecha: string;
  titulo: string;
  /**
   * Lo gastado ese día (compras y transferencias), de la lista completa del
   * mes; `null` en la bandeja (solo se ven los pendientes).
   */
  gastadoCentavos: number | null;
  movimientos: Movimiento[];
}

/**
 * Agrupa por día, del más reciente al más antiguo (la API ya los manda así).
 * El "Gastado" de cada día se suma sobre `delMes` (todo el día), no solo
 * sobre las filas visibles: con un filtro, la cifra del día no cambia. Sin
 * `delMes` (la bandeja), no hay cifra.
 */
export function agruparPorDia(
  visibles: readonly Movimiento[],
  delMes: readonly Movimiento[] | null,
  hoy: string,
): Dia[] {
  const gastado = new Map<string, number>();
  for (const m of delMes ?? []) {
    if (!m.es_gasto) continue;
    const fecha = m.fecha_hora.slice(0, 10);
    gastado.set(fecha, (gastado.get(fecha) ?? 0) + m.monto_centavos);
  }
  const dias: Dia[] = [];
  for (const m of visibles) {
    const fecha = m.fecha_hora.slice(0, 10);
    let dia = dias.at(-1);
    if (!dia || dia.fecha !== fecha) {
      dia = {
        fecha,
        titulo: tituloDia(fecha, hoy),
        gastadoCentavos: delMes ? (gastado.get(fecha) ?? 0) : null,
        movimientos: [],
      };
      dias.push(dia);
    }
    dia.movimientos.push(m);
  }
  return dias;
}
