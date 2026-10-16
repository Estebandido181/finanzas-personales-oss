/** "Configurar saldo" (ítem 16): lógica pura de saldo/datos.ts. Datos inventados. */
import { describe, expect, it } from "vitest";
import { saldoInventado, saldoSinConfigurar } from "@/pruebas/saldo-inventado";
import {
  estadoConfiguracion,
  leerSaldoInicial,
  montoParaCampo,
  revisarFechaInicio,
  TEXTOS_CONFIGURAR,
  TEXTOS_MONTO,
  textoSaldoFijo,
  textoSaldoInicialGuardado,
} from "@/funcionalidades/saldo/datos";

/** Configurado y sin ningún movimiento: la API dice `configuracion_fija: false`. */
function configuradoSinMovimientos(saldoInicial = 125_000_000) {
  return saldoInventado({
    configuracion: { saldo_inicial_centavos: saldoInicial, fecha_inicio: "2026-09-01" },
    configuracion_fija: false,
    saldo_centavos: saldoInicial,
    desglose: { saldo_inicial_centavos: saldoInicial, ingresos_centavos: 0, gastos_centavos: 0, ajustes_centavos: 0 },
    del_mes: [],
    ajustes_del_mes: { total_centavos: 0, cantidad: 0 },
    ultimos: [],
  });
}

describe("estadoConfiguracion (solo configuracion_fija de la API)", () => {
  it("sin configurar: formulario vacío con el día 1 del mes de hoy", () => {
    expect(estadoConfiguracion(saldoSinConfigurar())).toEqual({
      tipo: "formulario",
      inicial: { monto: "", fecha: "2026-09-01" },
    });
    expect(estadoConfiguracion({ ...saldoSinConfigurar(), hoy: "2026-10-02" })).toEqual({
      tipo: "formulario",
      inicial: { monto: "", fecha: "2026-10-01" },
    });
  });

  it("configurado y no fija: formulario con lo guardado (se puede volver a configurar)", () => {
    expect(estadoConfiguracion(configuradoSinMovimientos(123_456_789))).toEqual({
      tipo: "formulario",
      inicial: { monto: "1.234.567,89", fecha: "2026-09-01" },
    });
  });

  it("fija: solo lectura, con lo guardado", () => {
    expect(estadoConfiguracion(saldoInventado())).toEqual({
      tipo: "fijo",
      configuracion: { saldo_inicial_centavos: 125_000_000, fecha_inicio: "2026-09-01" },
    });
  });

  it("fija aunque el desglose y las filas estén vacíos (p. ej. un movimiento anterior a la fecha de inicio)", () => {
    expect(estadoConfiguracion({ ...configuradoSinMovimientos(), configuracion_fija: true }).tipo).toBe("fijo");
  });

  it("no fija aunque el desglose o las filas digan otra cosa: manda la API", () => {
    expect(estadoConfiguracion({ ...saldoInventado(), configuracion_fija: false }).tipo).toBe("formulario");
  });

  it("fija sin configuración (movimientos sin saldo): fijo, sin cifras", () => {
    expect(estadoConfiguracion({ ...saldoSinConfigurar(), configuracion_fija: true })).toEqual({
      tipo: "fijo",
      configuracion: null,
    });
  });
});

describe("leerSaldoInicial (pesos a centavos, sin floats)", () => {
  it.each([
    ["1.250.000", 125_000_000],
    ["1250000", 125_000_000],
    ["$ 1.250.000,5", 125_000_050],
    ["0", 0],
    ["0,01", 1],
    ["999.999.999,99", 99_999_999_999],
  ])("%s → %i centavos", (texto, centavos) => {
    expect(leerSaldoInicial(texto)).toEqual({ tipo: "ok", centavos });
  });

  it("vacío tiene su propio texto (y cero sí se permite)", () => {
    expect(leerSaldoInicial("   ")).toEqual({ tipo: "error", texto: TEXTOS_CONFIGURAR.saldoVacio });
  });

  it.each(["$", " $ ", "$   "])("solo «%s» cuenta como vacío, no como formato", (texto) => {
    expect(leerSaldoInicial(texto)).toEqual({ tipo: "error", texto: TEXTOS_CONFIGURAR.saldoVacio });
  });

  it("una letra O en lugar de un cero lo explica con el monto corregido", () => {
    expect(leerSaldoInicial("1.25O.000")).toEqual({
      tipo: "error",
      texto: "Ese monto tiene una letra O en lugar de un cero. Escríbelo solo con números, por ejemplo 1.250.000.",
    });
  });

  it.each(["1.250.000.5", "1,250,000", "-5.000", "1.25.000", "doce"])("%s no es un monto", (texto) => {
    expect(leerSaldoInicial(texto)).toEqual({ tipo: "error", texto: TEXTOS_MONTO.formato });
  });

  it("por encima del tope de la API, demasiado grande", () => {
    expect(leerSaldoInicial("10.000.000.001")).toEqual({ tipo: "error", texto: TEXTOS_MONTO.demasiadoGrande });
  });
});

describe("revisarFechaInicio", () => {
  it("hoy y antes valen; mañana es futura", () => {
    expect(revisarFechaInicio("2026-09-30", "2026-09-30")).toBeNull();
    expect(revisarFechaInicio("2025-01-01", "2026-09-30")).toBeNull();
    expect(revisarFechaInicio("2026-10-01", "2026-09-30")).toBe(TEXTOS_CONFIGURAR.fechaFutura);
  });

  it("vacía o incompleta pide elegirla", () => {
    expect(revisarFechaInicio("", "2026-09-30")).toBe(TEXTOS_CONFIGURAR.fechaVacia);
    expect(revisarFechaInicio("2026-09", "2026-09-30")).toBe(TEXTOS_CONFIGURAR.fechaVacia);
  });
});

describe("textos", () => {
  it("montoParaCampo es lo que se escribiría en el campo", () => {
    expect(montoParaCampo(125_000_000)).toBe("1.250.000");
    expect(montoParaCampo(0)).toBe("0");
    expect(montoParaCampo(1_234_567)).toBe("12.345,67");
  });

  it("resultado y aviso del estado fijo", () => {
    expect(textoSaldoInicialGuardado({ saldo_inicial_centavos: 125_000_000, fecha_inicio: "2026-09-01" })).toBe(
      "Saldo inicial guardado: $1.250.000 desde el 1 de septiembre de 2026.",
    );
    expect(textoSaldoFijo("2026-09-01")).toBe(
      "Ya hay movimientos desde el 1 de septiembre de 2026, así que el saldo inicial y la fecha de inicio quedaron fijos. Si el saldo no coincide con el de Bancolombia, corrígelo con un ajuste de saldo.",
    );
  });
});
