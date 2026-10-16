/**
 * Lo que muestra "Saldo" (ítem 16), a partir de `GET /api/saldo`. Lógica pura
 * (sin React), probada en datos.test.ts.
 *
 * La API calcula el saldo, el desglose, el total de ajustes del mes y decide
 * qué ingreso se puede borrar (`se_puede_borrar`, regla en finanzas/saldo.py).
 * Aquí no se vuelve a sumar ni a decidir nada de eso: solo se arma el texto.
 * La única "cuenta" es leer lo que escribe el dueño en un campo de monto y
 * pasarlo a centavos, sin decimales de por medio (nunca se redondea).
 */
import type { Esquemas } from "@/compartido/http/cliente";
import { fechaYHora, leerFechaHora, MESES, pesos } from "@/compartido/formatos/formato";

export type Saldo = Esquemas["Saldo"];
export type FilaDelMes = Esquemas["IngresoOAjusteDelMes"];
export type Desglose = Esquemas["DesgloseSaldo"];

/** El mismo tope de la API (`maximum` de los montos en centavos). */
export const MAXIMO_CENTAVOS = 1_000_000_000_000;

// --- Campos de monto ----------------------------------------------------------------

export const TEXTOS_MONTO = {
  formato:
    "Escribe el monto en pesos, con punto para los miles y coma para los centavos, por ejemplo 1.234.567,89.",
  mayorQueCero: "Escribe un monto mayor que cero.",
  /** Inventado (revisión del ítem 16): por encima del tope de la API. */
  demasiadoGrande: "El monto es demasiado grande.",
} as const;

/** "Ese monto tiene una letra O en lugar de un cero…" con el monto corregido como ejemplo. */
export function textoLetraO(corregido: number): string {
  return `Ese monto tiene una letra O en lugar de un cero. Escríbelo solo con números, por ejemplo ${pesos(corregido).slice(1)}.`;
}

export type LecturaMonto = { tipo: "ok"; centavos: number } | { tipo: "error"; texto: string };

// Parte entera sin separador ("1234567") o con punto de miles bien agrupado
// ("1.234.567"); decimales con coma, 1 o 2 cifras. Igual que leer_pesos de la
// v1 (finanzas/saldo.py). Solo cifras ASCII.
const FORMA_PESOS = /^(?<entero>[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+)(?:,(?<decimales>[0-9]{1,2}))?$/;
const LARGO_MAXIMO = 40;

/** Centavos, `null` si no tiene forma de monto o "grande" si pasa el tope de la API. */
function aCentavos(texto: string): number | "grande" | null {
  const partes = FORMA_PESOS.exec(texto);
  if (!partes?.groups) return null;
  const entero = partes.groups.entero!.replace(/\./g, "");
  const decimales = (partes.groups.decimales ?? "").padEnd(2, "0");
  // Sin pasar por decimales: los centavos se arman como texto.
  const centavos = Number(`${entero}${decimales}`);
  return Number.isSafeInteger(centavos) && centavos <= MAXIMO_CENTAVOS ? centavos : "grande";
}

/**
 * Lo que escribe el dueño en "Monto en pesos" o "Saldo real en Bancolombia",
 * en centavos. Acepta `1.234.567,89`, `1.234.567`, `1234567,89` y `1234567`,
 * con `$` y espacios opcionales. Nunca adivina: con letras, dos comas, punto
 * decimal o más de dos decimales, error del campo (TEXTOS.md, "Errores").
 * `permitirCero`: el saldo real puede ser $0; un ingreso, no.
 */
export function leerMonto(texto: string, { permitirCero = false }: { permitirCero?: boolean } = {}): LecturaMonto {
  let limpio = texto.trim();
  if (limpio.startsWith("$")) limpio = limpio.slice(1).trim();
  if (limpio === "") {
    return { tipo: "error", texto: permitirCero ? TEXTOS_MONTO.formato : TEXTOS_MONTO.mayorQueCero };
  }
  if (limpio.length > LARGO_MAXIMO) return { tipo: "error", texto: TEXTOS_MONTO.demasiadoGrande };
  const centavos = aCentavos(limpio);
  if (centavos === "grande") return { tipo: "error", texto: TEXTOS_MONTO.demasiadoGrande };
  if (centavos === null) {
    // Una "O" en lugar de un cero (error típico al escribir en el celular).
    if (/[oO]/.test(limpio)) {
      const corregido = aCentavos(limpio.replace(/[oO]/g, "0"));
      if (typeof corregido === "number" && corregido > 0) return { tipo: "error", texto: textoLetraO(corregido) };
    }
    return { tipo: "error", texto: TEXTOS_MONTO.formato };
  }
  if (centavos === 0 && !permitirCero) return { tipo: "error", texto: TEXTOS_MONTO.mayorQueCero };
  return { tipo: "ok", centavos };
}

// --- Fecha y hora del ingreso -------------------------------------------------------

/** "2026-09-30T09:15:42" a lo que usa un `datetime-local` ("2026-09-30T09:15"). */
export function paraCampoFechaHora(texto: string): string {
  return texto.slice(0, 16);
}

const FORMA_CAMPO_FECHA_HORA = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

/**
 * La fecha y hora elegidas en el campo, en frase ("1 de octubre, 7:45 p. m."):
 * el campo nativo puede mostrarla en números (TEXTOS.md no los admite).
 * `null` si el campo está vacío o incompleto.
 */
export function fechaElegidaEnFrase(valor: string, hoy: string): string | null {
  return FORMA_CAMPO_FECHA_HORA.test(valor) ? fechaYHora(valor, hoy) : null;
}

/** "1 de septiembre de 2026" (siempre con el año). */
export function fechaConAnio(texto: string): string {
  const { anio, mes, dia } = leerFechaHora(texto);
  return `${dia} de ${MESES[mes - 1]} de ${anio}`;
}

/** "Llevas las cuentas desde el 1 de septiembre de 2026." */
export function textoLlevasDesde(fechaInicio: string): string {
  return `Llevas las cuentas desde el ${fechaConAnio(fechaInicio)}.`;
}

/**
 * Revisa la fecha y hora del ingreso antes de enviarla: vacía o anterior a la
 * fecha de inicio. Lo demás (una fecha futura) lo dice la API.
 */
export function revisarFechaHora(valor: string, minima: string | null): string | null {
  if (valor.trim() === "") return "Elige la fecha y hora del ingreso.";
  if (minima && paraCampoFechaHora(valor) < paraCampoFechaHora(minima)) {
    return `La fecha es anterior al ${fechaConAnio(minima)}, cuando empezaste a llevar las cuentas. Elige una fecha desde ese día.`;
  }
  return null;
}

// --- Lista del mes ------------------------------------------------------------------

/** "Ingreso a mano", "Ingreso de Gmail" o "Ajuste". */
export function queEs(fila: Pick<FilaDelMes, "tipo" | "origen">): string {
  if (fila.tipo === "ajuste") return "Ajuste";
  return fila.origen === "manual" ? "Ingreso a mano" : "Ingreso de Gmail";
}

/** "Ingreso a mano · 29 de septiembre, 10:00 a. m." */
export function metaFila(fila: Pick<FilaDelMes, "tipo" | "origen" | "fecha_hora">, hoy: string): string {
  return `${queEs(fila)} · ${fechaYHora(fila.fecha_hora, hoy)}`;
}

export type ClaseMonto = "suma" | "resta" | "neutro";

/** Un monto con signo ("+$150.000", "−$12.399,50", "$0") y su color. */
export function montoConSigno(centavos: number): { texto: string; clase: ClaseMonto } {
  return {
    texto: pesos(centavos, { conSigno: true }),
    clase: centavos > 0 ? "suma" : centavos < 0 ? "resta" : "neutro",
  };
}

/** "en 2 ajustes", "en 1 ajuste"; sin ajustes, nada. */
export function textoCantidadAjustes(cantidad: number): string | null {
  if (cantidad <= 0) return null;
  return cantidad === 1 ? "en 1 ajuste" : `en ${cantidad} ajustes`;
}

/** "Ingresos y ajustes de septiembre". */
export function tituloLista(nombreMes: string): string {
  return `Ingresos y ajustes de ${nombreMes}`;
}

/** Estado vacío de la lista (TEXTOS.md, "Estados vacíos"). */
export function textosListaVacia(nombreMes: string) {
  return {
    titulo: `Sin ingresos ni ajustes en ${nombreMes}`,
    texto: "Los ingresos con aviso de Bancolombia aparecen solos; los demás se registran arriba.",
  };
}

// --- Borrar un ingreso --------------------------------------------------------------

/** "Ingreso borrado. El saldo bajó $150.000." (con el monto que devuelve la API). */
export function textoIngresoBorrado(montoCentavos: number): string {
  return `Ingreso borrado. El saldo bajó ${pesos(montoCentavos)}.`;
}

// --- Resultados de registrar y ajustar ----------------------------------------------

/** "Ingreso de $150.000 registrado." */
export function textoIngresoRegistrado(montoCentavos: number): string {
  return `Ingreso de ${pesos(montoCentavos)} registrado.`;
}

/**
 * "Saldo ajustado: se registró un ajuste de −$12.400." o, si ya coincidía,
 * el aviso informativo de TEXTOS.md (no es un error).
 */
export function resultadoAjuste(ajuste: Pick<Esquemas["Ajuste"], "registrado" | "diferencia_centavos">): {
  tipo: "exito" | "info";
  texto: string;
} {
  if (!ajuste.registrado) {
    return {
      tipo: "info",
      texto: "Tu saldo ya coincide con el de Bancolombia: no se registró ningún ajuste.",
    };
  }
  return {
    tipo: "exito",
    texto: `Saldo ajustado: se registró un ajuste de ${pesos(ajuste.diferencia_centavos, { conSigno: true })}.`,
  };
}

// --- Configurar saldo (saldo inicial y fecha de inicio) -----------------------------

export type Configuracion = Esquemas["ConfiguracionSaldo"];

/** "Configurar saldo", dentro de la sección Saldo (sin la base /app). */
export const RUTA_CONFIGURAR = "/saldo/configurar";

export const TEXTOS_CONFIGURAR = {
  saldoVacio: "Escribe el saldo inicial. Si empiezas en cero, escribe 0.",
  fechaFutura: "La fecha de inicio no puede ser futura. Elige hoy o un día anterior.",
  /** El campo de fecha quedó vacío o incompleto (TEXTOS.md, "Fecha de inicio vacía"). */
  fechaVacia: "Elige la fecha de inicio.",
} as const;

/**
 * Qué muestra "Configurar saldo":
 * - `formulario`: se puede (re)configurar; `inicial` son los valores con que
 *   arrancan los campos (los guardados, o vacío y el día 1 del mes de hoy);
 * - `fijo`: ya hay movimientos, solo lectura. `configuracion` es `null` solo
 *   si hay movimientos sin saldo configurado (no debería pasar: la
 *   sincronización lo exige); entonces no hay cifras que mostrar.
 *
 * Lo decide la API con `configuracion_fija`, la misma regla con la que el PUT
 * rechaza (finanzas/saldo.py, `configuracion_fija`): aquí no se deduce nada
 * del desglose ni de las filas.
 */
export type EstadoConfiguracion =
  | { tipo: "formulario"; inicial: { monto: string; fecha: string } }
  | { tipo: "fijo"; configuracion: Configuracion | null };

export function estadoConfiguracion(
  saldo: Pick<Saldo, "configuracion" | "configuracion_fija" | "hoy">,
): EstadoConfiguracion {
  const { configuracion } = saldo;
  if (saldo.configuracion_fija) return { tipo: "fijo", configuracion };
  if (configuracion === null) {
    return { tipo: "formulario", inicial: { monto: "", fecha: `${saldo.hoy.slice(0, 8)}01` } };
  }
  return {
    tipo: "formulario",
    inicial: { monto: montoParaCampo(configuracion.saldo_inicial_centavos), fecha: configuracion.fecha_inicio },
  };
}

/** Centavos a lo que se escribe en el campo ("1.250.000", "12.345,67"), sin el "$". */
export function montoParaCampo(centavos: number): string {
  return pesos(centavos).replace("$", "");
}

/**
 * "Saldo inicial en pesos": vacío (o solo "$", con o sin espacios) tiene su
 * propio texto; $0 sí vale (cuenta en cero).
 */
export function leerSaldoInicial(texto: string): LecturaMonto {
  if (/^\s*\$?\s*$/.test(texto)) return { tipo: "error", texto: TEXTOS_CONFIGURAR.saldoVacio };
  return leerMonto(texto, { permitirCero: true });
}

/**
 * Revisa la fecha de inicio ("AAAA-MM-DD", la del campo) contra `hoy` (el de
 * la API, en Colombia: la zona del navegador no cuenta). La API lo vuelve a
 * comprobar al guardar.
 */
export function revisarFechaInicio(valor: string, hoy: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(valor)) return TEXTOS_CONFIGURAR.fechaVacia;
  return valor > hoy ? TEXTOS_CONFIGURAR.fechaFutura : null;
}

/** "Saldo inicial guardado: $1.250.000 desde el 1 de septiembre de 2026." */
export function textoSaldoInicialGuardado(configuracion: Configuracion): string {
  return `Saldo inicial guardado: ${pesos(configuracion.saldo_inicial_centavos)} desde el ${fechaConAnio(configuracion.fecha_inicio)}.`;
}

/** El aviso del estado fijo (TEXTOS.md, "Configurar saldo"). */
export function textoSaldoFijo(fechaInicio: string): string {
  return `Ya hay movimientos desde el ${fechaConAnio(fechaInicio)}, así que el saldo inicial y la fecha de inicio quedaron fijos. Si el saldo no coincide con el de Bancolombia, corrígelo con un ajuste de saldo.`;
}
