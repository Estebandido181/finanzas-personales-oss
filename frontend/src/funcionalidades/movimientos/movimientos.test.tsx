import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { memoryLocation } from "wouter/memory-location";
import { guardarTokenCsrf, type Esquemas } from "@/compartido/http/cliente";
import { App } from "@/app/app";
import { reiniciarFocoDePantallas } from "@/compartido/ui/pantalla";
import {
  SESION_INVENTADA,
  simularApi,
  TOKEN_INVENTADO,
  type Manejador,
  type Respuesta,
} from "@/pruebas/api-simulada";
import { reporteInventado, sincronizacionCorrecta } from "@/pruebas/inicio-inventado";
import {
  CATEGORIAS_INVENTADAS,
  grupoInventado,
  movimiento,
  movimientosDelMesInventados,
} from "@/pruebas/movimientos-inventado";
import { reiniciarTemaEnMemoria } from "@/compartido/tema/preferencias";

const ok = (cuerpo: unknown): Respuesta => ({ estado: 200, cuerpo });

/**
 * Un pendiente inventado de agosto: la bandeja es de todos los meses.
 */
const PENDIENTE_DE_AGOSTO = () =>
  movimiento({
    id: 201,
    fecha_hora: "2026-08-14T12:00:00",
    descripcion: "CAFETERIA EL PARQUE EJEMPLO",
    monto_centavos: 700_000,
  });

/**
 * Una API de mentira con estado: filtra como la de verdad y PUT categoriza
 * (el movimiento queda "manual"; con `recordar`, los pendientes iguales
 * quedan "regla"). Así las pruebas ven la lista recargada. La bandeja y el
 * número de pendientes del reporte son de todos los meses.
 */
function apiConEstado(movimientos = [...movimientosDelMesInventados(), PENDIENTE_DE_AGOSTO()]) {
  let lista = movimientos;
  const pendientes = () => lista.filter((m) => m.pendiente);
  const categoria = (id: number) => CATEGORIAS_INVENTADAS.find((c) => c.id === id)!;
  const filtrar = (url: URL): Esquemas["Movimiento"][] => {
    const q = url.searchParams;
    const mes = url.searchParams.get("mes") ?? "2026-09";
    return lista.filter((m) => {
      if (!m.fecha_hora.startsWith(mes)) return false;
      const tipo = q.get("tipo");
      if (tipo === "gasto" && !m.es_gasto) return false;
      if (tipo && tipo !== "gasto" && m.tipo !== tipo) return false;
      if (q.get("categoria_id") && m.categoria?.id !== Number(q.get("categoria_id"))) return false;
      if (q.get("sin_categoria") === "true" && !(m.es_gasto && m.categoria === null)) return false;
      return true;
    });
  };
  const rutas: Record<string, Manejador | Respuesta> = {
    "GET /api/sesion": ok(SESION_INVENTADA),
    "GET /api/no-reconocidos": ok({ correos: [] }),
    "GET /api/sincronizacion": ok(sincronizacionCorrecta()),
    "GET /api/categorias": ok({ categorias: CATEGORIAS_INVENTADAS }),
    "GET /api/reporte": (p) => {
      const mes = new URL(p.url).searchParams.get("mes");
      const pendientesAhora = { pendientes: pendientes().length };
      return ok(
        mes === "2026-08"
          ? reporteInventado({ mes, es_mes_actual: false, mes_anterior: null, mes_siguiente: "2026-09", ...pendientesAhora })
          : reporteInventado(pendientesAhora),
      );
    },
    "GET /api/movimientos": (p) => {
      const url = new URL(p.url);
      const mes = url.searchParams.get("mes") ?? "2026-09";
      return ok({ mes, movimientos: filtrar(url) });
    },
    "GET /api/movimientos/sin-categorizar": () => ok({ total: pendientes().length, movimientos: pendientes(), grupos: [] }),
  };
  const categorizar: Manejador = async (p) => {
    const id = Number(new URL(p.url).pathname.split("/")[3]);
    const cuerpo = (await p.json()) as Esquemas["CategorizarEntrada"];
    const elegido = lista.find((m) => m.id === id)!;
    let categorizados = 1;
    // Ítem 17: la regla que se pidió (por omisión, por texto), como la arma la API.
    const condiciones = cuerpo.condiciones ?? "texto";
    const opcion = elegido.reglas_posibles.find((o) => o.condiciones === condiciones);
    const regla = cuerpo.recordar && opcion ? { id: 50, modo_texto: "exacta" as const, origen_regla: "todos" as const, ...opcion } : null;
    const coincide = (m: Esquemas["Movimiento"]) =>
      regla !== null &&
      m.tipo === elegido.tipo &&
      (regla.texto === null || m.descripcion.toLowerCase() === regla.texto) &&
      (regla.monto_centavos === null || m.monto_centavos === regla.monto_centavos);
    lista = lista.map((m) => {
      if (m.id === id) {
        return {
          ...m,
          categoria: categoria(cuerpo.categoria_id),
          origen_categoria: "manual",
          regla: null,
          pendiente: false,
        };
      }
      if (regla && m.categoria === null && coincide(m)) {
        categorizados++;
        return { ...m, categoria: categoria(cuerpo.categoria_id), origen_categoria: "regla", regla, pendiente: false };
      }
      return m;
    });
    return ok({ categorizados, regla_guardada: cuerpo.recordar, regla });
  };
  for (const id of movimientos.map((m) => m.id)) rutas[`PUT /api/movimientos/${id}/categoria`] = categorizar;
  return rutas;
}

function montar(rutas: Record<string, Manejador | Respuesta>, ruta = "/movimientos") {
  const api = simularApi(rutas);
  const [path, search = ""] = ruta.split("?");
  const ubicacion = memoryLocation({ path: path!, searchPath: search, record: true });
  const usuario = userEvent.setup();
  render(<App cliente={api.cliente} hook={ubicacion.hook} searchHook={ubicacion.searchHook} />);
  return { ...api, ubicacion, usuario };
}

const pedidos = (peticiones: Request[], metodo: string, ruta: string | RegExp) =>
  peticiones.filter(
    (p) =>
      p.method === metodo &&
      (typeof ruta === "string" ? new URL(p.url).pathname === ruta : ruta.test(new URL(p.url).pathname)),
  );

const dias = () => screen.findByRole("list", { name: "Movimientos de septiembre, por día" });
/** La fila (li) de un movimiento, por su descripción. */
const fila = (descripcion: string) => screen.getByText(descripcion, { selector: "p" }).closest("li")!;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-09-30T15:00:00Z"));
  reiniciarTemaEnMemoria();
  reiniciarFocoDePantallas();
});
afterEach(() => {
  vi.useRealTimers();
  guardarTokenCsrf(null);
});

describe("Movimientos", () => {
  it("muestra el mes por días, con lo gastado y cómo se categorizó cada uno", async () => {
    montar(apiConEstado());
    const lista = await dias();
    expect(document.title).toBe("Movimientos · Finanzas personales");
    expect(screen.getByRole("heading", { level: 1, name: "Movimientos" })).toBeVisible();

    const hojas = within(lista).getAllByRole("heading", { level: 2 });
    expect(hojas.map((h) => h.textContent)).toEqual([
      "Hoy, miércoles 30 de septiembreGastado: $11.700",
      "Ayer, martes 29 de septiembreGastado: $174.450",
      "Lunes 28 de septiembreGastado: $51.900",
      "Domingo 27 de septiembreGastado: $12.000",
    ]);

    expect(fila("SUPERMERCADO LA ESPIGA")).toHaveTextContent(
      "Mercado, por regla: compra en «SUPERMERCADO LA ESPIGA»",
    );
    expect(fila("*3000000001")).toHaveTextContent("Transporte, por regla: transferencia a «*3000000001»");
    expect(fila("SUPERMERCADO LA ESPIGA")).toHaveTextContent("Compra · 6:15 p. m.");
    expect(fila("SUPERMERCADO LA ESPIGA")).toHaveTextContent("$132.449,50");
    expect(fila("DROGUERIA SAN ROQUE EJEMPLO")).toHaveTextContent("Salud, a mano");
    expect(fila("RESTAURANTE DOÑA TERE EJEMPLO")).toHaveTextContent(
      "Restaurantes, no se sabe si fue a mano o por regla",
    );
    expect(fila("HELADERIA POLO NORTE EJEMPLO")).toHaveTextContent("Antojos, por una regla que ya se borró");
    expect(fila("TIENDA DON PEPE EJEMPLO")).toHaveTextContent("Sin categorizar");
    // Ingresos con su signo y su categoría (ítem 15); el ajuste, sin categoría ni botón.
    expect(fila("EMPRESA EJEMPLO S.A.S.")).toHaveTextContent("Ingreso · 8:00 a. m.+$4.800.000");
    expect(fila("EMPRESA EJEMPLO S.A.S.")).toHaveTextContent(
      "Sueldo, por regla: ingreso de «EMPRESA EJEMPLO S.A.S.»",
    );
    expect(fila("Ajuste de saldo")).toHaveTextContent("−$18.400");
    expect(within(fila("Ajuste de saldo")).queryByRole("button")).toBeNull();

    expect(
      within(fila("DROGUERIA SAN ROQUE EJEMPLO")).getByRole("button", {
        name: "Cambiar categoría de DROGUERIA SAN ROQUE EJEMPLO",
      }),
    ).toBeVisible();
    // El primer pendiente ya muestra las opciones; el siguiente, el botón.
    expect(within(fila("PANADERIA EL TRIGAL")).getByRole("group", { name: "¿En qué categoría va? Toca una:" }))
      .toBeVisible();
    expect(
      within(fila("TIENDA DON PEPE EJEMPLO")).getByRole("button", { name: "Categorizar TIENDA DON PEPE EJEMPLO" }),
    ).toBeVisible();

    const mostrar = screen.getByRole("group", { name: "Mostrar" });
    expect(within(mostrar).getByRole("button", { name: "Todos" })).toHaveAttribute("aria-pressed", "true");
    // El número es de todos los meses (el mismo de Inicio): 2 de septiembre y 1 de agosto.
    expect(within(mostrar).getByRole("button", { name: "Sin categorizar (3)" })).toBeVisible();
    const selector = screen.getByRole("navigation", { name: "Cambiar de mes" });
    expect(within(selector).getByRole("link", { name: "Agosto" })).toHaveAttribute(
      "href",
      "/movimientos?mes=2026-08",
    );
    expect(selector).toHaveTextContent("Septiembre de 2026");
    expect(within(selector).getAllByRole("link")).toHaveLength(1);
  });

  it("en «Sin categorizar», un toque categoriza y otro crea la regla", async () => {
    const { usuario, peticiones } = montar(apiConEstado(), "/movimientos?ver=sin-categorizar");
    const lista = await screen.findByRole("list", { name: "Movimientos sin categorizar, por día" });
    // Una sola bandeja, de todos los meses: también el pendiente de agosto, sin "Gastado" ni selector de mes.
    expect(within(lista).getAllByRole("group", { name: "¿En qué categoría va? Toca una:" })).toHaveLength(3);
    expect(within(lista).getByText("CAFETERIA EL PARQUE EJEMPLO")).toBeVisible();
    expect(within(lista).getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "Hoy, miércoles 30 de septiembre",
      "Lunes 28 de septiembre",
      "Viernes 14 de agosto",
    ]);
    expect(screen.getByText("Sin categorizar · todos los meses")).toBeVisible();
    expect(screen.queryByRole("navigation", { name: "Cambiar de mes" })).toBeNull();
    expect(pedidos(peticiones, "GET", "/api/movimientos")).toHaveLength(0);
    // "Otros" va al final de las opciones.
    const opciones = within(fila("PANADERIA EL TRIGAL")).getByRole("group");
    expect(within(opciones).getAllByRole("button").at(-1)).toHaveTextContent("Otros");

    await usuario.click(within(fila("PANADERIA EL TRIGAL")).getByRole("button", { name: "Mercado" }));
    const guardado = await within(fila("PANADERIA EL TRIGAL")).findByRole("status");
    expect(guardado).toHaveTextContent(
      "Guardado en Mercado.¿Categorizar igual las siguientes? Crea una regla con un toque:",
    );
    expect(guardado).toHaveFocus();
    // Sigue a la vista (aunque ya no es pendiente) hasta cambiar de filtro.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Sin categorizar (2)" })).toBeVisible(),
    );
    expect(fila("PANADERIA EL TRIGAL")).toHaveTextContent("Mercado, a mano");

    const put = pedidos(peticiones, "PUT", "/api/movimientos/101/categoria");
    expect(put).toHaveLength(1);
    expect(put[0]!.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
    expect(await put[0]!.json()).toEqual({ categoria_id: 1, recordar: false });

    await usuario.click(within(guardado).getByRole("button", { name: "Compras en PANADERIA EL TRIGAL" }));
    await waitFor(() =>
      expect(within(fila("PANADERIA EL TRIGAL")).getByRole("status")).toHaveTextContent(
        "Regla creada: compras en PANADERIA EL TRIGAL van a Mercado.",
      ),
    );
    const segundo = pedidos(peticiones, "PUT", "/api/movimientos/101/categoria")[1]!;
    expect(await segundo.json()).toEqual({ categoria_id: 1, recordar: true, condiciones: "texto" });
  });

  it("un ingreso pendiente (ítem 15): solo categorías de ingreso y regla por quien envía", async () => {
    const ingreso = movimiento({
      id: 202,
      fecha_hora: "2026-09-26T11:00:00",
      tipo: "ingreso",
      es_gasto: false,
      descripcion: "CARLOS RUIZ EJEMPLO",
      monto_centavos: 40_000_000,
    });
    const { usuario, peticiones } = montar(
      apiConEstado([...movimientosDelMesInventados(), PENDIENTE_DE_AGOSTO(), ingreso]),
      "/movimientos?ver=sin-categorizar",
    );
    await screen.findByRole("list", { name: "Movimientos sin categorizar, por día" });
    const carlos = fila("CARLOS RUIZ EJEMPLO");
    expect(carlos).toHaveTextContent("Sin categorizar");
    const opciones = within(carlos).getByRole("group", { name: "¿En qué categoría va? Toca una:" });
    expect(within(opciones).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Sueldo",
      "Préstamos",
      "Otros ingresos",
    ]);
    // Y un gasto pendiente, solo las de gasto.
    const panaderia = within(fila("PANADERIA EL TRIGAL")).getByRole("group", { name: "¿En qué categoría va? Toca una:" });
    expect(within(panaderia).queryByRole("button", { name: "Sueldo" })).toBeNull();

    await usuario.click(within(opciones).getByRole("button", { name: "Préstamos" }));
    expect(await within(carlos).findByText("Guardado en Préstamos.")).toBeVisible();
    // Ítem 17: un ingreso ofrece las tres reglas, en el orden de la API.
    const guardado = within(carlos).getByRole("status");
    expect(within(guardado).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Ingresos de CARLOS RUIZ EJEMPLO",
      "Ingresos de $400.000",
      "Las dos cosas juntas",
    ]);
    await usuario.click(within(carlos).getByRole("button", { name: "Ingresos de CARLOS RUIZ EJEMPLO" }));
    expect(await within(carlos).findByText("Regla creada: ingresos de CARLOS RUIZ EJEMPLO van a Préstamos.")).toBeVisible();
    const puts = peticiones.filter((p) => p.method === "PUT");
    expect(await puts.at(-1)!.json()).toEqual({ categoria_id: 11, recordar: true, condiciones: "texto" });
  });

  it("ítem 17: «Transferencias de $3.200» crea la regla por monto y alcanza a otro destino", async () => {
    const bus = (id: number, cuenta: string, hora: string) =>
      movimiento({ id, fecha_hora: `2026-09-30T${hora}`, tipo: "transferencia", descripcion: cuenta, monto_centavos: 320_000 });
    const { usuario, peticiones } = montar(
      apiConEstado([...movimientosDelMesInventados(), bus(301, "*3000000002", "06:30:00"), bus(302, "*3000000003", "06:10:00")]),
      "/movimientos?ver=sin-categorizar",
    );
    await screen.findByRole("list", { name: "Movimientos sin categorizar, por día" });
    const primero = fila("*3000000002");
    await usuario.click(within(primero).getByRole("button", { name: "Transporte" }));
    const guardado = await within(primero).findByRole("status");
    expect(within(guardado).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Transferencias a *3000000002",
      "Transferencias de $3.200",
      "Las dos cosas juntas",
    ]);
    // El monto va en la letra de los montos (TEXTOS.md).
    expect(
      within(guardado).getByRole("button", { name: "Las dos cosas juntas: transferencias a «*3000000002» por $3.200" }),
    ).toBeVisible();
    const porMonto = within(guardado).getByRole("button", { name: "Transferencias de $3.200" });
    expect(within(porMonto).getByText("$3.200")).toHaveClass("font-montos");

    await usuario.click(porMonto);
    await waitFor(() =>
      expect(within(fila("*3000000002")).getByRole("status")).toHaveTextContent(
        "Regla creada: transferencias de $3.200 van a Transporte.",
      ),
    );
    const puts = pedidos(peticiones, "PUT", "/api/movimientos/301/categoria");
    expect(await puts.at(-1)!.json()).toEqual({ categoria_id: 3, recordar: true, condiciones: "monto" });
    // La otra transferencia de $3.200, a otra cuenta, ya no está pendiente.
    await usuario.click(screen.getByRole("button", { name: "Todos" }));
    await waitFor(() =>
      expect(fila("*3000000003")).toHaveTextContent("Transporte, por regla: transferencia de $3.200"),
    );
    // Dos veces en la fila: el monto del movimiento y el de la regla, los dos en su letra.
    expect(within(fila("*3000000003")).getAllByText("$3.200")).toHaveLength(2);
  });

  it("corregir uno categorizado por regla lo deja a mano y no ofrece cambiar la regla", async () => {
    const { usuario } = montar(apiConEstado());
    await dias();
    await usuario.click(screen.getByRole("button", { name: "Cambiar categoría de SUPERMERCADO LA ESPIGA" }));
    const opciones = within(fila("SUPERMERCADO LA ESPIGA")).getByRole("group", {
      name: "¿En qué categoría va? Toca una:",
    });
    // La categoría actual va marcada.
    expect(within(opciones).getByRole("button", { name: "Mercado" })).toHaveAttribute("aria-pressed", "true");
    expect(within(opciones).getByRole("button", { name: "Antojos" })).toHaveAttribute("aria-pressed", "false");
    await usuario.click(within(opciones).getByRole("button", { name: "Antojos" }));
    const aviso = await within(fila("SUPERMERCADO LA ESPIGA")).findByRole("status");
    expect(aviso).toHaveTextContent(
      "Cambiado a Antojos.Ahora está categorizado a mano; la regla sigue igual para los demás.",
    );
    expect(within(aviso).queryByRole("button")).toBeNull();
    await waitFor(() => expect(fila("SUPERMERCADO LA ESPIGA")).toHaveTextContent("Antojos, a mano"));
  });

  it("«Cambiar» se puede cancelar sin tocar nada", async () => {
    const { usuario, peticiones } = montar(apiConEstado());
    await dias();
    await usuario.click(screen.getByRole("button", { name: "Cambiar categoría de DROGUERIA SAN ROQUE EJEMPLO" }));
    await usuario.click(within(fila("DROGUERIA SAN ROQUE EJEMPLO")).getByRole("button", { name: "Cancelar" }));
    expect(within(fila("DROGUERIA SAN ROQUE EJEMPLO")).queryByRole("group")).toBeNull();
    expect(pedidos(peticiones, "PUT", /categoria$/)).toHaveLength(0);
  });

  it("el filtro enfocado sigue habilitado mientras su lectura está pendiente", async () => {
    const rutas = apiConEstado();
    const leer = rutas["GET /api/movimientos"] as Manejador;
    let terminar!: () => void;
    rutas["GET /api/movimientos"] = (peticion) => {
      if (new URL(peticion.url).searchParams.get("tipo") !== "ingreso") return leer(peticion);
      return new Promise<Respuesta>((resolver) => { terminar = () => { void Promise.resolve(leer(peticion)).then(resolver); }; });
    };
    const { usuario } = montar(rutas);
    await dias();
    const ingresos = screen.getByRole("button", { name: "Ingresos" });
    await usuario.click(ingresos);
    await waitFor(() => expect(terminar).toBeTypeOf("function"));
    try {
      expect(ingresos).toHaveFocus();
      expect(ingresos).toBeEnabled();
    } finally {
      await act(async () => { terminar(); });
    }
    await waitFor(() => expect(screen.queryByText("PANADERIA EL TRIGAL")).toBeNull());
    expect(ingresos).toHaveFocus();
  });

  it("filtra por tipo y por categoría con la API, y lo guarda en la dirección", async () => {
    const { usuario, peticiones, ubicacion } = montar(apiConEstado());
    await dias();
    await usuario.click(screen.getByRole("button", { name: "Ingresos" }));
    await waitFor(() => expect(screen.queryByText("PANADERIA EL TRIGAL")).toBeNull());
    expect(screen.getByText("EMPRESA EJEMPLO S.A.S.")).toBeVisible();
    expect(ubicacion.history?.at(-1)).toBe("/movimientos?ver=ingresos");
    // Cambiar de filtro no mueve el foco al título.
    expect(screen.getByRole("button", { name: "Ingresos" })).toHaveFocus();

    await usuario.selectOptions(screen.getByLabelText("Categoría"), "Salud");
    await waitFor(() => expect(screen.getByText("DROGUERIA SAN ROQUE EJEMPLO")).toBeVisible());
    expect(screen.queryByText("EMPRESA EJEMPLO S.A.S.")).toBeNull();
    expect(ubicacion.history?.at(-1)).toBe("/movimientos?categoria=5");
    expect(screen.getByRole("button", { name: "Todos" })).toHaveAttribute("aria-pressed", "true");

    const conFiltro = pedidos(peticiones, "GET", "/api/movimientos").map((p) => new URL(p.url).search);
    expect(conFiltro).toContain("?tipo=ingreso");
    expect(conFiltro).toContain("?categoria_id=5");
  });

  it("un filtro sin resultados lo dice y ofrece ver todos", async () => {
    const { usuario } = montar(apiConEstado(), "/movimientos?ver=gastos&categoria=6");
    expect(await screen.findByRole("heading", { level: 2, name: "Nada con este filtro" })).toBeVisible();
    expect(screen.getByText("No hay movimientos de Entretenimiento en septiembre.")).toBeVisible();
    await usuario.click(screen.getByRole("link", { name: "Ver todos los movimientos" }));
    expect(await dias()).toBeVisible();
  });

  it("con todo categorizado, la bandeja lo dice", async () => {
    const todos = movimientosDelMesInventados().filter((m) => !m.pendiente);
    montar(apiConEstado(todos), "/movimientos?ver=sin-categorizar");
    expect(await screen.findByRole("heading", { level: 2, name: "Todo categorizado" })).toBeVisible();
    expect(screen.getByText("Cada movimiento tiene su categoría.")).toBeVisible();
    // Con 0, sin "(0)".
    expect(screen.getByRole("button", { name: "Sin categorizar" })).toHaveAttribute("aria-pressed", "true");
  });

  it("un mes pasado sin movimientos lo dice, con el mes siguiente", async () => {
    montar(apiConEstado(movimientosDelMesInventados()), "/movimientos?mes=2026-08");
    expect(await screen.findByRole("heading", { level: 2, name: "Sin movimientos en agosto" })).toBeVisible();
    const selector = screen.getByRole("navigation", { name: "Cambiar de mes" });
    expect(within(selector).getByRole("link", { name: "Septiembre" })).toHaveAttribute(
      "href",
      "/movimientos?mes=2026-09",
    );
  });

  it("si no se puede categorizar, lo dice en la fila y deja las opciones", async () => {
    const rutas = apiConEstado();
    rutas["PUT /api/movimientos/101/categoria"] = { estado: 404, cuerpo: { detalle: "No existe." } };
    const { usuario } = montar(rutas);
    await dias();
    await usuario.click(within(fila("PANADERIA EL TRIGAL")).getByRole("button", { name: "Mercado" }));
    expect(await within(fila("PANADERIA EL TRIGAL")).findByRole("alert")).toHaveTextContent(
      "Ese movimiento ya no existe. Recarga la página.",
    );
    expect(within(fila("PANADERIA EL TRIGAL")).getByRole("group")).toBeVisible();
  });

  it("sin conexión al abrir, lo dice y deja volver a intentar", async () => {
    const rutas = apiConEstado();
    const bien = rutas["GET /api/movimientos"]!;
    rutas["GET /api/movimientos"] = "sin-red";
    const { usuario, rutas: vivas } = montar(rutas);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No hay conexión con la app. Revisa tu internet y vuelve a intentarlo.",
    );
    vivas["GET /api/movimientos"] = bien;
    await usuario.click(screen.getByRole("button", { name: "Volver a intentar" }));
    expect(await dias()).toBeVisible();
  });
});

describe("Movimientos: grupos en «Sin categorizar» (ítem 38)", () => {
  const viaje = (id: number) =>
    movimiento({
      id,
      fecha_hora: "2026-09-29T06:30:00",
      descripcion: "COBRO VIAJE TRANSPORTE MASIVO",
      monto_centavos: 320_000,
    });

  /** 20 viajes iguales (un grupo) y un pendiente suelto; categorizar el grupo los quita de la bandeja. */
  function apiConGrupo(cambios: Record<string, Manejador | Respuesta> = {}) {
    const ids = Array.from({ length: 20 }, (_, i) => 320 - i);
    const suelto = PENDIENTE_DE_AGOSTO();
    let pendientes = [...ids.map(viaje), suelto];
    let grupos = [grupoInventado({ ids })];
    const rutas: Record<string, Manejador | Respuesta> = {
      "GET /api/sesion": ok(SESION_INVENTADA),
      "GET /api/no-reconocidos": ok({ correos: [] }),
      "GET /api/sincronizacion": ok(sincronizacionCorrecta()),
      "GET /api/categorias": ok({ categorias: CATEGORIAS_INVENTADAS }),
      "GET /api/movimientos/sin-categorizar": () => ok({ total: pendientes.length, movimientos: pendientes, grupos }),
      "POST /api/movimientos/categorizar-grupo": () => {
        pendientes = pendientes.filter((m) => m.id === suelto.id);
        grupos = [];
        return ok({ categorizados: 20, regla_guardada: true, regla: null });
      },
      ...cambios,
    };
    return rutas;
  }
  const abrir = (ruta = "/movimientos?ver=sin-categorizar", cambios: Record<string, Manejador | Respuesta> = {}) =>
    montar(apiConGrupo(cambios), ruta);
  const regionGrupos = () => screen.findByRole("region", { name: "Movimientos que se repiten" });

  it("muestra el grupo («· 20 veces» con su suma) y deja los sueltos como hoy", async () => {
    abrir();
    const grupos = await regionGrupos();
    const lista = within(grupos).getByRole("list", { name: "Grupos de movimientos iguales" });
    const item = within(lista).getAllByRole("listitem")[0]!;
    expect(item).toHaveTextContent("COBRO VIAJE TRANSPORTE MASIVO");
    expect(item).toHaveTextContent("Compra · 20 veces");
    expect(item).toHaveTextContent("$64.000");
    expect(
      within(item).getByRole("button", { name: "Categorizar las 20 de COBRO VIAJE TRANSPORTE MASIVO" }),
    ).toBeVisible();
    // Los viajes no salen sueltos; el pendiente de agosto, sí, con sus opciones abiertas.
    const sueltos = await screen.findByRole("list", { name: "Movimientos sin categorizar, por día" });
    expect(within(sueltos).queryByText("COBRO VIAJE TRANSPORTE MASIVO")).toBeNull();
    expect(within(sueltos).getByText("CAFETERIA EL PARQUE EJEMPLO")).toBeVisible();
  });

  it("un toque en la categoría categoriza el grupo y guarda la regla, con CSRF", async () => {
    const { usuario, peticiones } = abrir();
    const grupos = await regionGrupos();
    await usuario.click(within(grupos).getByRole("button", { name: /^Categorizar las 20/ }));
    expect(within(grupos).getByRole("group", { name: "¿En qué categoría van las 20? Toca una:" })).toBeVisible();
    expect(grupos).toHaveTextContent(
      "Se categorizan juntos y se guarda la regla: compras en COBRO VIAJE TRANSPORTE MASIVO van a la categoría que elijas.",
    );
    await usuario.click(within(grupos).getByRole("button", { name: "Transporte" }));

    const aviso = await within(grupos).findByRole("status");
    expect(aviso).toHaveTextContent("20 movimientos categorizados en Transporte.");
    expect(aviso).toHaveTextContent("Regla creada: compras en COBRO VIAJE TRANSPORTE MASIVO van a Transporte.");
    expect(aviso).toHaveFocus();
    const envio = pedidos(peticiones, "POST", "/api/movimientos/categorizar-grupo")[0]!;
    expect(envio.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
    const cuerpo = (await envio.json()) as { clave: string; ids: number[]; categoria_id: number };
    expect(cuerpo.clave).toBe("compra|cobro viaje transporte masivo");
    expect(cuerpo.categoria_id).toBe(3);
    expect(cuerpo.ids).toHaveLength(20);
    // El servidor ya no lo trae, pero su resultado sigue a la vista; el número de pendientes baja.
    await waitFor(() => expect(screen.getByRole("button", { name: "Sin categorizar (1)" })).toBeVisible());
    expect(within(grupos).getByRole("status")).toBeVisible();
    // Un grupo ya categorizado no ofrece categorizar otra vez.
    expect(within(grupos).queryByRole("button", { name: /^Categorizar las/ })).toBeNull();
  });

  it("solo ofrece las categorías de su clase (un grupo de ingresos, las de ingreso)", async () => {
    const grupo = grupoInventado({
      clave: "ingreso|carlos ruiz ejemplo",
      tipo: "ingreso",
      descripcion: "CARLOS RUIZ EJEMPLO",
      clase_categoria: "ingreso",
      es_gasto: false,
      ids: [401, 402],
      suma_centavos: 80_000_000,
      regla: {
        condiciones: "texto",
        tipo_movimiento: "ingreso",
        campo: "quien_envia",
        texto: "carlos ruiz ejemplo",
        monto_centavos: null,
        frase: "ingreso de «carlos ruiz ejemplo»",
      },
    });
    const { usuario } = abrir("/movimientos?ver=sin-categorizar", {
      "GET /api/movimientos/sin-categorizar": ok({ total: 2, movimientos: [], grupos: [grupo] }),
    });
    const grupos = await regionGrupos();
    expect(grupos).toHaveTextContent("Ingreso · 2 veces");
    expect(grupos).toHaveTextContent("+$800.000");
    await usuario.click(within(grupos).getByRole("button", { name: /^Categorizar las 2/ }));
    const opciones = within(within(grupos).getByRole("group", { name: /¿En qué categoría van las 2\?/ }))
      .getAllByRole("button")
      .map((b) => b.textContent);
    expect(opciones).toEqual(["Sueldo", "Préstamos", "Otros ingresos"]);
  });

  it("un error del servidor se dice en el grupo y deja las opciones para reintentar", async () => {
    const { usuario } = abrir("/movimientos?ver=sin-categorizar", {
      "POST /api/movimientos/categorizar-grupo": {
        estado: 400,
        cuerpo: { detalle: "Esa categoría es de otra clase." },
      },
    });
    const grupos = await regionGrupos();
    await usuario.click(within(grupos).getByRole("button", { name: /^Categorizar las 20/ }));
    await usuario.click(within(grupos).getByRole("button", { name: "Transporte" }));
    expect(await within(grupos).findByRole("alert")).toHaveTextContent("Esa categoría es de otra clase.");
    expect(within(grupos).getByRole("button", { name: "Transporte" })).toBeEnabled();
  });

  it("si ya no estaban pendientes (categorizados = 0), lo dice y no habla de regla", async () => {
    const { usuario } = abrir("/movimientos?ver=sin-categorizar", {
      "POST /api/movimientos/categorizar-grupo": ok({ categorizados: 0, regla_guardada: false, regla: null }),
    });
    const grupos = await regionGrupos();
    await usuario.click(within(grupos).getByRole("button", { name: /^Categorizar las 20/ }));
    await usuario.click(within(grupos).getByRole("button", { name: "Transporte" }));
    const aviso = await within(grupos).findByRole("status");
    expect(aviso).toHaveTextContent("Esos movimientos ya no estaban sin categorizar. No se cambió nada.");
    expect(aviso).not.toHaveTextContent("Regla creada");
  });

  it("sin grupos, la bandeja queda como hoy (sin la hoja de grupos)", async () => {
    abrir("/movimientos?ver=sin-categorizar", {
      "GET /api/movimientos/sin-categorizar": ok({ total: 1, movimientos: [PENDIENTE_DE_AGOSTO()], grupos: [] }),
    });
    await screen.findByRole("list", { name: "Movimientos sin categorizar, por día" });
    expect(screen.queryByRole("region", { name: "Movimientos que se repiten" })).toBeNull();
  });
});
