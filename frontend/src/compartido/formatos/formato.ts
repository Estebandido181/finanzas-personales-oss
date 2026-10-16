/**
 * Cómo se muestran montos, fechas, horas y meses (TEXTOS.md, "Montos en pesos
 * colombianos" y "Fechas y horas"). Todo es lógica pura, sin React.
 *
 * - Los montos llegan de la API en centavos enteros y solo aquí se pasan a
 *   pesos, sin pasar por decimales (nunca se redondea).
 * - Las fechas de la API son hora de Colombia sin zona ("2026-09-30T07:40:00"):
 *   se leen como texto, sin `Date`, para que la zona del navegador no las mueva.
 * - No se usa `Intl` para los números ni las horas: su salida cambia con la
 *   versión de ICU del navegador (espacios que no se parten, "a. m." o "a.m.",
 *   agrupar o no los miles de 4 cifras). Así el texto es siempre el de la guía.
 */

/** Espacio que no se parte (entre número y "%", y dentro de "a. m."). */
export const NBSP = " ";
/** Signo menos tipográfico (U+2212), no el guion. */
export const MENOS = "−";

export const MESES = [
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

function agruparMiles(entero: string): string {
  return entero.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

/**
 * Centavos a pesos: "$486.250", "$486.250,50", "$0", "−$12.399,50".
 * Con `conSigno`, los positivos llevan "+" ("+$4.800.000"); el cero, nunca.
 */
export function pesos(centavos: number, { conSigno = false }: { conSigno?: boolean } = {}): string {
  if (!Number.isSafeInteger(centavos)) throw new RangeError("El monto debe ser un entero en centavos.");
  const absoluto = Math.abs(centavos);
  const enteros = Math.floor(absoluto / 100);
  const resto = absoluto % 100;
  const numero = agruparMiles(String(enteros)) + (resto === 0 ? "" : `,${String(resto).padStart(2, "0")}`);
  const signo = centavos < 0 ? MENOS : conSigno && centavos > 0 ? "+" : "";
  return `${signo}$${numero}`;
}

/**
 * Un texto partido alrededor de un monto, para escribir el monto en la letra
 * de máquina de escribir (TEXTOS.md: "un monto siempre va en la letra de
 * máquina de escribir" y nunca se parte en dos líneas). Busca en el texto el
 * monto tal como se muestra ("$3.200"); si no está, va todo en `antes`.
 */
export interface TextoConMonto {
  antes: string;
  monto: string | null;
  despues: string;
}

export function partirMonto(texto: string, centavos: number | null): TextoConMonto {
  if (centavos === null) return { antes: texto, monto: null, despues: "" };
  const monto = pesos(centavos);
  // El último que no siga con más cifras ("$3.200" no es el comienzo de "$3.200.000").
  for (let i = texto.lastIndexOf(monto); i >= 0; i = i === 0 ? -1 : texto.lastIndexOf(monto, i - 1)) {
    const despues = texto.slice(i + monto.length);
    if (!/^[.,]?\d/u.test(despues)) return { antes: texto.slice(0, i), monto, despues };
  }
  return { antes: texto, monto: null, despues: "" };
}

/** 26.4 -> "26,4 %" (un decimal, como lo da la API). */
export function porcentaje(valor: number): string {
  return `${valor.toFixed(1).replace(".", ",")}${NBSP}%`;
}

// --- Fechas y horas ---------------------------------------------------------------

export interface FechaHora {
  anio: number;
  mes: number;
  dia: number;
  hora: number;
  minuto: number;
}

const FORMA_FECHA_HORA = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::\d{2})?)?/;

/** "2026-09-30T07:40:00" (o solo la fecha) a sus partes. */
export function leerFechaHora(texto: string): FechaHora {
  const partes = FORMA_FECHA_HORA.exec(texto);
  if (!partes) throw new RangeError(`Fecha no válida: ${texto}`);
  const [, anio, mes, dia, hora = "0", minuto = "0"] = partes;
  return { anio: +anio!, mes: +mes!, dia: +dia!, hora: +hora, minuto: +minuto };
}

/** "7:40 a. m.", "12:00 p. m.", "9:28 p. m." (12 horas, como Colombia). */
export function hora(texto: string): string {
  const { hora: h, minuto } = leerFechaHora(texto);
  const doce = h % 12 === 0 ? 12 : h % 12;
  const sufijo = h < 12 ? "a." : "p.";
  return `${doce}:${String(minuto).padStart(2, "0")}${NBSP}${sufijo}${NBSP}m.`;
}

/** "a las 7:40 a. m.", pero "a la 1:15 p. m." */
function alaHora(texto: string): string {
  const { hora: h } = leerFechaHora(texto);
  return `${h % 12 === 1 ? "a la" : "a las"} ${hora(texto)}`;
}

/** Hoy en Colombia, "aaaa-mm-dd" (la app entera vive en hora de Colombia). */
export function hoyColombia(ahora: Date = new Date()): string {
  // en-CA da justo aaaa-mm-dd.
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Bogota",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(ahora);
}

/** El mes actual en Colombia, "aaaa-mm". */
export function mesActualColombia(ahora: Date = new Date()): string {
  return hoyColombia(ahora).slice(0, 7);
}

function diaAnterior(fecha: string): string {
  const { anio, mes, dia } = leerFechaHora(fecha);
  const d = new Date(Date.UTC(anio, mes - 1, dia - 1));
  return d.toISOString().slice(0, 10);
}

/** "29 de septiembre" (del año de `hoy`) o "29 de septiembre de 2025". */
export function fechaEnFrase(texto: string, hoy: string): string {
  const { anio, mes, dia } = leerFechaHora(texto);
  const base = `${dia} de ${MESES[mes - 1]}`;
  return anio === leerFechaHora(hoy).anio ? base : `${base} de ${anio}`;
}

/**
 * Estado de sincronización correcta: "Sincronizado hoy a las 6:02 a. m.",
 * "Sincronizado ayer a las 11:30 p. m." o "Sincronizado el 27 de septiembre a
 * las 6:00 a. m.".
 */
export function textoSincronizado(terminadaEn: string, hoy: string): string {
  const fecha = terminadaEn.slice(0, 10);
  if (fecha === hoy) return `Sincronizado hoy ${alaHora(terminadaEn)}`;
  if (fecha === diaAnterior(hoy)) return `Sincronizado ayer ${alaHora(terminadaEn)}`;
  return `Sincronizado el ${fechaEnFrase(terminadaEn, hoy)} ${alaHora(terminadaEn)}`;
}

/** "28 de septiembre, 12:00 p. m." (la última sincronización correcta). */
export function fechaYHora(texto: string, hoy: string): string {
  return `${fechaEnFrase(texto, hoy)}, ${hora(texto)}`;
}

// --- Meses -------------------------------------------------------------------------

const FORMA_MES = /^(\d{4})-(\d{2})$/;

export function esMes(texto: string | null | undefined): texto is string {
  if (!texto) return false;
  const partes = FORMA_MES.exec(texto);
  return !!partes && +partes[2]! >= 1 && +partes[2]! <= 12;
}

/** "2026-09" -> "septiembre" (dentro de una frase). */
export function nombreMes(mes: string): string {
  return MESES[+mes.slice(5, 7) - 1]!;
}

/** "2026-09" -> "Septiembre de 2026" (título). */
export function tituloMes(mes: string): string {
  return `${conMayuscula(nombreMes(mes))} de ${mes.slice(0, 4)}`;
}

/** "2026-08" -> "Agosto" (botones del selector de mes). */
export function nombreMesCorto(mes: string): string {
  return conMayuscula(nombreMes(mes));
}
