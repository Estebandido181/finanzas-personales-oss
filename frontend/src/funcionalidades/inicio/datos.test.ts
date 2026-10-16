import { describe, expect, it } from "vitest";
import {
  movimientoInventado,
  movimientosInventados,
  reporteInventado,
} from "@/pruebas/inicio-inventado";

import { anchoBarra, FILAS_ULTIMOS, partesPendientes, queEs, rutaDelMes, tajadasDona, tituloPendientes, ultimosMovimientos } from "@/funcionalidades/inicio/datos";
import { llevaMarcaDeCategoria, montoDeFila } from "@/funcionalidades/movimientos/presentacion";
import { mesSiguienteVisible } from "@/compartido/formatos/mes";

describe("selector de mes", () => {
  it("en el mes actual no hay mes siguiente, aunque la API lo mande", () => {
    expect(mesSiguienteVisible(reporteInventado(), "2026-09")).toBeNull();
  });

  it("en un mes pasado sí", () => {
    const agosto = reporteInventado({ mes: "2026-08", es_mes_actual: false, mes_siguiente: "2026-09" });
    expect(mesSiguienteVisible(agosto, "2026-09")).toBe("2026-09");
  });

  it("en un mes futuro (dirección escrita a mano) tampoco", () => {
    const futuro = reporteInventado({ mes: "2026-11", es_mes_actual: false, mes_siguiente: "2026-12" });
    expect(mesSiguienteVisible(futuro, "2026-09")).toBeNull();
  });

  it("sin mes siguiente en la API (2099-12), nada", () => {
    const ultimo = reporteInventado({ mes: "2026-08", es_mes_actual: false, mes_siguiente: null });
    expect(mesSiguienteVisible(ultimo, "2026-09")).toBeNull();
  });

  it("la dirección lleva el mes en la consulta", () => {
    expect(rutaDelMes("2026-08")).toBe("/?mes=2026-08");
  });
});

describe("gráfico", () => {
  it("las barras son proporcionales a la mayor, en enteros de 0 a 100", () => {
    expect(anchoBarra(48_624_950, 48_624_950)).toBe(100);
    expect(anchoBarra(41_280_000, 48_624_950)).toBe(85);
    expect(anchoBarra(2_770_000, 48_624_950)).toBe(6);
  });

  it("un gasto diminuto no desaparece; cero y total cero dan 0", () => {
    expect(anchoBarra(1, 48_624_950)).toBe(1);
    expect(anchoBarra(0, 100)).toBe(0);
    expect(anchoBarra(5, 0)).toBe(0);
  });

  it("la dona empieza a las 12, va en el orden de la lista y cierra el anillo", () => {
    const tajadas = tajadasDona(reporteInventado().por_categoria);
    expect(tajadas.map((t) => t.nombre)).toEqual(reporteInventado().por_categoria.map((c) => c.nombre));
    expect(tajadas[0]!.d.startsWith("M0 -110A110 110")).toBe(true);
    // La última termina donde empezó la primera (arriba, en 0 -110).
    expect(tajadas.at(-1)!.d).toMatch(/A110 110 0 0 1 0 -110L0 -78/);
    // Como en el prototipo: Mercado (26,4 %) termina en 109.58 9.6.
    expect(tajadas[0]!.d).toContain("109.58 9.6");
  });

  it("una sola categoría es el anillo entero (dos mitades)", () => {
    const [tajada] = tajadasDona([{ nombre: "Mercado", centavos: 100, porcentaje: 100, categoria: { id: 1, nombre: "Mercado", clase: "gasto", color: "cat-mercado", icono: "shopping-basket" } }]);
    expect(tajada!.d.match(/M/g)).toHaveLength(2);
  });

  it("sin gastos no hay tajadas", () => {
    expect(tajadasDona([])).toEqual([]);
  });
});

describe("últimos movimientos", () => {
  it(`muestra ${FILAS_ULTIMOS}, en el orden de la API`, () => {
    const todos = movimientosInventados();
    expect(ultimosMovimientos(todos)).toEqual(todos.slice(0, 4));
  });

  it("qué es y cómo va el monto", () => {
    const [panaderia, transporte, , , ingreso] = movimientosInventados();
    expect(queEs(panaderia!)).toBe("Sin categorizar");
    expect(queEs(transporte!)).toBe("Transporte");
    expect(queEs(ingreso!)).toBe("Ingreso");
    expect(montoDeFila(panaderia!)).toEqual({ texto: "$8.500", clase: "gasto" });
    expect(montoDeFila(ingreso!)).toEqual({ texto: "+$4.800.000", clase: "suma" });
    const ajuste = movimientoInventado({
      tipo: "ajuste",
      es_gasto: false,
      monto_centavos: -1_840_000,
      pendiente: false,
      categorizable: false,
      clase_categoria: null,
      regla_posible: null,
    });
    expect(queEs(ajuste)).toBe("Ajuste");
    const sueldo = movimientoInventado({
      tipo: "ingreso",
      es_gasto: false,
      monto_centavos: 480_000_000,
      categoria: { id: 10, nombre: "Sueldo", clase: "ingreso", color: "cat-sueldo", icono: "briefcase" },
    });
    expect(queEs(sueldo)).toBe("Sueldo");
    expect(montoDeFila(ajuste)).toEqual({ texto: "−$18.400", clase: "resta" });
    expect(llevaMarcaDeCategoria(sueldo)).toBe(true);
    expect(llevaMarcaDeCategoria(ajuste)).toBe(false);
    expect(llevaMarcaDeCategoria(ingreso!)).toBe(false);
  });

  it("un ingreso sin categoría es pendiente (ítem 15): «Sin categorizar», con su cuadro hueco", () => {
    const pendiente = movimientoInventado({
      tipo: "ingreso",
      es_gasto: false,
      descripcion: "CARLOS RUIZ EJEMPLO",
      pendiente: true,
      clase_categoria: "ingreso",
      regla_posible: { campo: "quien_envia", texto: "carlos ruiz ejemplo" },
    });
    expect(queEs(pendiente)).toBe("Sin categorizar");
    expect(llevaMarcaDeCategoria(pendiente)).toBe(true);
    expect(montoDeFila(pendiente)).toEqual({ texto: "+$8.500", clase: "suma" });
  });
});

describe("montos pendientes (ítem 15): gastos e ingresos nunca se suman", () => {
  it("solo gastos", () => {
    expect(partesPendientes({ pendientes_centavos: 2_770_000, pendientes_ingresos_centavos: 0 })).toEqual({
      tipo: "gastos",
      gastos: 2_770_000,
    });
  });

  it("gastos e ingresos van aparte", () => {
    expect(
      partesPendientes({ pendientes_centavos: 2_770_000, pendientes_ingresos_centavos: 40_000_000 }),
    ).toEqual({ tipo: "ambos", gastos: 2_770_000, ingresos: 40_000_000 });
  });

  it("solo ingresos", () => {
    expect(partesPendientes({ pendientes_centavos: 0, pendientes_ingresos_centavos: 40_000_050 })).toEqual({
      tipo: "ingresos",
      ingresos: 40_000_050,
    });
  });
});


it("título de pendientes en singular y plural", () => {
  expect(tituloPendientes(1)).toBe("1 movimiento sin categorizar");
  expect(tituloPendientes(3)).toBe("3 movimientos sin categorizar");
});
