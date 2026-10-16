import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  CATEGORIAS_INVENTADAS,
  grupoInventado,
  movimiento,
  movimientosDelMesInventados,
} from "@/pruebas/movimientos-inventado";
import {
  agruparPorDia,
  botonRegla,
  categoriasDeGrupo,
  conCategoria,
  consultaApi,
  conVista,
  esBandeja,
  filasBandeja,
  filasVisibles,
  fraseRegla,
  leerFiltros,
  ofertasRegla,
  ofrecerRegla,
  opcionesPara,
  ordenarCategorias,
  ordenarGrupos,
  origenDe,
  rutaMovimientos,
  SIN_FILTROS,
  sinGrupo,
  textoGrupoCategorizado,
  textoGuardado,
  textoReglaDelGrupo,
  textoReglaCreada,
  textosVacio,
  tituloDia,
} from "@/funcionalidades/movimientos/datos";

describe("filtros en la dirección", () => {
  it("lee la vista y la categoría, e ignora lo que no entiende", () => {
    expect(leerFiltros("")).toEqual(SIN_FILTROS);
    expect(leerFiltros("ver=gastos&categoria=3")).toEqual({ vista: "gastos", categoria: 3 });
    expect(leerFiltros("ver=sin-categorizar")).toEqual({ vista: "sin-categorizar", categoria: null });
    expect(leerFiltros("ver=otra&categoria=abc")).toEqual(SIN_FILTROS);
    expect(leerFiltros("categoria=0")).toEqual(SIN_FILTROS);
    expect(leerFiltros("categoria=-2")).toEqual(SIN_FILTROS);
  });

  it("«Sin categorizar» e «Ingresos» no llevan categoría (la API no los combina)", () => {
    expect(leerFiltros("ver=sin-categorizar&categoria=3")).toEqual({ vista: "sin-categorizar", categoria: null });
    expect(leerFiltros("ver=ingresos&categoria=3")).toEqual({ vista: "ingresos", categoria: null });
  });

  it("arma la dirección con el mes y los filtros", () => {
    expect(rutaMovimientos(null)).toBe("/movimientos");
    expect(rutaMovimientos("2026-08")).toBe("/movimientos?mes=2026-08");
    expect(rutaMovimientos("2026-08", { vista: "gastos", categoria: 5 })).toBe(
      "/movimientos?mes=2026-08&ver=gastos&categoria=5",
    );
    // La bandeja es de todos los meses: no lleva mes.
    expect(rutaMovimientos("2026-08", { vista: "sin-categorizar", categoria: 5 })).toBe(
      "/movimientos?ver=sin-categorizar",
    );
    expect(esBandeja({ vista: "sin-categorizar", categoria: null })).toBe(true);
    expect(esBandeja(SIN_FILTROS)).toBe(false);
  });

  it("elegir un segmento o una categoría deja una combinación válida", () => {
    expect(conVista({ vista: "todos", categoria: 5 }, "gastos")).toEqual({ vista: "gastos", categoria: 5 });
    expect(conVista({ vista: "todos", categoria: 5 }, "sin-categorizar")).toEqual({
      vista: "sin-categorizar",
      categoria: null,
    });
    expect(conCategoria({ vista: "sin-categorizar", categoria: null }, 2)).toEqual({ vista: "todos", categoria: 2 });
    expect(conCategoria({ vista: "ingresos", categoria: null }, 2)).toEqual({ vista: "todos", categoria: 2 });
    expect(conCategoria({ vista: "gastos", categoria: 2 }, null)).toEqual({ vista: "gastos", categoria: null });
  });

  it("pasa los filtros a los parámetros de la API", () => {
    expect(consultaApi(null, SIN_FILTROS)).toEqual({});
    expect(consultaApi("2026-09", { vista: "gastos", categoria: 5 })).toEqual({
      mes: "2026-09",
      tipo: "gasto",
      categoria_id: 5,
    });
    expect(consultaApi(null, { vista: "ingresos", categoria: null })).toEqual({ tipo: "ingreso" });
  });
});

describe("pendientes y filas visibles", () => {
  const delMes = movimientosDelMesInventados();

  it("sin filtro, todas; con filtro, las de la API más las recién categorizadas, en el orden del mes", () => {
    const nada = new Map<number, (typeof delMes)[number]>();
    expect(filasVisibles(delMes, null, nada)).toHaveLength(delMes.length);
    const filtradas = delMes.filter((m) => m.id === 106);
    expect(filasVisibles(delMes, filtradas, nada).map((m) => m.id)).toEqual([106]);
    const panaderia = delMes.find((m) => m.id === 101)!;
    expect(filasVisibles(delMes, filtradas, new Map([[101, panaderia]])).map((m) => m.id)).toEqual([101, 106]);
  });

  it("la bandeja suma las recién categorizadas en su lugar, de la más reciente a la más antigua", () => {
    const pendientes = [
      movimiento({ id: 3, fecha_hora: "2026-09-28T10:00:00" }),
      movimiento({ id: 1, fecha_hora: "2026-08-15T10:00:00" }),
    ];
    const retenidas = new Map([
      [2, movimiento({ id: 2, fecha_hora: "2026-09-01T10:00:00" })],
      [4, movimiento({ id: 4, fecha_hora: "2026-09-28T10:00:00" })],
      [3, pendientes[0]!],
    ]);
    expect(filasBandeja(pendientes, retenidas).map((m) => m.id)).toEqual([4, 3, 2, 1]);
  });

  it("«Otros» va al final de las opciones", () => {
    const orden = ordenarCategorias([{ id: 8, nombre: "Otros", clase: "gasto", color: "cat-otros", icono: "shapes" }, ...CATEGORIAS_INVENTADAS.filter((c) => c.id !== 8)]);
    expect(orden.at(-1)!.nombre).toBe("Otros");
    expect(orden).toHaveLength(CATEGORIAS_INVENTADAS.length);
    expect(orden[0]!.nombre).toBe("Mercado");
  });
});

describe("días", () => {
  it("dice hoy, ayer, el día de la semana y el año si no es el actual", () => {
    expect(tituloDia("2026-09-30", "2026-09-30")).toBe("Hoy, miércoles 30 de septiembre");
    expect(tituloDia("2026-09-29", "2026-09-30")).toBe("Ayer, martes 29 de septiembre");
    expect(tituloDia("2026-09-28", "2026-09-30")).toBe("Lunes 28 de septiembre");
    expect(tituloDia("2026-10-01", "2026-10-01")).toBe("Hoy, jueves 1 de octubre");
    expect(tituloDia("2026-09-30", "2026-10-01")).toBe("Ayer, miércoles 30 de septiembre");
    expect(tituloDia("2025-12-31", "2026-01-15")).toBe("Miércoles 31 de diciembre de 2025");
  });

  it("agrupa por día y suma lo gastado del día entero, aunque haya filtro", () => {
    const delMes = movimientosDelMesInventados();
    const dias = agruparPorDia(delMes, delMes, "2026-09-30");
    expect(dias.map((d) => [d.fecha, d.movimientos.length, d.gastadoCentavos])).toEqual([
      ["2026-09-30", 2, 1_170_000],
      ["2026-09-29", 2, 17_445_000],
      // El ingreso no cuenta como gasto.
      ["2026-09-28", 3, 5_190_000],
      // El ajuste tampoco.
      ["2026-09-27", 2, 1_200_000],
    ]);
    // En la bandeja (sin la lista del mes) no hay "Gastado".
    expect(agruparPorDia(delMes, null, "2026-09-30")[0]!.gastadoCentavos).toBeNull();
    const soloIngreso = agruparPorDia(delMes.filter((m) => m.id === 105), delMes, "2026-09-30");
    expect(soloIngreso).toHaveLength(1);
    expect(soloIngreso[0]!.gastadoCentavos).toBe(5_190_000);
    expect(agruparPorDia([], delMes, "2026-09-30")).toEqual([]);
  });
});

describe("cómo se categorizó", () => {
  const porId = new Map(movimientosDelMesInventados().map((m) => [m.id, m]));
  const [pendiente, porCuenta, porComercio, aMano, desconocido, ingreso, ajuste, reglaBorrada] = [
    101, 102, 103, 104, 107, 105, 109, 108,
  ].map((id) => porId.get(id));

  it("distingue sin categorizar, a mano, por regla, regla borrada y desconocido", () => {
    expect(origenDe(pendiente!)).toEqual({ tipo: "sin-categorizar" });
    expect(origenDe(aMano!)).toEqual({ tipo: "manual", categoria: "Salud" });
    expect(origenDe(porComercio!)).toEqual({
      tipo: "regla",
      categoria: "Mercado",
      frase: "compra en «SUPERMERCADO LA ESPIGA»",
      montoCentavos: null,
    });
    expect(origenDe(porCuenta!)).toEqual({
      tipo: "regla",
      categoria: "Transporte",
      frase: "transferencia a «*3000000001»",
      montoCentavos: null,
    });
    expect(origenDe(desconocido!)).toEqual({ tipo: "desconocido", categoria: "Restaurantes" });
    expect(origenDe(reglaBorrada!)).toEqual({ tipo: "regla-borrada", categoria: "Antojos" });
    // Ítem 15: el ingreso del prototipo lo categorizó la regla por quien envía.
    expect(origenDe(ingreso!)).toEqual({
      tipo: "regla",
      categoria: "Sueldo",
      frase: "ingreso de «EMPRESA EJEMPLO S.A.S.»",
      montoCentavos: null,
    });
    expect(origenDe(ajuste!)).toEqual({ tipo: "no-aplica" });
  });

  it("una categoría sin origen guardado se lee como desconocido", () => {
    const viejo = movimiento({ categoria: { id: 1, nombre: "Mercado", clase: "gasto", color: "cat-mercado", icono: "shopping-basket" }, origen_categoria: null });
    expect(origenDe(viejo)).toEqual({ tipo: "desconocido", categoria: "Mercado" });
  });

  it("la regla se muestra con la descripción del banco si la API dice que es la suya; si no, con su texto", () => {
    const regla = { modo_texto: "exacta", origen_regla: "todos", id: 1, tipo_movimiento: "compra", campo: "comercio", texto: "café el sol", monto_centavos: null, condiciones: "texto", frase: "compra en «café el sol»" } as const;
    const cafe = movimiento({
      descripcion: "CAFÉ  EL SOL",
      regla_posible: { campo: "comercio", texto: "café el sol" },
    });
    expect(fraseRegla(regla, cafe)).toBe("compra en «CAFÉ  EL SOL»");
    expect(fraseRegla({ ...regla, texto: "otro comercio" }, cafe)).toBe("compra en «otro comercio»");
    expect(fraseRegla(regla, { ...cafe, regla_posible: null })).toBe("compra en «café el sol»");
  });

  it("una regla por monto se lee con la frase de la API", () => {
    const bus = { modo_texto: "exacta", origen_regla: "todos", id: 2, tipo_movimiento: "transferencia", campo: "cuenta_destino", texto: null, monto_centavos: 320_000, condiciones: "monto", frase: "transferencia de $3.200" } as const;
    expect(fraseRegla(bus, movimiento({ tipo: "transferencia", descripcion: "*3000000001" }))).toBe("transferencia de $3.200");
  });
});

describe("categorizar y crear la regla", () => {
  const compra = movimiento({ descripcion: "PANADERIA EL TRIGAL" });
  const transferencia = movimiento({ tipo: "transferencia", descripcion: "LAURA GÓMEZ EJEMPLO" });

  it("los botones y el resultado dicen la regla completa", () => {
    expect(botonRegla(compra)).toBe("Compras en PANADERIA EL TRIGAL");
    expect(botonRegla(transferencia)).toBe("Transferencias a LAURA GÓMEZ EJEMPLO");
    expect(textoReglaCreada(compra, "Mercado")).toBe("Regla creada: compras en PANADERIA EL TRIGAL van a Mercado.");
    expect(textoReglaCreada(transferencia, "Restaurantes")).toBe(
      "Regla creada: transferencias a LAURA GÓMEZ EJEMPLO van a Restaurantes.",
    );
  });

  it("un ingreso (ítem 15): solo categorías de ingreso y regla por quien envía", () => {
    const ingreso = movimiento({ tipo: "ingreso", es_gasto: false, descripcion: "CARLOS RUIZ EJEMPLO" });
    expect(ingreso.pendiente).toBe(true);
    expect(opcionesPara(ingreso, CATEGORIAS_INVENTADAS).map((c) => c.nombre)).toEqual([
      "Sueldo",
      "Préstamos",
      "Otros ingresos",
    ]);
    expect(botonRegla(ingreso)).toBe("Ingresos de CARLOS RUIZ EJEMPLO");
    expect(textoReglaCreada(ingreso, "Préstamos")).toBe("Regla creada: ingresos de CARLOS RUIZ EJEMPLO van a Préstamos.");
    expect(ofrecerRegla(ingreso, "sin-categorizar")).toBe(true);
  });

  it("un gasto solo ve las de gasto («Otros» al final); un ajuste, ninguna", () => {
    const opciones = opcionesPara(compra, CATEGORIAS_INVENTADAS);
    expect(opciones.every((c) => c.clase === "gasto")).toBe(true);
    expect(opciones.at(-1)!.nombre).toBe("Otros");
    const ajuste = movimiento({ tipo: "ajuste", es_gasto: false });
    expect(opcionesPara(ajuste, CATEGORIAS_INVENTADAS)).toEqual([]);
  });

  it("ofrece la regla salvo al corregir lo que categorizó una regla, o si la API no la permite", () => {
    expect(ofrecerRegla(compra, "sin-categorizar")).toBe(true);
    expect(ofrecerRegla(compra, "manual")).toBe(true);
    expect(ofrecerRegla(compra, "desconocido")).toBe(true);
    expect(ofrecerRegla(compra, "regla")).toBe(false);
    expect(ofrecerRegla(compra, "regla-borrada")).toBe(false);
    // Sin regla posible (lo decide la API, p. ej. una descripción vacía), no se ofrece.
    expect(ofrecerRegla({ ...compra, regla_posible: null, reglas_posibles: [] }, "sin-categorizar")).toBe(false);
  });

  it("al corregir uno por regla, avisa que queda a mano y la regla sigue igual", () => {
    expect(textoGuardado("Restaurantes", "sin-categorizar")).toEqual({
      titulo: "Guardado en Restaurantes.",
      texto: "¿Categorizar igual las siguientes? Crea una regla con un toque:",
    });
    expect(textoGuardado("Antojos", "regla")).toEqual({
      titulo: "Cambiado a Antojos.",
      texto: "Ahora está categorizado a mano; la regla sigue igual para los demás.",
    });
  });
});

describe("reglas combinables (ítem 17)", () => {
  const laura = movimiento({ tipo: "transferencia", descripcion: "LAURA GÓMEZ EJEMPLO", monto_centavos: 620_000 });
  const bus = movimiento({ tipo: "transferencia", descripcion: "*3000000002", monto_centavos: 320_000 });
  const carlos = movimiento({ tipo: "ingreso", es_gasto: false, descripcion: "CARLOS RUIZ EJEMPLO", monto_centavos: 40_000_000 });
  const panaderia = movimiento({ descripcion: "PANADERIA EL TRIGAL" });

  it("una transferencia ofrece las tres reglas del prototipo, en el orden de la API", () => {
    expect(ofertasRegla(laura)).toEqual([
      { condiciones: "texto", boton: "Transferencias a LAURA GÓMEZ EJEMPLO", detalle: null, montoCentavos: null, alcance: "transferencias a LAURA GÓMEZ EJEMPLO" },
      { condiciones: "monto", boton: "Transferencias de $6.200", detalle: null, montoCentavos: 620_000, alcance: "transferencias de $6.200" },
      {
        condiciones: "texto_y_monto",
        boton: "Las dos cosas juntas",
        detalle: "transferencias a «LAURA GÓMEZ EJEMPLO» por $6.200",
        montoCentavos: 620_000,
        alcance: "transferencias a «LAURA GÓMEZ EJEMPLO» por $6.200",
      },
    ]);
  });

  it("una compra solo ofrece la regla por texto: como antes del ítem 17", () => {
    const ofertas = ofertasRegla(panaderia);
    expect(ofertas.map((o) => [o.condiciones, o.boton])).toEqual([["texto", "Compras en PANADERIA EL TRIGAL"]]);
    expect(textoReglaCreada(panaderia, "Mercado", ofertas[0])).toBe(textoReglaCreada(panaderia, "Mercado"));
  });

  it("un ingreso ofrece las tres, con «ingresos de»", () => {
    expect(ofertasRegla(carlos).map((o) => o.boton)).toEqual([
      "Ingresos de CARLOS RUIZ EJEMPLO",
      "Ingresos de $400.000",
      "Las dos cosas juntas",
    ]);
    expect(textoReglaCreada(carlos, "Préstamos", ofertasRegla(carlos)[2])).toBe(
      "Regla creada: ingresos de «CARLOS RUIZ EJEMPLO» por $400.000 van a Préstamos.",
    );
  });

  it("el resultado dice la regla que se creó (TEXTOS.md)", () => {
    const [, porMonto] = ofertasRegla(bus);
    expect(porMonto!.condiciones).toBe("monto");
    expect(textoReglaCreada(bus, "Transporte", porMonto)).toBe("Regla creada: transferencias de $3.200 van a Transporte.");
  });

  it("usa la frase de la API, no la arma: si la API dice otra cosa, se muestra eso", () => {
    const raro = movimiento({
      tipo: "transferencia",
      descripcion: "*3000000002",
      monto_centavos: 320_000,
      reglas_posibles: [
        { condiciones: "monto", tipo_movimiento: "transferencia", campo: "cuenta_destino", texto: null, monto_centavos: 320_000, frase: "pagos de $3.200" },
      ],
    });
    expect(ofertasRegla(raro).map((o) => o.boton)).toEqual(["Pagos de $3.200"]);
  });

  it("las frases reales del backend empiezan como espera el plural (si cambian, esta prueba falla)", () => {
    // Las mismas frases que exige backend/tests/api/test_api_reglas_combinables.py: si el backend
    // cambia su forma, esa prueba cambia y esta deja de encontrarlas.
    const backend = readFileSync(
      // vitest corre en frontend/ (en jsdom, import.meta.url no es un archivo).
      resolve(process.cwd(), "../backend/tests/api/test_api_reglas_combinables.py"),
      "utf8",
    );
    const reales = {
      monto: "transferencia de $6.200",
      juntas: "transferencia a «laura gómez ejemplo» por $6.200",
      ingreso: "ingreso de «carlos ruiz ejemplo» por $400.000",
    };
    for (const frase of Object.values(reales)) expect(backend).toContain(`"${frase}"`);
    const opcion = (condiciones: "monto" | "texto_y_monto", frase: string, tipo: "transferencia" | "ingreso", monto: number, texto: string | null) => ({
      condiciones,
      tipo_movimiento: tipo,
      campo: tipo === "ingreso" ? ("quien_envia" as const) : ("cuenta_destino" as const),
      texto,
      monto_centavos: monto,
      frase,
    });
    const conReales = movimiento({
      tipo: "transferencia",
      descripcion: "LAURA GÓMEZ EJEMPLO",
      monto_centavos: 620_000,
      reglas_posibles: [
        opcion("monto", reales.monto, "transferencia", 620_000, null),
        opcion("texto_y_monto", reales.juntas, "transferencia", 620_000, "laura gómez ejemplo"),
      ],
    });
    expect(ofertasRegla(conReales).map((o) => o.alcance)).toEqual([
      "transferencias de $6.200",
      "transferencias a «LAURA GÓMEZ EJEMPLO» por $6.200",
    ]);
    const ingresoReal = movimiento({
      tipo: "ingreso",
      es_gasto: false,
      descripcion: "CARLOS RUIZ EJEMPLO",
      monto_centavos: 40_000_000,
      reglas_posibles: [opcion("texto_y_monto", reales.ingreso, "ingreso", 40_000_000, "carlos ruiz ejemplo")],
    });
    expect(ofertasRegla(ingresoReal)[0]!.alcance).toBe("ingresos de «CARLOS RUIZ EJEMPLO» por $400.000");
  });

  it("«Las dos cosas juntas» solo junto a las otras dos; sola, dice la regla completa", () => {
    const soloJuntas = { ...laura, reglas_posibles: laura.reglas_posibles.filter((o) => o.condiciones === "texto_y_monto") };
    expect(ofertasRegla(soloJuntas).map((o) => [o.boton, o.detalle])).toEqual([
      ["Transferencias a «LAURA GÓMEZ EJEMPLO» por $6.200", null],
    ]);
    // Sin descripción, la API no ofrece reglas por texto: solo por monto.
    const sinTexto = { ...laura, reglas_posibles: laura.reglas_posibles.filter((o) => o.condiciones === "monto") };
    expect(ofertasRegla(sinTexto).map((o) => o.boton)).toEqual(["Transferencias de $6.200"]);
    expect(ofrecerRegla({ ...sinTexto, regla_posible: null }, "sin-categorizar")).toBe(true);
  });

  it("sin reglas posibles no hay ofertas", () => {
    expect(ofertasRegla({ ...panaderia, reglas_posibles: [] })).toEqual([]);
  });

  it("cómo se categorizó, con una regla por texto y monto: la descripción del banco si es la suya", () => {
    const regla = {
      modo_texto: "exacta",
      origen_regla: "todos",
      id: 3,
      tipo_movimiento: "ingreso",
      campo: "quien_envia",
      texto: "carlos ruiz ejemplo",
      monto_centavos: 40_000_000,
      condiciones: "texto_y_monto",
      frase: "ingreso de «carlos ruiz ejemplo» por $400.000",
    } as const;
    const categorizado = {
      ...carlos,
      regla_posible: { campo: "quien_envia" as const, texto: "carlos ruiz ejemplo" },
      categoria: { id: 11, nombre: "Préstamos", clase: "ingreso", color: "cat-prestamos", icono: "handshake" } as const,
      origen_categoria: "regla" as const,
      regla,
      pendiente: false,
    };
    expect(origenDe(categorizado)).toEqual({
      tipo: "regla",
      categoria: "Préstamos",
      frase: "ingreso de «CARLOS RUIZ EJEMPLO» por $400.000",
      montoCentavos: 40_000_000,
    });
    expect(fraseRegla({ ...regla, texto: "otra persona" }, categorizado)).toBe(regla.frase);
  });
});

describe("estados vacíos", () => {
  it("dice qué pasa con cada filtro", () => {
    expect(textosVacio({ vista: "sin-categorizar", categoria: null }, null, "septiembre")).toEqual({
      titulo: "Todo categorizado",
      texto: "Cada movimiento tiene su categoría.",
      verTodos: false,
    });
    expect(textosVacio({ vista: "todos", categoria: 5 }, "Salud", "septiembre")).toEqual({
      titulo: "Nada con este filtro",
      texto: "No hay movimientos de Salud en septiembre.",
      verTodos: true,
    });
    expect(textosVacio({ vista: "ingresos", categoria: null }, null, "julio")?.texto).toBe(
      "No hay ingresos en julio.",
    );
    expect(textosVacio({ vista: "gastos", categoria: null }, null, "julio")?.texto).toBe("No hay gastos en julio.");
    expect(textosVacio(SIN_FILTROS, null, "julio")).toBeNull();
  });
});

describe("grupos de pendientes iguales (ítem 38)", () => {
  it("los pendientes que no están en un grupo siguen sueltos", () => {
    const a = movimiento({ id: 1 });
    const b = movimiento({ id: 2 });
    const c = movimiento({ id: 3 });
    expect(sinGrupo([a, b, c], [grupoInventado({ ids: [2, 1] })])).toEqual([c]);
    expect(sinGrupo([a, b, c], [])).toEqual([a, b, c]);
  });

  it("un grupo ofrece solo las categorías de su clase, con «Otros» al final", () => {
    const gasto = categoriasDeGrupo(grupoInventado(), CATEGORIAS_INVENTADAS).map((c) => c.nombre);
    expect(gasto).toContain("Transporte");
    expect(gasto).not.toContain("Sueldo");
    expect(gasto.at(-1)).toBe("Otros");
    const ingreso = categoriasDeGrupo(grupoInventado({ clase_categoria: "ingreso" }), CATEGORIAS_INVENTADAS);
    expect(ingreso.map((c) => c.nombre)).toEqual(["Sueldo", "Préstamos", "Otros ingresos"]);
  });

  it("los grupos que ya se veían conservan su sitio; los nuevos van al final", () => {
    const g = (clave: string) => ({ clave });
    expect(ordenarGrupos([g("c"), g("a"), g("b")], ["a", "b"]).map((x) => x.clave)).toEqual(["a", "b", "c"]);
    expect(ordenarGrupos([g("b"), g("a")], ["a", "b"]).map((x) => x.clave)).toEqual(["a", "b"]);
  });

  it("dice qué regla se guarda antes de elegir la categoría", () => {
    expect(textoReglaDelGrupo(grupoInventado())).toBe(
      "Se categorizan juntos y se guarda la regla: compras en COBRO VIAJE TRANSPORTE MASIVO van a la categoría que elijas.",
    );
  });

  it("el resultado cuenta lo que respondió el servidor, no lo que mostraba el grupo", () => {
    const grupo = grupoInventado();
    expect(textoGrupoCategorizado(grupo, "Transporte", { categorizados: 20, regla_guardada: true })).toEqual({
      titulo: "20 movimientos categorizados en Transporte.",
      regla: "Regla creada: compras en COBRO VIAJE TRANSPORTE MASIVO van a Transporte.",
    });
    expect(textoGrupoCategorizado(grupo, "Transporte", { categorizados: 1, regla_guardada: false })).toEqual({
      titulo: "1 movimiento categorizado en Transporte.",
      regla: null,
    });
    expect(textoGrupoCategorizado(grupo, "Transporte", { categorizados: 0, regla_guardada: false }).titulo).toBe(
      "Esos movimientos ya no estaban sin categorizar. No se cambió nada.",
    );
  });
});
