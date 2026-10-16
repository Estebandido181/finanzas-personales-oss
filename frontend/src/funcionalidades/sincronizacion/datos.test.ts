import { describe, expect, it } from "vitest";
import { NBSP } from "@/compartido/formatos/formato";
import { fechaDelCorreo, ordenarPorFecha, textoReproceso, type ContadoresReproceso } from "@/funcionalidades/sincronizacion/datos";

function contadores(parcial: Partial<ContadoresReproceso>): ContadoresReproceso {
  return {
    revisados: 0,
    movimientos_creados: 0,
    siguen_sin_reconocerse: 0,
    ya_registrados: 0,
    errores: 0,
    ...parcial,
  };
}

describe("fechaDelCorreo", () => {
  it("siempre lleva el año y la hora de 12 horas", () => {
    expect(fechaDelCorreo("2026-09-29T21:28:00")).toBe(`29 de septiembre de 2026, 9:28${NBSP}p.${NBSP}m.`);
    expect(fechaDelCorreo("2026-09-03T18:47:00")).toBe(`3 de septiembre de 2026, 6:47${NBSP}p.${NBSP}m.`);
    expect(fechaDelCorreo("2025-01-05T00:05:00")).toBe(`5 de enero de 2025, 12:05${NBSP}a.${NBSP}m.`);
  });
});

describe("ordenarPorFecha", () => {
  it("el más reciente primero y sin fecha al final", () => {
    const c = (gmail_id: string, fecha: string | null) => ({ gmail_id, fecha, asunto: gmail_id });
    expect(ordenarPorFecha([c("a", "2026-09-03T10:00:00"), c("b", null), c("c", "2026-09-29T10:00:00")]).map((x) => x.gmail_id)).toEqual(["c", "a", "b"]);
    expect(fechaDelCorreo(null)).toBe("Sin fecha");
  });
});

describe("textoReproceso", () => {
  it("el ejemplo del prototipo", () => {
    expect(textoReproceso(contadores({ revisados: 4, movimientos_creados: 1, siguen_sin_reconocerse: 3 }))).toEqual({
      titulo: "Se volvieron a procesar 4 correos.",
      detalle: "1 creó un movimiento nuevo; 3 siguen sin reconocerse.",
      tipo: "exito",
    });
  });

  it("singulares y plurales", () => {
    expect(textoReproceso(contadores({ revisados: 1, siguen_sin_reconocerse: 1 }))).toMatchObject({
      titulo: "Se volvió a procesar 1 correo.",
      detalle: "No creó ningún movimiento nuevo; 1 sigue sin reconocerse.",
    });
    expect(textoReproceso(contadores({ revisados: 3, movimientos_creados: 3 }))).toMatchObject({
      detalle: "3 crearon un movimiento nuevo.",
    });
  });

  it("menciona los ya registrados y los errores, y con errores no es de éxito", () => {
    const texto = textoReproceso(
      contadores({ revisados: 5, movimientos_creados: 1, ya_registrados: 1, errores: 2, siguen_sin_reconocerse: 1 }),
    );
    expect(texto.detalle).toBe(
      "1 creó un movimiento nuevo; 1 sigue sin reconocerse; 1 ya estaba registrado; 2 no se pudieron leer y siguen en la lista.",
    );
    expect(texto.tipo).toBe("info");
  });

  it("nunca dice que el lector no los reconoce (incluye los anteriores a la fecha de inicio)", () => {
    const texto = textoReproceso(contadores({ revisados: 2, siguen_sin_reconocerse: 2 }));
    expect(`${texto.titulo} ${texto.detalle}`).not.toMatch(/lector/i);
  });

  it("sin correos revisados", () => {
    expect(textoReproceso(contadores({}))).toMatchObject({ titulo: "No había correos para volver a procesar." });
  });
});
