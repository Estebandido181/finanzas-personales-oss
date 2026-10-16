import { describe, expect, it } from "vitest";
import { NBSP } from "@/compartido/formatos/formato";
import {
  fechaElegidaEnFrase,
  leerMonto,
  metaFila,
  montoConSigno,
  paraCampoFechaHora,
  queEs,
  resultadoAjuste,
  revisarFechaHora,
  TEXTOS_MONTO,
  textoCantidadAjustes,
  textoIngresoBorrado,
  textoIngresoRegistrado,
  textoLlevasDesde,
  textosListaVacia,
  tituloLista,
} from "@/funcionalidades/saldo/datos";

describe("leerMonto (pesos a centavos, sin redondear)", () => {
  it.each([
    ["150.000", 15_000_000],
    ["150000", 15_000_000],
    ["1.234.567,89", 123_456_789],
    ["1234567,89", 123_456_789],
    ["0,05", 5],
    ["0,5", 50],
    ["$ 4.730.000", 473_000_000],
    ["  12.399,50 ", 1_239_950],
    ["10.000.000.000", 1_000_000_000_000],
  ])("%s → %d centavos", (texto, centavos) => {
    expect(leerMonto(texto)).toEqual({ tipo: "ok", centavos });
  });

  it.each([
    "1.2345", // miles mal agrupados
    "1234.56", // punto como decimal
    "1,234", // tres decimales
    "1,2,3", // dos comas
    "-5.000", // negativo
    "−5.000", // signo menos tipográfico
    "5 000",
    "abc",
    "١٢٣", // cifras de otro alfabeto
  ])("rechaza %s con el texto de formato", (texto) => {
    expect(leerMonto(texto)).toEqual({ tipo: "error", texto: TEXTOS_MONTO.formato });
  });

  it("por encima del tope de la API: «El monto es demasiado grande.»", () => {
    for (const texto of ["10.000.000.000,01", "99999999999999999999", "1".repeat(41)]) {
      expect(leerMonto(texto)).toEqual({ tipo: "error", texto: TEXTOS_MONTO.demasiadoGrande });
    }
  });

  it("una O en lugar de un cero lo dice y da el monto corregido de ejemplo", () => {
    expect(leerMonto("4.73O.000")).toEqual({
      tipo: "error",
      texto: "Ese monto tiene una letra O en lugar de un cero. Escríbelo solo con números, por ejemplo 4.730.000.",
    });
    expect(leerMonto("1o,5o")).toMatchObject({ texto: expect.stringContaining("por ejemplo 10,50.") });
  });

  it("un ingreso vacío o en cero pide un monto mayor que cero", () => {
    expect(leerMonto("")).toEqual({ tipo: "error", texto: TEXTOS_MONTO.mayorQueCero });
    expect(leerMonto("0")).toEqual({ tipo: "error", texto: TEXTOS_MONTO.mayorQueCero });
    expect(leerMonto("0,00")).toEqual({ tipo: "error", texto: TEXTOS_MONTO.mayorQueCero });
  });

  it("el saldo real puede ser $0, pero no vacío", () => {
    expect(leerMonto("0", { permitirCero: true })).toEqual({ tipo: "ok", centavos: 0 });
    expect(leerMonto(" ", { permitirCero: true })).toEqual({ tipo: "error", texto: TEXTOS_MONTO.formato });
  });
});

describe("fechas", () => {
  it("lleva la hora de la API al campo datetime-local", () => {
    expect(paraCampoFechaHora("2026-09-30T09:15:42")).toBe("2026-09-30T09:15");
  });

  it("la fecha elegida en frase, sin números; nada si el campo está incompleto", () => {
    expect(fechaElegidaEnFrase("2026-10-01T19:45", "2026-10-01")).toBe(`1 de octubre, 7:45${NBSP}p.${NBSP}m.`);
    expect(fechaElegidaEnFrase("2025-12-31T08:05", "2026-10-01")).toBe(
      `31 de diciembre de 2025, 8:05${NBSP}a.${NBSP}m.`,
    );
    expect(fechaElegidaEnFrase("", "2026-10-01")).toBeNull();
  });

  it("«Llevas las cuentas desde…» siempre con el año", () => {
    expect(textoLlevasDesde("2026-09-01")).toBe("Llevas las cuentas desde el 1 de septiembre de 2026.");
  });

  it("rechaza una fecha vacía o anterior a la de inicio; acepta desde las 00:00 de ese día", () => {
    const minima = "2026-09-01T00:00:00";
    expect(revisarFechaHora("", minima)).toBe("Elige la fecha y hora del ingreso.");
    expect(revisarFechaHora("2026-08-31T23:59", minima)).toBe(
      "La fecha es anterior al 1 de septiembre de 2026, cuando empezaste a llevar las cuentas. Elige una fecha desde ese día.",
    );
    expect(revisarFechaHora("2026-09-01T00:00", minima)).toBeNull();
    expect(revisarFechaHora("2026-09-30T10:00", null)).toBeNull();
  });
});

describe("lista del mes", () => {
  it("dice qué es cada fila", () => {
    expect(queEs({ tipo: "ingreso", origen: "manual" })).toBe("Ingreso a mano");
    expect(queEs({ tipo: "ingreso", origen: "gmail" })).toBe("Ingreso de Gmail");
    expect(queEs({ tipo: "ajuste", origen: "manual" })).toBe("Ajuste");
  });

  it("arma la línea de la fila con fecha y hora", () => {
    expect(metaFila({ tipo: "ingreso", origen: "manual", fecha_hora: "2026-09-29T10:00:00" }, "2026-09-30")).toBe(
      `Ingreso a mano · 29 de septiembre, 10:00${NBSP}a.${NBSP}m.`,
    );
    expect(metaFila({ tipo: "ajuste", origen: "manual", fecha_hora: "2026-09-20T19:30:00" }, "2026-09-30")).toBe(
      `Ajuste · 20 de septiembre, 7:30${NBSP}p.${NBSP}m.`,
    );
  });

  it("los montos llevan su signo y su color", () => {
    expect(montoConSigno(15_000_000)).toEqual({ texto: "+$150.000", clase: "suma" });
    expect(montoConSigno(-1_239_950)).toEqual({ texto: "−$12.399,50", clase: "resta" });
    expect(montoConSigno(0)).toEqual({ texto: "$0", clase: "neutro" });
  });

  it("total de ajustes: «en 2 ajustes», «en 1 ajuste» y nada sin ajustes", () => {
    expect(textoCantidadAjustes(2)).toBe("en 2 ajustes");
    expect(textoCantidadAjustes(1)).toBe("en 1 ajuste");
    expect(textoCantidadAjustes(0)).toBeNull();
  });

  it("título y estado vacío con el nombre del mes", () => {
    expect(tituloLista("septiembre")).toBe("Ingresos y ajustes de septiembre");
    expect(textosListaVacia("septiembre").titulo).toBe("Sin ingresos ni ajustes en septiembre");
  });
});

describe("textos de resultado", () => {
  it("borrar: el resultado dice el monto exacto", () => {
    expect(textoIngresoBorrado(15_000_050)).toBe("Ingreso borrado. El saldo bajó $150.000,50.");
  });

  it("registrar y ajustar", () => {
    expect(textoIngresoRegistrado(15_000_000)).toBe("Ingreso de $150.000 registrado.");
    expect(resultadoAjuste({ registrado: true, diferencia_centavos: -1_240_000 })).toEqual({
      tipo: "exito",
      texto: "Saldo ajustado: se registró un ajuste de −$12.400.",
    });
    expect(resultadoAjuste({ registrado: true, diferencia_centavos: 500_000 }).texto).toBe(
      "Saldo ajustado: se registró un ajuste de +$5.000.",
    );
    expect(resultadoAjuste({ registrado: false, diferencia_centavos: 0 })).toEqual({
      tipo: "info",
      texto: "Tu saldo ya coincide con el de Bancolombia: no se registró ningún ajuste.",
    });
  });
});
