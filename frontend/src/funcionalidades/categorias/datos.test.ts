import { describe, expect, it } from "vitest";
import { CATEGORIAS_CON_USO, reglaInventada } from "@/pruebas/categorias-inventado";
import {
  borradorNuevo,
  botonBorrar,
  cambiosDe,
  claveNombre,
  deLaClase,
  fraseEnMayusculas,
  hayErrores,
  partesFrase,
  planBorrado,
  primerParLibre,
  revisarBorrador,
  textoBorrada,
  textoUso,
  type CategoriaConUso,
} from "@/funcionalidades/categorias/datos";

const porNombre = (nombre: string) => CATEGORIAS_CON_USO.find((c) => c.nombre === nombre)!;

describe("listas", () => {
  it("separa por clase, en el orden de la API", () => {
    expect(deLaClase(CATEGORIAS_CON_USO, "gasto").map((c) => c.nombre).at(-1)).toBe("Otros");
    expect(deLaClase(CATEGORIAS_CON_USO, "ingreso").map((c) => c.nombre)).toEqual([
      "Sueldo",
      "Préstamos",
      "Otros ingresos",
    ]);
  });

  it("cuántos movimientos este mes", () => {
    expect(textoUso(14)).toBe("14 movimientos este mes");
    expect(textoUso(1)).toBe("1 movimiento este mes");
    expect(textoUso(0)).toBe("Sin movimientos este mes");
  });
});

describe("formulario", () => {
  it("compara nombres como la API: sin mayúsculas ni espacios de más", () => {
    expect(claveNombre("  ANTOJOS   de  noche ")).toBe(claveNombre("antojos de noche"));
    // "é" compuesta y "e" + tilde combinante son la misma.
    expect(claveNombre("Café")).toBe(claveNombre("Café"));
  });

  it("nombre vacío, largo o repetido en su clase", () => {
    const base = { clase: "gasto" as const, color: "cat-antojos" as const, icono: "bus" as const };
    expect(revisarBorrador({ ...base, nombre: "   " }, CATEGORIAS_CON_USO, null).nombre).toBe(
      "Escribe el nombre de la categoría.",
    );
    expect(revisarBorrador({ ...base, nombre: "x".repeat(41) }, CATEGORIAS_CON_USO, null).nombre).toBe(
      "El nombre puede tener hasta 40 caracteres.",
    );
    expect(revisarBorrador({ ...base, nombre: " antojos " }, CATEGORIAS_CON_USO, null).nombre).toBe(
      "Ya existe una categoría «Antojos». Usa otro nombre.",
    );
    // El mismo nombre en la otra clase sí se puede.
    expect(revisarBorrador({ ...base, clase: "ingreso", nombre: "Antojos" }, CATEGORIAS_CON_USO, null)).toEqual({});
    // Al editar, no choca consigo misma.
    const antojos = porNombre("Antojos");
    expect(
      revisarBorrador({ ...base, nombre: "Antojos", color: antojos.color, icono: antojos.icono }, CATEGORIAS_CON_USO, antojos.id),
    ).toEqual({});
  });

  it("el par color + ícono no se repite (el color solo sí)", () => {
    const errores = revisarBorrador(
      { nombre: "Nueva", clase: "ingreso", color: "cat-mercado", icono: "shopping-basket" },
      CATEGORIAS_CON_USO,
      null,
    );
    expect(errores.icono).toBe("Otra categoría ya tiene ese color con ese ícono; cambia uno de los dos.");
    expect(hayErrores(errores)).toBe(true);
    const otroIcono = revisarBorrador(
      { nombre: "Nueva", clase: "gasto", color: "cat-mercado", icono: "bus" },
      CATEGORIAS_CON_USO,
      null,
    );
    expect(hayErrores(otroIcono)).toBe(false);
  });

  it("una categoría nueva empieza de gasto y con un par libre", () => {
    expect(primerParLibre(CATEGORIAS_CON_USO)).toEqual({ color: "cat-mercado", icono: "utensils" });
    const nuevo = borradorNuevo(CATEGORIAS_CON_USO);
    expect(nuevo).toEqual({ nombre: "", clase: "gasto", color: "cat-mercado", icono: "utensils" });
    expect(hayErrores(revisarBorrador({ ...nuevo, nombre: "Mascotas nuevas" }, CATEGORIAS_CON_USO, null))).toBe(false);
  });

  it("al editar solo se envía lo que cambió", () => {
    const antojos = porNombre("Antojos");
    const igual = { nombre: " Antojos ", clase: antojos.clase, color: antojos.color, icono: antojos.icono };
    expect(cambiosDe(antojos, igual)).toBeNull();
    expect(cambiosDe(antojos, { ...igual, nombre: "Caprichos  ricos" })).toEqual({ nombre: "Caprichos ricos" });
    expect(cambiosDe(antojos, { ...igual, color: "cat-salud", icono: "bus" })).toEqual({
      color: "cat-salud",
      icono: "bus",
    });
  });
});

describe("borrar una categoría", () => {
  it("con movimientos y reglas: se elige a cuál pasan, «Otros» de entrada", () => {
    const plan = planBorrado(porNombre("Antojos"), CATEGORIAS_CON_USO);
    expect(plan.tipo).toBe("mover");
    if (plan.tipo !== "mover") return;
    expect(plan.texto).toBe(
      "Antojos tiene 12 movimientos y 1 regla. Elige a qué categoría pasan; los movimientos no se borran.",
    );
    // Solo las de la misma clase, sin ella misma.
    expect(plan.destinos.every((c) => c.clase === "gasto" && c.nombre !== "Antojos")).toBe(true);
    const otros = plan.destinos.find((c) => c.id === plan.destinoInicial);
    expect(otros?.nombre).toBe("Otros");
    expect(botonBorrar(plan, otros)).toBe("Borrar y pasar a Otros");
    expect(botonBorrar(plan, porNombre("Mercado"))).toBe("Borrar y pasar a Mercado");
  });

  it("una de ingreso propone «Otros ingresos»; si es esa, la primera", () => {
    const sueldo = planBorrado(porNombre("Sueldo"), CATEGORIAS_CON_USO);
    expect(sueldo.tipo === "mover" && sueldo.destinos.find((c) => c.id === sueldo.destinoInicial)?.nombre).toBe(
      "Otros ingresos",
    );
    const otrosIngresos = planBorrado(porNombre("Otros ingresos"), CATEGORIAS_CON_USO);
    expect(otrosIngresos.tipo).toBe("mover");
    if (otrosIngresos.tipo === "mover") {
      expect(otrosIngresos.texto).toBe("Otros ingresos tiene 1 movimiento. Elige a qué categoría pasa; los movimientos no se borran.");
      expect(otrosIngresos.destinos.find((c) => c.id === otrosIngresos.destinoInicial)?.nombre).toBe("Sueldo");
    }
  });

  it("solo con reglas, sin movimientos", () => {
    const mascotas: CategoriaConUso = { ...porNombre("Antojos"), id: 99, nombre: "Mascotas", movimientos_total: 0, reglas: 2 };
    const plan = planBorrado(mascotas, [...CATEGORIAS_CON_USO, mascotas]);
    expect(plan.texto).toBe("Mascotas tiene 2 reglas. Elige a qué categoría pasan.");
  });

  it("sin movimientos ni reglas: no hay que elegir", () => {
    const vacia: CategoriaConUso = { ...porNombre("Antojos"), id: 99, nombre: "Mascotas", movimientos_total: 0, reglas: 0 };
    const plan = planBorrado(vacia, [...CATEGORIAS_CON_USO, vacia]);
    expect(plan).toEqual({ tipo: "vacia", texto: "Mascotas no tiene movimientos ni reglas." });
    expect(botonBorrar(plan, undefined)).toBe("Borrar categoría");
  });

  it("la última de su clase no se puede borrar", () => {
    const soloUna = CATEGORIAS_CON_USO.filter((c) => c.clase === "gasto" || c.nombre === "Sueldo");
    expect(planBorrado(porNombre("Sueldo"), soloUna)).toEqual({
      tipo: "ultima",
      texto: "No se puede borrar la última categoría de ingreso: crea otra antes.",
    });
  });

  it("el resultado dice cuánto pasó y a dónde", () => {
    const otros = porNombre("Otros");
    expect(textoBorrada("Antojos", { movimientos_movidos: 12, reglas_movidas: 1, destino: otros, deshacer: null })).toBe(
      "Categoría Antojos borrada: 12 movimientos y 1 regla pasaron a Otros.",
    );
    expect(textoBorrada("Mascotas", { movimientos_movidos: 0, reglas_movidas: 1, destino: otros, deshacer: null })).toBe(
      "Categoría Mascotas borrada: 1 regla pasó a Otros.",
    );
    expect(textoBorrada("Mascotas", { movimientos_movidos: 0, reglas_movidas: 0, destino: null, deshacer: null })).toBe(
      "Categoría Mascotas borrada.",
    );
  });
});

describe("frase de una regla", () => {
  it("el tipo en negrita y la categoría como chip", () => {
    expect(partesFrase(reglaInventada())).toEqual({
      chip: true,
      antes: "Si es una ",
      tipo: "compra",
      resto: " en «SUPERMERCADO LA ESPIGA»",
    });
    expect(
      partesFrase(
        reglaInventada({
          tipo_movimiento: "ingreso",
          campo: "quien_envia",
          texto: "empresa ejemplo s.a.s.",
          frase: "Si es un ingreso de «empresa ejemplo s.a.s.», va a Sueldo",
          categoria: { id: 10, nombre: "Sueldo", clase: "ingreso", color: "cat-sueldo", icono: "briefcase" },
        }),
      ),
    ).toEqual({ chip: true, antes: "Si es un ", tipo: "ingreso", resto: " de «EMPRESA EJEMPLO S.A.S.»" });
  });

  it("solo el texto entre «…» va en mayúsculas (también con tildes y eñes)", () => {
    expect(fraseEnMayusculas("Si es una transferencia a «laura gómez ejemplo», va a Comida")).toBe(
      "Si es una transferencia a «LAURA GÓMEZ EJEMPLO», va a Comida",
    );
    expect(fraseEnMayusculas("Si es una compra en «doña tere», va a Restaurantes")).toBe(
      "Si es una compra en «DOÑA TERE», va a Restaurantes",
    );
  });

  it("si la frase no tiene la forma esperada, va entera", () => {
    const rara = reglaInventada({ frase: "Otra forma de decirlo" });
    expect(partesFrase(rara)).toEqual({ chip: false, frase: "Otra forma de decirlo" });
  });
});
