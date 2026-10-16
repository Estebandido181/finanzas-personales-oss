/** "Configurar saldo" (ítem 16) con la API simulada. Todos los datos son inventados. */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { memoryLocation } from "wouter/memory-location";
import { guardarTokenCsrf } from "@/compartido/http/cliente";
import { App } from "@/app/app";
import { reiniciarFocoDePantallas } from "@/compartido/ui/pantalla";
import { SESION_INVENTADA, simularApi, TOKEN_INVENTADO, type Manejador, type Respuesta } from "@/pruebas/api-simulada";
import { sincronizacionCorrecta } from "@/pruebas/inicio-inventado";
import { saldoInventado, saldoSinConfigurar } from "@/pruebas/saldo-inventado";
import { reiniciarTemaEnMemoria } from "@/compartido/tema/preferencias";

const ok = (cuerpo: unknown): Respuesta => ({ estado: 200, cuerpo });

function rutas(extra: Record<string, Manejador | Respuesta> = {}): Record<string, Manejador | Respuesta> {
  return {
    "GET /api/sesion": ok(SESION_INVENTADA),
    "GET /api/no-reconocidos": ok({ correos: [] }),
    "GET /api/sincronizacion": ok(sincronizacionCorrecta()),
    "GET /api/saldo": ok(saldoSinConfigurar()),
    "PUT /api/saldo/configuracion": async (peticion) => ok(await peticion.json()),
    ...extra,
  };
}

function montar(r: Record<string, Manejador | Respuesta>, path = "/saldo/configurar") {
  const api = simularApi(r);
  const ubicacion = memoryLocation({ path, record: true });
  const usuario = userEvent.setup();
  render(<App cliente={api.cliente} hook={ubicacion.hook} searchHook={ubicacion.searchHook} />);
  return { ...api, usuario, ubicacion };
}

const hoja = () => screen.findByRole("region", { name: "Tu punto de partida" });
const envios = (peticiones: Request[]) => peticiones.filter((p) => p.method === "PUT");

beforeEach(() => {
  reiniciarTemaEnMemoria();
  reiniciarFocoDePantallas();
});
afterEach(() => guardarTokenCsrf(null));

describe("Configurar saldo", () => {
  it("sin configurar: título, ayudas y campos del prototipo", async () => {
    montar(rutas());
    const h = await hoja();
    expect(screen.getByRole("heading", { level: 1, name: "Configurar saldo" })).toBeVisible();
    expect(document.title).toBe("Configurar saldo · Finanzas personales");
    const monto = within(h).getByLabelText("Saldo inicial en pesos");
    expect(monto).toHaveValue("");
    expect(monto).toHaveAttribute("placeholder", "1.250.000");
    expect(monto).toHaveAccessibleDescription(
      "El que tenías al comenzar el día de la fecha de inicio (a las 00:00). Punto para los miles y coma para los centavos.",
    );
    const fecha = within(h).getByLabelText("Fecha de inicio");
    expect(fecha).toHaveValue("2026-09-01");
    expect(fecha).toHaveAttribute("max", "2026-09-30");
    expect(within(h).getByRole("button", { name: "Guardar saldo inicial" })).toBeEnabled();
    // La sección Saldo sigue marcada en la navegación.
    for (const nav of screen.getAllByRole("navigation", { name: "Secciones" })) {
      expect(within(nav).getByRole("link", { name: "Saldo" })).toHaveAttribute("aria-current", "page");
    }
  });

  it("guarda en centavos enteros, con el token CSRF, y lo confirma", async () => {
    const { usuario, peticiones } = montar(rutas());
    const h = await hoja();
    await usuario.type(within(h).getByLabelText("Saldo inicial en pesos"), "1.250.000,50");
    await usuario.click(within(h).getByRole("button", { name: "Guardar saldo inicial" }));
    expect(await within(h).findByRole("status")).toHaveTextContent(
      "Saldo inicial guardado: $1.250.000,50 desde el 1 de septiembre de 2026.",
    );
    const [envio] = envios(peticiones);
    expect(envio!.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
    expect(await envio!.json()).toEqual({ saldo_inicial_centavos: 125_000_050, fecha_inicio: "2026-09-01" });
  });

  it("cero es un saldo inicial válido", async () => {
    const { usuario, peticiones } = montar(rutas());
    const h = await hoja();
    await usuario.type(within(h).getByLabelText("Saldo inicial en pesos"), "0");
    await usuario.click(within(h).getByRole("button", { name: "Guardar saldo inicial" }));
    await within(h).findByRole("status");
    expect(await envios(peticiones)[0]!.json()).toMatchObject({ saldo_inicial_centavos: 0 });
  });

  it("errores de campo: la letra O y la fecha futura, sin llamar a la API", async () => {
    const { usuario, peticiones } = montar(rutas());
    const h = await hoja();
    const monto = within(h).getByLabelText("Saldo inicial en pesos");
    const fecha = within(h).getByLabelText("Fecha de inicio");
    await usuario.type(monto, "1.25O.000");
    await usuario.clear(fecha);
    await usuario.type(fecha, "2026-10-15");
    await usuario.click(within(h).getByRole("button", { name: "Guardar saldo inicial" }));

    expect(monto).toHaveAttribute("aria-invalid", "true");
    expect(monto).toHaveAccessibleDescription(
      "El que tenías al comenzar el día de la fecha de inicio (a las 00:00). Punto para los miles y coma para los centavos. Ese monto tiene una letra O en lugar de un cero. Escríbelo solo con números, por ejemplo 1.250.000.",
    );
    expect(monto).toHaveFocus();
    expect(fecha).toHaveAttribute("aria-invalid", "true");
    expect(fecha).toHaveAccessibleDescription(
      "Los movimientos de ese día sí cuentan. La fecha de inicio no se puede cambiar cuando ya hay movimientos. La fecha de inicio no puede ser futura. Elige hoy o un día anterior.",
    );
    expect(envios(peticiones)).toHaveLength(0);

    // Corregido el monto, el foco pasa a la fecha.
    await usuario.clear(monto);
    await usuario.type(monto, "1.250.000");
    expect(monto).not.toHaveAttribute("aria-invalid");
    await usuario.click(within(h).getByRole("button", { name: "Guardar saldo inicial" }));
    expect(fecha).toHaveFocus();
    expect(envios(peticiones)).toHaveLength(0);
  });

  it("saldo vacío tiene su propio texto", async () => {
    const { usuario } = montar(rutas());
    const h = await hoja();
    await usuario.click(within(h).getByRole("button", { name: "Guardar saldo inicial" }));
    expect(within(h).getByText("Escribe el saldo inicial. Si empiezas en cero, escribe 0.")).toBeVisible();
  });

  it("si la API lo rechaza y sigue sin quedar fija, su mensaje va en un aviso bajo el botón", async () => {
    const detalle = "La fecha de inicio no puede ser futura.";
    const { usuario, peticiones } = montar(
      rutas({ "PUT /api/saldo/configuracion": { estado: 400, cuerpo: { detalle } } }),
    );
    const h = await hoja();
    await usuario.type(within(h).getByLabelText("Saldo inicial en pesos"), "1.250.000");
    await usuario.click(within(h).getByRole("button", { name: "Guardar saldo inicial" }));
    expect(await within(h).findByRole("alert")).toHaveTextContent(detalle);
    // Se volvió a leer (por si ya había movimientos); el formulario se queda con lo escrito.
    await waitFor(() => expect(peticiones.filter((p) => p.url.endsWith("/api/saldo"))).toHaveLength(2));
    expect(within(h).getByLabelText("Saldo inicial en pesos")).toHaveValue("1.250.000");
    expect(within(h).getByRole("alert")).toHaveTextContent(detalle);
    expect(within(h).getByRole("button", { name: "Guardar saldo inicial" })).toBeEnabled();
  });

  it.each([400, 409])(
    "si la API lo rechaza (%i) porque entró un movimiento, vuelve a leer y queda fija",
    async (estado) => {
      const detalle =
        "Ya hay movimientos registrados: el saldo inicial y la fecha de inicio ya no se pueden cambiar. Corrige el saldo con un ajuste.";
      let lecturas = 0;
      const { usuario } = montar(
        rutas({
          // Primera lectura: sin movimientos; al volver a leer, ya hay uno (configuración fija).
          "GET /api/saldo": () =>
            ok(++lecturas === 1 ? saldoInventado({ configuracion_fija: false }) : saldoInventado()),
          "PUT /api/saldo/configuracion": { estado, cuerpo: { detalle } },
        }),
      );
      const h = await hoja();
      await usuario.click(within(h).getByRole("button", { name: "Guardar saldo inicial" }));
      const nota = await screen.findByRole("note");
      expect(nota).toHaveTextContent("El saldo inicial ya no se puede cambiar");
      expect(screen.queryByRole("button", { name: "Guardar saldo inicial" })).toBeNull();
      expect(screen.queryByRole("textbox")).toBeNull();
      // El botón ya no existe: el foco pasa al aviso.
      await waitFor(() => expect(nota.parentElement).toHaveFocus());
      expect(lecturas).toBe(2);
    },
  );

  it("manda configuracion_fija: con desglose y filas pero no fija, se puede configurar", async () => {
    montar(rutas({ "GET /api/saldo": ok(saldoInventado({ configuracion_fija: false })) }));
    const h = await hoja();
    expect(within(h).getByLabelText("Saldo inicial en pesos")).toHaveValue("1.250.000");
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("manda configuracion_fija: sin desglose ni filas pero fija, solo lectura", async () => {
    montar(
      rutas({
        "GET /api/saldo": ok(
          saldoInventado({
            desglose: { saldo_inicial_centavos: 125_000_000, ingresos_centavos: 0, gastos_centavos: 0, ajustes_centavos: 0 },
            del_mes: [],
            ultimos: [],
          }),
        ),
      }),
    );
    await hoja();
    expect(screen.getByRole("note")).toHaveTextContent("El saldo inicial ya no se puede cambiar");
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("solo «$» en el monto dice que falta el saldo inicial", async () => {
    const { usuario, peticiones } = montar(rutas());
    const h = await hoja();
    await usuario.type(within(h).getByLabelText("Saldo inicial en pesos"), " $ ");
    await usuario.click(within(h).getByRole("button", { name: "Guardar saldo inicial" }));
    expect(within(h).getByText("Escribe el saldo inicial. Si empiezas en cero, escribe 0.")).toBeVisible();
    expect(envios(peticiones)).toHaveLength(0);
  });

  it("mientras guarda dice «Guardando…» y no deja enviar dos veces", async () => {
    let soltar: (r: Respuesta) => void = () => {};
    const { usuario, peticiones } = montar(
      rutas({ "PUT /api/saldo/configuracion": () => new Promise<Respuesta>((r) => (soltar = r)) }),
    );
    const h = await hoja();
    await usuario.type(within(h).getByLabelText("Saldo inicial en pesos"), "1.250.000");
    await usuario.click(within(h).getByRole("button", { name: "Guardar saldo inicial" }));
    const boton = await within(h).findByRole("button", { name: "Guardando…" });
    expect(boton).toBeDisabled();
    soltar(ok({ saldo_inicial_centavos: 125_000_000, fecha_inicio: "2026-09-01" }));
    await within(h).findByRole("status");
    expect(envios(peticiones)).toHaveLength(1);
  });

  it("configurado y sin movimientos: los campos traen lo guardado", async () => {
    montar(
      rutas({
        "GET /api/saldo": ok(
          saldoInventado({
            configuracion: { saldo_inicial_centavos: 98_765_432, fecha_inicio: "2026-09-10" },
            configuracion_fija: false,
            desglose: { saldo_inicial_centavos: 98_765_432, ingresos_centavos: 0, gastos_centavos: 0, ajustes_centavos: 0 },
            del_mes: [],
            ultimos: [],
          }),
        ),
      }),
    );
    const h = await hoja();
    expect(within(h).getByLabelText("Saldo inicial en pesos")).toHaveValue("987.654,32");
    expect(within(h).getByLabelText("Fecha de inicio")).toHaveValue("2026-09-10");
  });

  it("con movimientos: solo lectura y «Ajustar el saldo» lleva a Saldo", async () => {
    const { usuario, ubicacion } = montar(rutas({ "GET /api/saldo": ok(saldoInventado()) }));
    const h = await hoja();
    expect(within(h).queryByRole("textbox")).toBeNull();
    expect(within(h).queryByRole("button")).toBeNull();
    expect(h).toHaveTextContent("Saldo inicial$1.250.000");
    expect(h).toHaveTextContent("Fecha de inicio1 de septiembre de 2026");
    const nota = screen.getByRole("note");
    expect(nota).toHaveTextContent("El saldo inicial ya no se puede cambiar");
    expect(nota).toHaveTextContent(
      "Ya hay movimientos desde el 1 de septiembre de 2026, así que el saldo inicial y la fecha de inicio quedaron fijos.",
    );
    await usuario.click(within(nota).getByRole("link", { name: "Ajustar el saldo" }));
    expect(ubicacion.history?.at(-1)).toBe("/saldo");
    expect(await screen.findByRole("heading", { level: 1, name: "Saldo" })).toBeVisible();
  });

  it("sin red al abrir: lo dice y deja volver a intentar", async () => {
    let veces = 0;
    const { usuario } = montar(
      rutas({ "GET /api/saldo": () => (++veces === 1 ? "sin-red" : ok(saldoSinConfigurar())) }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("No hay conexión con la app.");
    await usuario.click(screen.getByRole("button", { name: "Volver a intentar" }));
    expect(await hoja()).toBeVisible();
  });

  it("desde Saldo sin configurar, «Configurar saldo» abre esta pantalla", async () => {
    const { usuario, ubicacion } = montar(rutas(), "/saldo");
    await usuario.click(await screen.findByRole("link", { name: "Configurar saldo" }));
    expect(ubicacion.history?.at(-1)).toBe("/saldo/configurar");
    await waitFor(() => expect(screen.getByRole("heading", { level: 1, name: "Configurar saldo" })).toHaveFocus());
  });
});
