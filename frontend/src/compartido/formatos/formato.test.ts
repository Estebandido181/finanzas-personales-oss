import { describe, expect, it } from "vitest";
import {
  esMes,
  fechaEnFrase,
  fechaYHora,
  hora,
  hoyColombia,
  mesActualColombia,
  nombreMes,
  nombreMesCorto,
  partirMonto,
  pesos,
  porcentaje,
  textoSincronizado,
  tituloMes,
} from "@/compartido/formatos/formato";

describe("pesos (TEXTOS.md, «Montos»)", () => {
  it.each([
    [0, "$0"],
    [5, "$0,05"],
    [50, "$0,50"],
    [850_000, "$8.500"],
    [4_862_500, "$48.625"],
    [48_625_050, "$486.250,50"],
    [184_245_000, "$1.842.450"],
    [-1_239_950, "−$12.399,50"],
    [-1_840_000, "−$18.400"],
    [100, "$1"],
    [99_999_999_900, "$999.999.999"],
  ])("%i centavos -> %s", (centavos, texto) => {
    expect(pesos(centavos)).toBe(texto);
  });

  it("el menos es el tipográfico (U+2212), no el guion", () => {
    expect(pesos(-100).codePointAt(0)).toBe(0x2212);
  });

  it("con signo: + para lo que suma, nunca para el cero", () => {
    expect(pesos(535_000_000, { conSigno: true })).toBe("+$5.350.000");
    expect(pesos(0, { conSigno: true })).toBe("$0");
    expect(pesos(-1_840_000, { conSigno: true })).toBe("−$18.400");
  });

  it("un total sin centavos no los muestra aunque sus sumandos sí", () => {
    expect(pesos(1_239_950 + 600_050)).toBe("$18.400");
  });

  it("rechaza lo que no es un entero de centavos", () => {
    expect(() => pesos(1.5)).toThrow(RangeError);
    expect(() => pesos(Number.NaN)).toThrow(RangeError);
  });
});

describe("porcentaje", () => {
  it("un decimal con coma y espacio que no se parte", () => {
    expect(porcentaje(26.4)).toBe("26,4 %");
    expect(porcentaje(100)).toBe("100,0 %");
    expect(porcentaje(1.5)).toBe("1,5 %");
  });
});

describe("horas y fechas (hora de Colombia, sin zona)", () => {
  it.each([
    ["2026-09-30T07:40:00", "7:40 a. m."],
    ["2026-09-30T00:05:00", "12:05 a. m."],
    ["2026-09-30T12:00:00", "12:00 p. m."],
    ["2026-09-30T21:28:59", "9:28 p. m."],
  ])("%s -> %s", (texto, esperado) => {
    expect(hora(texto)).toBe(esperado);
  });

  it("fecha en frase: sin año si es del año en curso", () => {
    expect(fechaEnFrase("2026-09-28T12:00:00", "2026-09-30")).toBe("28 de septiembre");
    expect(fechaEnFrase("2025-12-31T12:00:00", "2026-01-02")).toBe("31 de diciembre de 2025");
  });

  it("fecha y hora de la última correcta", () => {
    expect(fechaYHora("2026-09-28T12:00:00", "2026-09-30")).toBe("28 de septiembre, 12:00 p. m.");
  });

  it("estado de sincronización: hoy, ayer o la fecha", () => {
    expect(textoSincronizado("2026-09-30T06:02:00", "2026-09-30")).toBe(
      "Sincronizado hoy a las 6:02 a. m.",
    );
    expect(textoSincronizado("2026-09-29T23:30:00", "2026-09-30")).toBe(
      "Sincronizado ayer a las 11:30 p. m.",
    );
    expect(textoSincronizado("2026-09-27T06:00:00", "2026-09-30")).toBe(
      "Sincronizado el 27 de septiembre a las 6:00 a. m.",
    );
    // "a la una", no "a las una".
    expect(textoSincronizado("2026-09-30T13:15:00", "2026-09-30")).toBe(
      "Sincronizado hoy a la 1:15 p. m.",
    );
  });

  it("ayer también cruza meses y años", () => {
    expect(textoSincronizado("2026-08-31T22:00:00", "2026-09-01")).toMatch(/^Sincronizado ayer/);
    expect(textoSincronizado("2025-12-31T22:00:00", "2026-01-01")).toMatch(/^Sincronizado ayer/);
  });

  it("hoy y el mes actual salen en hora de Colombia, no en la del navegador", () => {
    // 2026-10-01 03:00 UTC es todavía el 30 de septiembre en Colombia (UTC−5).
    const momento = new Date("2026-10-01T03:00:00Z");
    expect(hoyColombia(momento)).toBe("2026-09-30");
    expect(mesActualColombia(momento)).toBe("2026-09");
  });
});

describe("meses", () => {
  it("títulos y nombres", () => {
    expect(tituloMes("2026-09")).toBe("Septiembre de 2026");
    expect(nombreMes("2026-09")).toBe("septiembre");
    expect(nombreMesCorto("2026-08")).toBe("Agosto");
  });

  it("reconoce solo aaaa-mm válidos", () => {
    expect(esMes("2026-09")).toBe(true);
    expect(esMes("2026-13")).toBe(false);
    expect(esMes("2026-9")).toBe(false);
    expect(esMes("septiembre")).toBe(false);
    expect(esMes(null)).toBe(false);
  });
});

describe("partirMonto (ítem 17: el monto de una regla en su letra)", () => {
  it("encuentra el monto como se muestra", () => {
    expect(partirMonto("transferencia de $3.200", 320_000)).toEqual({
      antes: "transferencia de ",
      monto: "$3.200",
      despues: "",
    });
    expect(partirMonto("ingreso de «X» por $400.000, va a Préstamos", 40_000_000)).toEqual({
      antes: "ingreso de «X» por ",
      monto: "$400.000",
      despues: ", va a Préstamos",
    });
    expect(partirMonto("compra de $12.399,50", 1_239_950).monto).toBe("$12.399,50");
  });

  it("no confunde un monto con el comienzo de otro más grande", () => {
    expect(partirMonto("transferencia de $3.200.000", 320_000)).toEqual({
      antes: "transferencia de $3.200.000",
      monto: null,
      despues: "",
    });
    expect(partirMonto("de $3.200 y no $3.200,50", 320_000)).toEqual({
      antes: "de ",
      monto: "$3.200",
      despues: " y no $3.200,50",
    });
  });

  it("sin monto, o si no está, va todo en `antes`", () => {
    expect(partirMonto("compra en «X»", null)).toEqual({ antes: "compra en «X»", monto: null, despues: "" });
    expect(partirMonto("Las dos cosas juntas", 620_000).monto).toBeNull();
  });
});
