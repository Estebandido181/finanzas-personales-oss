import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { memoryLocation } from "wouter/memory-location";
import { guardarTokenCsrf } from "@/compartido/http/cliente";
import { App } from "@/app/app";
import { reiniciarFocoDePantallas } from "@/compartido/ui/pantalla";
import {
  SESION_INVENTADA,
  simularApi,
  TOKEN_INVENTADO,
  type Manejador,
  type Respuesta,
} from "@/pruebas/api-simulada";
import {
  movimientosInventados,
  reporteInventado,
  resultadoFallido,
  sincronizacionCorrecta,
  sincronizacionFallida,
} from "@/pruebas/inicio-inventado";
import { reiniciarVistaGraficoEnMemoria } from "@/compartido/tema/grafico";
import { reiniciarTemaEnMemoria } from "@/compartido/tema/preferencias";

// Testing Library compara el texto con los espacios normalizados: el espacio
// que no se parte (NBSP) de horas y porcentajes se escribe aquí como espacio.
const ok = (cuerpo: unknown): Respuesta => ({ estado: 200, cuerpo });

function rutasInicio(cambios: Record<string, Manejador | Respuesta> = {}) {
  return {
    "GET /api/sesion": ok(SESION_INVENTADA),
    "GET /api/no-reconocidos": ok({ correos: [] }),
    "GET /api/reporte": (p: Request) => {
      const mes = new URL(p.url).searchParams.get("mes");
      if (mes === "2026-08") {
        return ok(
          reporteInventado({
            mes: "2026-08",
            nombre_mes: "agosto de 2026",
            es_mes_actual: false,
            mes_anterior: "2026-07",
            mes_siguiente: "2026-09",
          }),
        );
      }
      return ok(reporteInventado());
    },
    "GET /api/movimientos": ok({ mes: "2026-09", movimientos: movimientosInventados() }),
    "GET /api/sincronizacion": ok(sincronizacionCorrecta()),
    ...cambios,
  };
}

function montar(rutas: Record<string, Manejador | Respuesta>, ruta = "/", conStrictMode = false) {
  const api = simularApi(rutas);
  const [path, search = ""] = ruta.split("?");
  const ubicacion = memoryLocation({ path: path!, searchPath: search, record: true });
  const usuario = userEvent.setup();
  const app = <App cliente={api.cliente} hook={ubicacion.hook} searchHook={ubicacion.searchHook} />;
  render(conStrictMode ? <StrictMode>{app}</StrictMode> : app);
  return { ...api, ubicacion, usuario };
}

const titulo = (nombre: string) => screen.findByRole("heading", { level: 1, name: nombre });

/** Inicio también anuncia el indicador de revisiones. Espera el resultado de
 * sincronización y conserva la comprobación de su aviso accesible. */
async function avisoSincronizacion() {
  const texto = await screen.findByText(/^Sincronización terminada/);
  const aviso = texto.closest('[role="status"]');
  expect(aviso).not.toBeNull();
  expect(aviso).toBeVisible();
  return aviso;
}
const pedidos = (peticiones: Request[], metodo: string, ruta: string) =>
  peticiones.filter((p) => p.method === metodo && new URL(p.url).pathname === ruta);

beforeEach(() => {
  // Solo la fecha es falsa (30 de septiembre de 2026, 10:00 en Colombia); los relojes no.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-09-30T15:00:00Z"));
  reiniciarTemaEnMemoria();
  reiniciarVistaGraficoEnMemoria();
  reiniciarFocoDePantallas();
});
afterEach(() => {
  vi.useRealTimers();
  guardarTokenCsrf(null);
  document.documentElement.removeAttribute("data-grafico");
});

describe("Inicio: el reporte del mes", () => {
  it("muestra el mes, la sincronización, los pendientes, las cifras, el gráfico y los últimos", async () => {
    montar(rutasInicio());
    expect(await titulo("Septiembre de 2026")).toBeVisible();
    await screen.findByRole("region", { name: "Resumen de septiembre" });
    expect(document.title).toBe("Septiembre de 2026 · Finanzas personales");

    const selector = screen.getByRole("navigation", { name: "Cambiar de mes" });
    expect(within(selector).getByRole("link", { name: "Agosto" })).toHaveAttribute("href", "/?mes=2026-08");
    expect(within(selector).getAllByRole("link")).toHaveLength(1); // sin mes siguiente

    expect(screen.getByText("Sincronizado hoy a las 6:02 a. m.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Sincronizar ahora" })).toBeEnabled();

    const pendientes = screen.getByRole("region", { name: "3 movimientos sin categorizar" });
    expect(pendientes).toHaveTextContent("Suman $27.700.");
    expect(within(pendientes).getByRole("link", { name: "Categorizar ahora" })).toHaveAttribute(
      "href",
      "/movimientos?ver=sin-categorizar",
    );

    const resumen = screen.getByRole("region", { name: "Resumen de septiembre" });
    expect(resumen).toHaveTextContent("Gastado en septiembre$1.842.450");
    expect(resumen).toHaveTextContent("Saldo actual$4.739.150");
    expect(resumen).toHaveTextContent("Ingresos de septiembre+$5.350.000");

    const lista = screen.getByRole("list", { name: "Gasto por categoría en septiembre" });
    const filas = within(lista).getAllByRole("listitem");
    expect(filas).toHaveLength(10);
    expect(filas[0]).toHaveTextContent("Mercado$486.249,50" + "26,4 %");
    expect(filas[9]).toHaveTextContent("Sin categorizar$27.700");
    expect(screen.getByText("Total gastado").parentElement).toHaveTextContent("$1.842.450");

    const ultimos = screen.getByRole("region", { name: "Últimos movimientos" });
    const movimientos = within(ultimos).getAllByRole("listitem");
    expect(movimientos).toHaveLength(4);
    expect(movimientos[0]).toHaveTextContent("PANADERIA EL TRIGALSin categorizar · 7:40 a. m.$8.500");
    expect(movimientos[1]).toHaveTextContent("Transporte · 7:12 a. m.");
    expect(within(ultimos).getByRole("link", { name: "Ver todos los movimientos" })).toHaveAttribute(
      "href",
      "/movimientos",
    );
    // El aviso de error de sincronización no aparece.
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("mientras carga dice «Cargando…», pero solo pasados 300 ms", async () => {
    montar(rutasInicio({ "GET /api/reporte": () => new Promise<Respuesta>(() => {}) }));
    expect(await titulo("Septiembre de 2026")).toBeVisible();
    expect(screen.queryByText("Cargando…")).toBeNull();
    expect(await screen.findByText("Cargando…")).toBeVisible();
  });

  it("cambia de mes: pide ese mes y en un mes pasado ofrece el siguiente", async () => {
    const { usuario, peticiones, ubicacion } = montar(rutasInicio());
    await usuario.click(await screen.findByRole("link", { name: "Agosto" }));
    expect(ubicacion.history.at(-1)).toBe("/?mes=2026-08");
    expect(await titulo("Agosto de 2026")).toHaveFocus();
    const reporte = pedidos(peticiones, "GET", "/api/reporte").at(-1)!;
    expect(new URL(reporte.url).searchParams.get("mes")).toBe("2026-08");
    const movimientos = pedidos(peticiones, "GET", "/api/movimientos").at(-1)!;
    expect(new URL(movimientos.url).searchParams.get("mes")).toBe("2026-08");
    const selector = screen.getByRole("navigation", { name: "Cambiar de mes" });
    expect(within(selector).getByRole("link", { name: "Julio" })).toHaveAttribute("rel", "prev");
    expect(within(selector).getByRole("link", { name: "Septiembre" })).toHaveAttribute(
      "href",
      "/?mes=2026-09",
    );
  });

  it("al llegar los datos de la primera pantalla no le quita el foco a quien ya tabula", async () => {
    let responder: (r: Respuesta) => void = () => {};
    const { usuario } = montar(
      rutasInicio({ "GET /api/reporte": () => new Promise<Respuesta>((r) => (responder = r)) }),
    );
    await titulo("Septiembre de 2026");
    await usuario.tab();
    const salto = screen.getByRole("link", { name: "Saltar al contenido" });
    expect(salto).toHaveFocus();
    responder(ok(reporteInventado()));
    await screen.findByRole("region", { name: "Resumen de septiembre" });
    expect(salto).toHaveFocus();
  });

  it("los ingresos pendientes van aparte, nunca sumados a los gastos (ítem 15)", async () => {
    montar(
      rutasInicio({
        "GET /api/reporte": ok(
          reporteInventado({ pendientes: 4, pendientes_centavos: 2_770_000, pendientes_ingresos_centavos: 40_000_000 }),
        ),
      }),
    );
    const aviso = await screen.findByRole("region", { name: "4 movimientos sin categorizar" });
    expect(aviso).toHaveTextContent("Los gastos suman $27.700.");
    expect(aviso).toHaveTextContent("Aparte, los ingresos suman +$400.000.");
    // Ninguna cifra junta los dos ($427.700).
    expect(aviso).not.toHaveTextContent("427.700");
  });

  it("si solo hay ingresos pendientes, su monto no se presenta como gasto", async () => {
    montar(
      rutasInicio({
        "GET /api/reporte": ok(
          reporteInventado({ pendientes: 1, pendientes_centavos: 0, pendientes_ingresos_centavos: 40_000_000 }),
        ),
      }),
    );
    const aviso = await screen.findByRole("region", { name: "1 movimiento sin categorizar" });
    expect(aviso).toHaveTextContent("Los ingresos suman +$400.000.");
    // Los ingresos no salen en el gráfico de gastos: no se dice que aparecen ahí.
    expect(aviso).not.toHaveTextContent("en el gráfico");
  });

  it("sin pendientes no hay aviso", async () => {
    montar(rutasInicio({ "GET /api/reporte": ok(reporteInventado({ pendientes: 0, pendientes_centavos: 0 })) }));
    await titulo("Septiembre de 2026");
    await screen.findByRole("region", { name: "Resumen de septiembre" });
    expect(screen.queryByText(/sin categorizar$/)).toBeNull();
  });

  it("mes sin movimientos: lo dice e invita a sincronizar", async () => {
    montar(
      rutasInicio({
        "GET /api/reporte": ok(
          reporteInventado({
            total_gasto_centavos: 0,
            total_ingresos_centavos: 0,
            por_categoria: [],
            pendientes: 0,
            pendientes_centavos: 0,
          }),
        ),
        "GET /api/movimientos": ok({ mes: "2026-09", movimientos: [] }),
      }),
    );
    expect(await screen.findByRole("heading", { level: 2, name: "Sin movimientos en septiembre" })).toBeVisible();
    expect(screen.getByText(/Todavía no hay compras, transferencias ni ingresos este mes/)).toBeVisible();
    expect(screen.getAllByRole("button", { name: "Sincronizar ahora" })).toHaveLength(2);
    expect(screen.getByRole("region", { name: "Resumen de septiembre" })).toHaveTextContent(
      "Ingresos de septiembre$0",
    );
    expect(screen.queryByRole("list", { name: /Gasto por categoría/ })).toBeNull();
  });

  it("mes pasado sin movimientos: sin botón de sincronizar", async () => {
    montar(
      rutasInicio({
        "GET /api/reporte": ok(
          reporteInventado({
            mes: "2026-07",
            es_mes_actual: false,
            nombre_mes: "julio de 2026",
            total_gasto_centavos: 0,
            por_categoria: [],
          }),
        ),
        "GET /api/movimientos": ok({ mes: "2026-07", movimientos: [] }),
      }),
      "/?mes=2026-07",
    );
    expect(await screen.findByRole("heading", { level: 2, name: "Sin movimientos en julio" })).toBeVisible();
    expect(screen.getByText("No hubo compras, transferencias ni ingresos en julio.")).toBeVisible();
    expect(screen.getAllByRole("button", { name: "Sincronizar ahora" })).toHaveLength(1);
  });

  it("con ingresos pero sin gastos: «No hay gastos en septiembre.»", async () => {
    montar(
      rutasInicio({
        "GET /api/reporte": ok(reporteInventado({ total_gasto_centavos: 0, por_categoria: [] })),
      }),
    );
    expect(await screen.findByText("No hay gastos en septiembre.")).toBeVisible();
    expect(screen.queryByRole("group", { name: "Ver como" })).toBeNull();
  });

  it("sin saldo configurado: «Empieza por tu saldo»", async () => {
    montar(rutasInicio({ "GET /api/reporte": ok(reporteInventado({ saldo_centavos: null, pendientes: 0 })) }));
    expect(await screen.findByRole("heading", { level: 2, name: "Empieza por tu saldo" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Configurar saldo" })).toHaveAttribute("href", "/saldo/configurar");
  });

  it("si la API falla, lo dice y deja volver a intentar", async () => {
    let falla = true;
    const { usuario } = montar(
      rutasInicio({ "GET /api/reporte": () => (falla ? { estado: 500 } : ok(reporteInventado())) }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La app no pudo completar la acción. Vuelve a intentarlo en unos minutos.",
    );
    falla = false;
    await usuario.click(screen.getByRole("button", { name: "Volver a intentar" }));
    expect(await screen.findByRole("region", { name: "Resumen de septiembre" })).toBeVisible();
  });

  it("sin red: lo dice", async () => {
    montar(rutasInicio({ "GET /api/movimientos": "sin-red" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No hay conexión con la app.");
  });

  it("otra excepción (que no es de red): falla genérica, no «sin conexión»", async () => {
    montar(
      rutasInicio({
        "GET /api/movimientos": () => {
          throw new Error("Falla inventada");
        },
      }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La app no pudo completar la acción. Vuelve a intentarlo en unos minutos.",
    );
  });

  it("un mes no válido en la dirección: muestra el texto de la API", async () => {
    montar(
      rutasInicio({
        "GET /api/reporte": { estado: 400, cuerpo: { detalle: "Mes no válido. Usa el formato AAAA-MM." } },
      }),
      "/?mes=2026-13",
    );
    expect(await titulo("Inicio")).toBeVisible();
    expect(await screen.findByRole("alert")).toHaveTextContent("Mes no válido. Usa el formato AAAA-MM.");
  });
});

/** Lo que dice el servidor: toca sincronizar al abrir (ítem 38). */
const tocaSincronizar = () => ({ ...sincronizacionCorrecta("2026-09-30T04:00:00"), debe_sincronizar_al_abrir: true });

describe("Inicio: sincronizar al abrir (ítem 38)", () => {
  it("si el servidor dice que toca, sincroniza sola una vez (también con StrictMode) y recarga", async () => {
    let estado = tocaSincronizar();
    let responder: (r: Respuesta) => void = () => {};
    const { peticiones } = montar(
      rutasInicio({
        "GET /api/sincronizacion": () => ok(estado),
        "POST /api/sincronizacion": () => new Promise<Respuesta>((r) => (responder = r)),
      }),
      "/",
      true,
    );
    // La pantalla no calcula la hora: sin tocar nada, ya está sincronizando.
    expect(await screen.findByRole("button", { name: "Sincronizando…" })).toBeDisabled();
    const envio = pedidos(peticiones, "POST", "/api/sincronizacion");
    expect(envio).toHaveLength(1);
    expect(envio[0]!.headers.get("x-csrf-token")).toBe(TOKEN_INVENTADO);
    estado = sincronizacionCorrecta();
    responder(ok({ ...sincronizacionCorrecta().ultima, origen: "web" }));
    expect(await avisoSincronizacion()).toHaveTextContent("Sincronización terminada: 3 movimientos nuevos.");
    // Recargó tras sincronizar (StrictMode ya duplica la primera lectura) y no volvió a lanzarla.
    await waitFor(() => expect(pedidos(peticiones, "GET", "/api/sincronizacion").length).toBeGreaterThanOrEqual(3));
    expect(pedidos(peticiones, "POST", "/api/sincronizacion")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Sincronizar ahora" })).toBeEnabled();
  });

  it("si el servidor no lo pide, no sincroniza", async () => {
    const { peticiones } = montar(rutasInicio());
    await titulo("Septiembre de 2026");
    await screen.findByRole("button", { name: "Sincronizar ahora" });
    expect(pedidos(peticiones, "POST", "/api/sincronizacion")).toHaveLength(0);
  });

  it("si falla (sin red), no reintenta sola aunque el servidor siga diciendo que toca; queda el botón", async () => {
    const { peticiones, usuario } = montar(
      rutasInicio({
        "GET /api/sincronizacion": ok(tocaSincronizar()),
        "POST /api/sincronizacion": "sin-red",
      }),
      "/",
      true,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No hay conexión con la app. Revisa tu internet y vuelve a intentarlo.",
    );
    // La pantalla se recargó con el mismo "sí": aun así, una sola vez.
    await waitFor(() => expect(pedidos(peticiones, "GET", "/api/sincronizacion").length).toBeGreaterThanOrEqual(1));
    // Cambiar de mes vuelve a leer el estado, y tampoco repite.
    await usuario.click(screen.getByRole("link", { name: "Agosto" }));
    await titulo("Agosto de 2026");
    expect(pedidos(peticiones, "POST", "/api/sincronizacion")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Sincronizar ahora" })).toBeEnabled();
  });
});

describe("Inicio: sincronización", () => {
  it("«Sincronizar ahora»: envía el token CSRF, dice «Sincronizando…», muestra el resultado y recarga", async () => {
    let responder: (r: Respuesta) => void = () => {};
    const { usuario, peticiones } = montar(
      rutasInicio({ "POST /api/sincronizacion": () => new Promise<Respuesta>((r) => (responder = r)) }),
    );
    await usuario.click(await screen.findByRole("button", { name: "Sincronizar ahora" }));
    expect(screen.getByRole("button", { name: "Sincronizando…" })).toBeDisabled();
    const envio = pedidos(peticiones, "POST", "/api/sincronizacion")[0]!;
    expect(envio.headers.get("x-csrf-token")).toBe(TOKEN_INVENTADO);
    expect(envio.headers.get("content-type")).toBe("application/json");
    responder(
      ok({
        ...sincronizacionCorrecta().ultima,
        origen: "web",
        contadores: { nuevos: 2, duplicados: 1, no_reconocidos: 1, errores: 0, rechazados_autenticacion: 0 },
      }),
    );
    expect(await avisoSincronizacion()).toHaveTextContent(
      "Sincronización terminada: 2 movimientos nuevos y 1 correo no reconocido (ver No reconocidos).",
    );
    expect(screen.getByRole("button", { name: "Sincronizar ahora" })).toBeEnabled();
    await waitFor(() => expect(pedidos(peticiones, "GET", "/api/reporte")).toHaveLength(2));
    expect(pedidos(peticiones, "GET", "/api/sincronizacion")).toHaveLength(2);
    // Recarga sin pasar por "Cargando…": la pantalla sigue ahí.
    expect(screen.getByRole("region", { name: "Resumen de septiembre" })).toBeVisible();
  });

  it("si Gmail rechaza el permiso: aviso arriba con qué hacer y el estado en rojo", async () => {
    let estado = sincronizacionCorrecta();
    const { usuario } = montar(
      rutasInicio({
        "GET /api/sincronizacion": () => ok(estado),
        "POST /api/sincronizacion": () => {
          estado = sincronizacionFallida("2026-09-30T06:02:00");
          return ok(resultadoFallido());
        },
      }),
    );
    await usuario.click(await screen.findByRole("button", { name: "Sincronizar ahora" }));
    const alerta = await screen.findByRole("alert");
    expect(within(alerta).getByRole("heading", { level: 2, name: "No se pudo sincronizar con Gmail" })).toBeVisible();
    expect(alerta).toHaveTextContent("Desde el 30 de septiembre no entran movimientos nuevos");
    expect(alerta).toHaveTextContent("Qué hacer: vuelve a autorizar Gmail con el paso 8");
    expect(within(alerta).getByRole("link", { name: "Ver cómo autorizar Gmail" })).toHaveAttribute(
      "href",
      "https://github.com/Estebandido181/finanzas-personales-oss/blob/main/docs/GMAIL.md",
    );
    expect(document.querySelector("header")).toHaveTextContent(
      "Falló la sincronización. Última correcta: 30 de septiembre, 6:02 a. m.",
    );
    const revisiones = await screen.findByText("Todo al día"); // respuesta independiente de la API simulada
    expect(screen.queryAllByRole("status")).toEqual([revisiones]); // ningún aviso adicional junto al botón
  });

  it("la falla de la sincronización automática se ve al abrir, con la fecha de la última correcta", async () => {
    montar(rutasInicio({ "GET /api/sincronizacion": ok(sincronizacionFallida()) }));
    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent(
      "Gmail rechazó el permiso de lectura de la app: se venció o se revocó. Desde el 28 de septiembre no entran movimientos nuevos, así que el reporte puede estar incompleto.",
    );
    expect(screen.getByText(/^Falló la sincronización\. Última correcta: 28 de septiembre, 12:00/)).toBeVisible();
  });

  it("sin causa clara: dice qué hacer y no manda a autorizar Gmail", async () => {
    montar(rutasInicio({ "GET /api/sincronizacion": ok(sincronizacionFallida(null, "error_inesperado")) }));
    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Vuelve a intentarlo en unos minutos; si se repite, revisa el registro");
    expect(within(alerta).queryByRole("link")).toBeNull();
    expect(
      screen.getByText("Falló la sincronización. Todavía no hay ninguna sincronización correcta."),
    ).toBeVisible();
  });

  it("otras causas: el texto de la API", async () => {
    montar(rutasInicio({ "GET /api/sincronizacion": ok(sincronizacionFallida(null, "gmail_no_configurado")) }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Mensaje inventado de la API para este error.");
  });

  it("si ya hay una en curso (409), lo dice junto al botón", async () => {
    const { usuario } = montar(
      rutasInicio({ "POST /api/sincronizacion": { estado: 409, cuerpo: { detalle: "Ya hay una sincronización en curso." } } }),
    );
    await usuario.click(await screen.findByRole("button", { name: "Sincronizar ahora" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Ya hay una sincronización en curso. Espera a que termine.",
    );
  });

  it("si la sesión se cerró (401), vuelve a «Entrar» y lo dice", async () => {
    const { usuario } = montar(
      rutasInicio({ "POST /api/sincronizacion": { estado: 401, cuerpo: { detalle: "Inicia sesión." } } }),
    );
    await usuario.click(await screen.findByRole("button", { name: "Sincronizar ahora" }));
    expect(await screen.findByText("Tu sesión se cerró. Entra de nuevo para seguir.")).toBeVisible();
    expect(screen.getByLabelText("Contraseña")).toBeVisible();
  });

  it("sin token CSRF en memoria: no envía nada y vuelve a «Entrar»", async () => {
    const { usuario, peticiones } = montar(rutasInicio());
    const boton = await screen.findByRole("button", { name: "Sincronizar ahora" });
    guardarTokenCsrf(null);
    await usuario.click(boton);
    expect(await screen.findByText("Tu sesión se cerró. Entra de nuevo para seguir.")).toBeVisible();
    expect(pedidos(peticiones, "POST", "/api/sincronizacion")).toHaveLength(0);
  });

  it("si el servidor falla (5xx), lo dice junto al botón", async () => {
    const { usuario } = montar(rutasInicio({ "POST /api/sincronizacion": { estado: 502 } }));
    await usuario.click(await screen.findByRole("button", { name: "Sincronizar ahora" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La app no pudo completar la acción. Vuelve a intentarlo en unos minutos.",
    );
    expect(screen.getByRole("button", { name: "Sincronizar ahora" })).toBeEnabled();
  });

  it("el resultado se borra al cambiar de mes", async () => {
    const { usuario } = montar(
      rutasInicio({
        "POST /api/sincronizacion": ok({ ...sincronizacionCorrecta().ultima, origen: "web" }),
      }),
    );
    await usuario.click(await screen.findByRole("button", { name: "Sincronizar ahora" }));
    expect(await avisoSincronizacion()).toHaveTextContent("Sincronización terminada");
    await usuario.click(screen.getByRole("link", { name: "Agosto" }));
    expect(await titulo("Agosto de 2026")).toBeVisible();
    await screen.findByRole("region", { name: "Resumen de agosto" });
    expect(screen.queryByText(/^Sincronización terminada/)).toBeNull();
  });

  it("sin red al sincronizar: lo dice", async () => {
    const { usuario } = montar(rutasInicio({ "POST /api/sincronizacion": "sin-red" }));
    await usuario.click(await screen.findByRole("button", { name: "Sincronizar ahora" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No hay conexión con la app.");
  });

  it("nunca se ha sincronizado", async () => {
    montar(rutasInicio({ "GET /api/sincronizacion": ok({ en_curso: false, ultima: null, ultima_correcta_en: null }) }));
    expect(await screen.findByText("Todavía no se ha sincronizado.")).toBeVisible();
  });
});

describe("Inicio: ver como barras o dona", () => {
  it("barras por defecto; la dona se recuerda en el dispositivo y la lista sigue igual", async () => {
    const { usuario } = montar(rutasInicio());
    const grupo = await screen.findByRole("group", { name: "Ver como" });
    const barras = within(grupo).getByRole("button", { name: "Barras" });
    const dona = within(grupo).getByRole("button", { name: "Dona" });
    expect(barras).toHaveAttribute("aria-pressed", "true");
    expect(document.querySelectorAll("path[data-categoria]")).toHaveLength(0);

    await usuario.click(dona);
    expect(dona).toHaveAttribute("aria-pressed", "true");
    expect(localStorage.getItem("finanzas-grafico")).toBe("dona");
    expect(document.documentElement.dataset.grafico).toBe("dona");
    expect(document.querySelectorAll("path[data-categoria]")).toHaveLength(10);
    expect(
      within(screen.getByRole("list", { name: "Gasto por categoría en septiembre" })).getAllByRole("listitem"),
    ).toHaveLength(10);

    await usuario.click(barras);
    expect(localStorage.getItem("finanzas-grafico")).toBeNull();
    expect(document.documentElement.dataset.grafico).toBeUndefined();
  });

  it("las barras miden en proporción a la mayor, con clases (sin estilos en línea)", async () => {
    montar(rutasInicio());
    const lista = await screen.findByRole("list", { name: "Gasto por categoría en septiembre" });
    const [mercado, vivienda] = within(lista).getAllByRole("listitem");
    expect(mercado!.querySelector("[class*='w-[100%]']")).not.toBeNull();
    expect(vivienda!.querySelector("[class*='w-[85%]']")).not.toBeNull();
    expect(document.querySelector("[style]")).toBeNull();
  });
});
