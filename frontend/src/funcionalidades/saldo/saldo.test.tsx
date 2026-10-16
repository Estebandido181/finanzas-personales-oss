import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { memoryLocation } from "wouter/memory-location";
import { guardarTokenCsrf, type Esquemas } from "@/compartido/http/cliente";
import { App } from "@/app/app";
import { reiniciarFocoDePantallas } from "@/compartido/ui/pantalla";
import { SESION_INVENTADA, simularApi, TOKEN_INVENTADO, type Manejador, type Respuesta } from "@/pruebas/api-simulada";
import { sincronizacionCorrecta } from "@/pruebas/inicio-inventado";
import { NBSP } from "@/compartido/formatos/formato";
import { filasInventadas, saldoInventado, saldoSinConfigurar } from "@/pruebas/saldo-inventado";
import { reiniciarTemaEnMemoria } from "@/compartido/tema/preferencias";
import { comprobacionInventada } from "@/pruebas/comprobacion-inventada";

const ok = (cuerpo: unknown): Respuesta => ({ estado: 200, cuerpo });

/**
 * API inventada con estado: borrar un ingreso lo quita de la lista y baja el
 * saldo (y los ingresos del desglose) exactamente en su monto, como la real.
 */
function apiConEstado(extra: Record<string, Manejador | Respuesta> = {}, segundosParaDeshacer = 10) {
  let saldo = saldoInventado();
  let lecturas = 0;
  // Lo último que se borró, para poder restaurarlo con el token (un solo uso).
  let borrado: { fila: Esquemas["IngresoOAjusteDelMes"]; saldoAntes: Esquemas["Saldo"] } | null = null;
  const rutas: Record<string, Manejador | Respuesta> = {
    "GET /api/sesion": ok(SESION_INVENTADA),
    "GET /api/no-reconocidos": ok({ correos: [] }),
    "GET /api/sincronizacion": ok(sincronizacionCorrecta()),
    "GET /api/saldo": () => {
      lecturas++;
      return ok({ ...saldo, token_ingreso: `token-ingreso-inventado-${lecturas}` });
    },
    "DELETE /api/ingresos/41": () => {
      const fila = saldo.del_mes.find((f) => f.id === 41);
      if (!fila) return { estado: 404, cuerpo: { detalle: "Ese ingreso ya no existe. Recarga la pantalla de saldo." } };
      const nuevo = saldo.saldo_centavos! - fila.monto_centavos;
      borrado = { fila, saldoAntes: saldo };
      saldo = {
        ...saldo,
        saldo_centavos: nuevo,
        desglose: { ...saldo.desglose!, ingresos_centavos: saldo.desglose!.ingresos_centavos - fila.monto_centavos },
        del_mes: saldo.del_mes.filter((f) => f.id !== 41),
      };
      return ok({
        id: 41,
        monto_centavos: fila.monto_centavos,
        saldo_centavos: nuevo,
        deshacer: { token: "token-deshacer-inventado", segundos: segundosParaDeshacer },
      });
    },
    "POST /api/deshacer": async (p) => {
      const { token } = (await p.json()) as { token: string };
      if (token !== "token-deshacer-inventado" || borrado === null) {
        return { estado: 410, cuerpo: { detalle: "Ya no se puede deshacer: pasó el tiempo o ya se deshizo." } };
      }
      saldo = borrado.saldoAntes;
      borrado = null;
      return ok({ que: "ingreso", id: 41, saldo_centavos: saldo.saldo_centavos });
    },
    ...extra,
  };
  return rutas;
}

function montar(rutas: Record<string, Manejador | Respuesta>) {
  const api = simularApi(rutas);
  const ubicacion = memoryLocation({ path: "/saldo", record: true });
  const usuario = userEvent.setup();
  render(<App cliente={api.cliente} hook={ubicacion.hook} searchHook={ubicacion.searchHook} />);
  return { ...api, usuario };
}

const hojaSaldo = () => screen.findByRole("region", { name: "Saldo actual" });
const hojaLista = () => screen.findByRole("region", { name: "Ingresos y ajustes de septiembre" });
const fila = (lista: HTMLElement, descripcion: string) =>
  within(lista)
    .getAllByRole("listitem")
    .find((li) => within(li).queryByText(descripcion, { exact: true }))!;

beforeEach(() => {
  reiniciarTemaEnMemoria();
  reiniciarFocoDePantallas();
});
afterEach(() => guardarTokenCsrf(null));

describe("Saldo", () => {
  it("descarta una comprobación retrasada al iniciar un ajuste y espera la recarga antes de habilitar", async () => {
    let resolverComprobacion!: (respuesta: Respuesta) => void;
    let resolverAjuste!: (respuesta: Respuesta) => void;
    const { usuario } = montar(apiConEstado({
      "POST /api/saldo/comprobar": () => new Promise((r) => { resolverComprobacion = r; }),
      "POST /api/ajustes": () => new Promise((r) => { resolverAjuste = r; }),
    }));
    const comprobar = within(await screen.findByRole("region", { name: "Comprobar saldo" }));
    await usuario.type(comprobar.getByLabelText("Escribe el saldo que ves ahora en Bancolombia"), "1.234,56");
    await usuario.click(comprobar.getByRole("button", { name: "Comprobar saldo" }));
    const ajustar = within(screen.getByRole("region", { name: "Ajustar el saldo" }));
    await usuario.type(ajustar.getByLabelText("Saldo real en Bancolombia"), "1.234,56");
    await usuario.click(ajustar.getByRole("button", { name: "Ajustar saldo" }));
    expect(comprobar.getByRole("button", { name: "Comprobar saldo" })).toBeDisabled();
    resolverComprobacion(ok(comprobacionInventada()));
    await waitFor(() => expect(comprobar.queryByText("+$0,06")).toBeNull());
    expect(comprobar.getByRole("button", { name: "Comprobar saldo" })).toBeDisabled();
    resolverAjuste(ok({ id: 99, registrado: true, diferencia_centavos: -1, saldo_centavos: 123456 }));
    await ajustar.findByText(/Saldo ajustado/);
    await waitFor(() => expect(comprobar.getByRole("button", { name: "Comprobar saldo" })).toBeEnabled());
    expect(comprobar.queryByText("+$0,06")).toBeNull();
  });
  it("muestra el saldo, el desglose plegado, el total de ajustes y la lista del mes", async () => {
    montar(apiConEstado());
    const saldo = await hojaSaldo();
    expect(screen.getByRole("heading", { level: 1, name: "Saldo" })).toBeVisible();
    expect(within(saldo).getAllByText("$4.739.150")[0]).toBeVisible();
    expect(within(saldo).getByText("Llevas las cuentas desde el 1 de septiembre de 2026.")).toBeVisible();
    // Desglose plegado por defecto (decisión del dueño).
    const desglose = within(saldo).getByText("Ver cómo se calcula").closest("details")!;
    expect(desglose).not.toHaveAttribute("open");
    expect(desglose).toHaveTextContent("Saldo inicial$1.250.000");
    expect(desglose).toHaveTextContent("Ingresos+$5.350.000");
    expect(desglose).toHaveTextContent("Gastos−$1.842.450");
    expect(desglose).toHaveTextContent("Ajustes−$18.400");

    const lista = await hojaLista();
    expect(lista).toHaveTextContent("Total de ajustes del mes−$18.400 en 2 ajustes");
    expect(within(lista).getAllByRole("listitem")).toHaveLength(5);
    expect(fila(lista, "Efectivo venta bicicleta")).toHaveTextContent(/Ingreso a mano · 29 de septiembre, 10:00/);
    expect(fila(lista, "EMPRESA EJEMPLO S.A.S.")).toHaveTextContent(/Ingreso de Gmail · 28 de septiembre/);
    expect(fila(lista, "Efectivo arriendo garaje EJEMPLO")).toHaveTextContent("+$200.000");
    expect(within(lista).getAllByText("Ajuste de saldo")).toHaveLength(2);
    expect(lista).toHaveTextContent("−$12.399,50");
    expect(lista).toHaveTextContent("Solo se puede borrar un ingreso registrado a mano y posterior al último ajuste.");
    expect(document.title).toBe("Saldo · Finanzas personales");
  });

  it("solo muestra «Borrar ingreso» donde la API dice se_puede_borrar", async () => {
    montar(apiConEstado());
    const lista = await hojaLista();
    const botones = within(lista).getAllByRole("button", { name: /^Borrar ingreso/ });
    expect(botones).toHaveLength(1);
    expect(botones[0]).toHaveAccessibleName("Borrar ingreso Efectivo venta bicicleta");
    // Ni el ajuste, ni el de Gmail, ni el ingreso a mano anterior al último ajuste.
    for (const descripcion of ["EMPRESA EJEMPLO S.A.S.", "Efectivo arriendo garaje EJEMPLO"]) {
      expect(within(fila(lista, descripcion)).queryByRole("button")).toBeNull();
    }
    for (const ajuste of within(lista).getAllByText("Ajuste de saldo")) {
      expect(within(ajuste.closest("li")!).queryByRole("button")).toBeNull();
    }
  });

  it("borrar un ingreso es tocar y deshacer: sin confirmación, baja el saldo exactamente en su monto", async () => {
    const { usuario, peticiones } = montar(apiConEstado());
    const lista = await hojaLista();
    await usuario.click(within(lista).getByRole("button", { name: "Borrar ingreso Efectivo venta bicicleta" }));
    expect(screen.queryByRole("dialog")).toBeNull();

    const aviso = await within(lista).findByRole("status");
    expect(aviso).toHaveTextContent("Ingreso borrado. El saldo bajó $150.000.");
    expect(within(aviso).getByRole("button", { name: "Deshacer" })).toBeVisible();
    expect(aviso).toHaveFocus();
    // 4.739.150 − 150.000 = 4.589.150, sin redondeos.
    await waitFor(async () => expect(await hojaSaldo()).toHaveTextContent("$4.589.150"));
    expect(within(lista).queryByText("Efectivo venta bicicleta", { selector: "p" })).toBeNull();
    expect(within(lista).getAllByRole("listitem")).toHaveLength(4);

    const borrado = peticiones.find((p) => p.method === "DELETE")!;
    expect(new URL(borrado.url).pathname).toBe("/api/ingresos/41");
    expect(borrado.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
  });

  it("Deshacer restaura el ingreso y el saldo como estaban", async () => {
    const { usuario, peticiones } = montar(apiConEstado());
    const lista = await hojaLista();
    await usuario.click(within(lista).getByRole("button", { name: "Borrar ingreso Efectivo venta bicicleta" }));
    await usuario.click(await within(lista).findByRole("button", { name: "Deshacer" }));

    expect(await within(lista).findByText("Ingreso restaurado. El saldo volvió a $4.739.150.")).toBeVisible();
    // Ya no hay nada que deshacer.
    expect(within(lista).queryByRole("button", { name: "Deshacer" })).toBeNull();
    await waitFor(() => expect(fila(lista, "Efectivo venta bicicleta")).toHaveTextContent("+$150.000"));
    expect(await hojaSaldo()).toHaveTextContent("$4.739.150");
    expect(within(lista).getAllByRole("listitem")).toHaveLength(5);

    const deshacer = peticiones.find((p) => new URL(p.url).pathname === "/api/deshacer")!;
    expect(deshacer.method).toBe("POST");
    expect(deshacer.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
    expect(await deshacer.json()).toEqual({ token: "token-deshacer-inventado" });
  });

  it("el aviso desaparece cuando se acaban los segundos que mandó el servidor", async () => {
    const { usuario } = montar(apiConEstado({}, 1));
    const lista = await hojaLista();
    await usuario.click(within(lista).getByRole("button", { name: "Borrar ingreso Efectivo venta bicicleta" }));
    expect(await within(lista).findByRole("button", { name: "Deshacer" })).toBeVisible();
    await waitFor(() => expect(within(lista).queryByRole("status")).toBeNull(), { timeout: 3000 });
    // El saldo sigue ya bajado, y el foco no se perdió en el body.
    expect(await hojaSaldo()).toHaveTextContent("$4.589.150");
    expect(document.activeElement).not.toBe(document.body);
  });

  it("un 410 al deshacer (venció o ya se usó) lo dice con claridad", async () => {
    const { usuario } = montar(
      apiConEstado({
        "POST /api/deshacer": {
          estado: 410,
          cuerpo: { detalle: "Ya no se puede deshacer: pasó el tiempo o ya se deshizo." },
        },
      }),
    );
    const lista = await hojaLista();
    await usuario.click(within(lista).getByRole("button", { name: "Borrar ingreso Efectivo venta bicicleta" }));
    await usuario.click(await within(lista).findByRole("button", { name: "Deshacer" }));
    expect(await within(lista).findByRole("alert")).toHaveTextContent(
      "Ya no se puede deshacer: pasó el tiempo o ya se deshizo.",
    );
    expect(within(lista).queryByRole("button", { name: "Deshacer" })).toBeNull();
    expect(await hojaSaldo()).toHaveTextContent("$4.589.150");
  });

  it("un 409 al deshacer muestra el motivo de la API", async () => {
    const detalle = "No se puede deshacer: ya hay un ajuste posterior.";
    const { usuario } = montar(apiConEstado({ "POST /api/deshacer": { estado: 409, cuerpo: { detalle } } }));
    const lista = await hojaLista();
    await usuario.click(within(lista).getByRole("button", { name: "Borrar ingreso Efectivo venta bicicleta" }));
    await usuario.click(await within(lista).findByRole("button", { name: "Deshacer" }));
    expect(await within(lista).findByRole("alert")).toHaveTextContent(detalle);
  });

  it("un 409 de la API al borrar muestra su mensaje y deja la lista y el saldo igual", async () => {
    const detalle =
      "Este ingreso es anterior al último ajuste: borrarlo descuadraría un saldo que ya cuadraste. Si hace falta, corrige el saldo con un ajuste.";
    const { usuario } = montar(apiConEstado({ "DELETE /api/ingresos/41": { estado: 409, cuerpo: { detalle } } }));
    const lista = await hojaLista();
    await usuario.click(within(lista).getByRole("button", { name: "Borrar ingreso Efectivo venta bicicleta" }));

    expect(await within(lista).findByRole("alert")).toHaveTextContent(detalle);
    expect(within(lista).queryByRole("button", { name: "Deshacer" })).toBeNull();
    expect(within(lista).getAllByRole("listitem")).toHaveLength(5);
    expect(fila(lista, "Efectivo venta bicicleta")).toHaveTextContent("+$150.000");
    expect(await hojaSaldo()).toHaveTextContent("$4.739.150");
  });

  it("un 404 al borrar (ya no existe) lo dice y la fila se va al volver a leer", async () => {
    const detalle = "Ese ingreso ya no existe. Recarga la pantalla de saldo.";
    let lecturas = 0;
    const { usuario } = montar(
      apiConEstado({
        "DELETE /api/ingresos/41": { estado: 404, cuerpo: { detalle } },
        // Otra pestaña ya lo borró: la segunda lectura no lo trae.
        "GET /api/saldo": () =>
          ok(++lecturas === 1 ? saldoInventado() : saldoInventado({ del_mes: filasInventadas().filter((f) => f.id !== 41) })),
      }),
    );
    const lista = await hojaLista();
    await usuario.click(within(lista).getByRole("button", { name: "Borrar ingreso Efectivo venta bicicleta" }));
    expect(await within(lista).findByRole("alert")).toHaveTextContent(detalle);
    await waitFor(() => expect(within(lista).queryByText("Efectivo venta bicicleta", { selector: "p" })).toBeNull());
    expect(document.activeElement).not.toBe(document.body);
  });

  it("mientras se borra, el botón dice «Borrando…» y no se puede tocar otra vez", async () => {
    let responder: (r: Respuesta) => void = () => {};
    const { usuario } = montar(
      apiConEstado({ "DELETE /api/ingresos/41": () => new Promise<Respuesta>((r) => (responder = r)) }),
    );
    const lista = await hojaLista();
    await usuario.click(within(lista).getByRole("button", { name: "Borrar ingreso Efectivo venta bicicleta" }));
    expect(within(lista).getByRole("button", { name: "Borrar ingreso Efectivo venta bicicleta" })).toBeDisabled();
    expect(within(lista).getByText("Borrando…")).toBeVisible();
    responder(
      ok({
        id: 41,
        monto_centavos: 15_000_000,
        saldo_centavos: 458_915_000,
        deshacer: { token: "token-deshacer-inventado", segundos: 10 },
      }),
    );
    expect(await within(lista).findByText("Ingreso borrado. El saldo bajó $150.000.")).toBeVisible();
  });

  it("sin red al borrar: lo dice y deja reintentar", async () => {
    const { usuario } = montar(apiConEstado({ "DELETE /api/ingresos/41": "sin-red" }));
    const lista = await hojaLista();
    await usuario.click(within(lista).getByRole("button", { name: "Borrar ingreso Efectivo venta bicicleta" }));
    expect(await within(lista).findByRole("alert")).toHaveTextContent(
      "No hay conexión con la app. Revisa tu internet y vuelve a intentarlo.",
    );
    expect(within(lista).getByRole("button", { name: "Borrar ingreso Efectivo venta bicicleta" })).toBeEnabled();
  });

  it("registrar un ingreso: revisa el monto y envía centavos con el token de un solo uso", async () => {
    let recibido: Esquemas["IngresoEntrada"] | null = null;
    const { usuario, peticiones } = montar(
      apiConEstado({
        "POST /api/ingresos": async (p) => {
          recibido = (await p.json()) as Esquemas["IngresoEntrada"];
          return { estado: 201, cuerpo: { id: 99, monto_centavos: recibido.monto_centavos } };
        },
      }),
    );
    const hoja = await screen.findByRole("region", { name: "Registrar un ingreso" });
    const monto = within(hoja).getByLabelText("Monto en pesos");
    expect(monto).toHaveAccessibleDescription("Punto para los miles y coma para los centavos.");
    expect(within(hoja).getByLabelText("Fecha y hora")).toHaveValue("2026-09-30T09:15");
    // La fecha elegida, también en frase (el campo nativo puede mostrarla en números).
    expect(within(hoja).getByLabelText("Fecha y hora")).toHaveAccessibleDescription(
      `30 de septiembre, 9:15${NBSP}a.${NBSP}m.`,
    );

    await usuario.type(monto, "15O.000");
    await usuario.click(within(hoja).getByRole("button", { name: "Registrar ingreso" }));
    expect(monto).toHaveAttribute("aria-invalid", "true");
    expect(monto).toHaveAccessibleDescription(/^Ese monto tiene una letra O en lugar de un cero\. .*150\.000\./);
    expect(recibido).toBeNull();

    await usuario.clear(monto);
    await usuario.type(monto, "150.000,50");
    await usuario.type(within(hoja).getByLabelText("Descripción (opcional)"), "  Efectivo de una venta EJEMPLO ");
    await usuario.click(within(hoja).getByRole("button", { name: "Registrar ingreso" }));
    expect(await within(hoja).findByRole("status")).toHaveTextContent("Ingreso de $150.000,50 registrado.");
    const post = peticiones.find((p) => p.method === "POST" && p.url.endsWith("/api/ingresos"))!;
    expect(post.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
    expect(recibido).toEqual({
      monto_centavos: 15_000_050,
      fecha_hora: "2026-09-30T09:15",
      descripcion: "Efectivo de una venta EJEMPLO",
      token: "token-ingreso-inventado-1",
    });
    expect(monto).toHaveValue("");
  });

  it("registrar un ingreso: monto vacío y fecha anterior a la de inicio", async () => {
    const { usuario, peticiones } = montar(apiConEstado());
    const hoja = await screen.findByRole("region", { name: "Registrar un ingreso" });
    await usuario.click(within(hoja).getByRole("button", { name: "Registrar ingreso" }));
    expect(within(hoja).getByLabelText("Monto en pesos")).toHaveAccessibleDescription(
      /^Escribe un monto mayor que cero\./,
    );
    await usuario.type(within(hoja).getByLabelText("Monto en pesos"), "1.000");
    const fecha = within(hoja).getByLabelText("Fecha y hora");
    await usuario.clear(fecha);
    await usuario.type(fecha, "2026-08-31T10:00");
    await usuario.click(within(hoja).getByRole("button", { name: "Registrar ingreso" }));
    expect(fecha).toHaveAccessibleDescription(
      `La fecha es anterior al 1 de septiembre de 2026, cuando empezaste a llevar las cuentas. Elige una fecha desde ese día. 31 de agosto, 10:00${NBSP}a.${NBSP}m.`,
    );
    expect(peticiones.some((p) => p.method === "POST")).toBe(false);
  });

  it("un ingreso enviado dos veces (409) lo dice y pide un token nuevo", async () => {
    const { usuario, peticiones } = montar(
      apiConEstado({ "POST /api/ingresos": { estado: 409, cuerpo: { detalle: "Repetido (inventado)." } } }),
    );
    const hoja = await screen.findByRole("region", { name: "Registrar un ingreso" });
    await usuario.type(within(hoja).getByLabelText("Monto en pesos"), "150.000");
    await usuario.click(within(hoja).getByRole("button", { name: "Registrar ingreso" }));
    expect(await within(hoja).findByRole("alert")).toHaveTextContent(
      "Este ingreso ya se registró. Revisa la lista antes de registrarlo otra vez.",
    );
    await waitFor(() => expect(peticiones.filter((p) => p.url.endsWith("/api/saldo"))).toHaveLength(2));
  });

  it("ajustar el saldo: envía el saldo real en centavos y dice el ajuste; si ya coincide, lo informa", async () => {
    const respuestas: Esquemas["Ajuste"][] = [
      { registrado: true, diferencia_centavos: -1_240_000, saldo_centavos: 472_675_000 },
      { registrado: false, diferencia_centavos: 0, saldo_centavos: 472_675_000 },
    ];
    const enviados: unknown[] = [];
    const { usuario, peticiones } = montar(
      apiConEstado({
        "POST /api/ajustes": async (p) => {
          enviados.push(await p.json());
          return ok(respuestas.shift());
        },
      }),
    );
    const hoja = await screen.findByRole("region", { name: "Ajustar el saldo" });
    expect(within(hoja).getByRole("note")).toHaveTextContent("Sincroniza antes de ajustar");
    const campo = within(hoja).getByLabelText("Saldo real en Bancolombia");
    await usuario.type(campo, "4.726.750");
    await usuario.click(within(hoja).getByRole("button", { name: "Ajustar saldo" }));
    expect(await within(hoja).findByText("Saldo ajustado: se registró un ajuste de −$12.400.")).toBeVisible();
    await usuario.type(campo, "4.726.750");
    await usuario.click(within(hoja).getByRole("button", { name: "Ajustar saldo" }));
    expect(
      await within(hoja).findByText("Tu saldo ya coincide con el de Bancolombia: no se registró ningún ajuste."),
    ).toBeVisible();
    expect(enviados).toEqual([{ saldo_real_centavos: 472_675_000 }, { saldo_real_centavos: 472_675_000 }]);
    const posts = peticiones.filter((p) => p.method === "POST" && p.url.endsWith("/api/ajustes"));
    expect(posts.map((p) => p.headers.get("X-CSRF-Token"))).toEqual([TOKEN_INVENTADO, TOKEN_INVENTADO]);
  });

  it("«Sincronizar ahora» junto al ajuste sincroniza y vuelve a leer el saldo", async () => {
    const { usuario, peticiones } = montar(
      apiConEstado({
        "POST /api/sincronizacion": ok({
          estado: "ok",
          contadores: { nuevos: 2, duplicados: 0, no_reconocidos: 0, errores: 0, rechazados_autenticacion: 0 },
          codigo_error: null,
          mensaje: "Inventado.",
        }),
      }),
    );
    const hoja = await screen.findByRole("region", { name: "Ajustar el saldo" });
    await usuario.click(within(hoja).getByRole("button", { name: "Sincronizar ahora" }));
    expect(await within(hoja).findByRole("status")).toHaveTextContent("Sincronización terminada: 2 movimientos nuevos.");
    expect(peticiones.filter((p) => p.url.endsWith("/api/saldo"))).toHaveLength(2);
  });

  it("sin token de ingreso: lo dice, no envía nada y vuelve a leer el saldo", async () => {
    let lecturas = 0;
    const { usuario, peticiones } = montar(
      apiConEstado({
        "GET /api/saldo": () => ok(saldoInventado({ token_ingreso: ++lecturas === 1 ? null : "token-ingreso-inventado-2" })),
      }),
    );
    const hoja = await screen.findByRole("region", { name: "Registrar un ingreso" });
    await usuario.type(within(hoja).getByLabelText("Monto en pesos"), "150.000");
    await usuario.click(within(hoja).getByRole("button", { name: "Registrar ingreso" }));
    expect(await within(hoja).findByRole("alert")).toHaveTextContent("El formulario ya no es válido.");
    expect(peticiones.some((p) => p.method === "POST")).toBe(false);
    expect(lecturas).toBe(2);
  });

  it("sin saldo configurado: «Empieza por tu saldo» lleva a configurarlo", async () => {
    montar(apiConEstado({ "GET /api/saldo": ok(saldoSinConfigurar()) }));
    expect(await screen.findByRole("heading", { level: 2, name: "Empieza por tu saldo" })).toBeVisible();
    // La pantalla nueva (ítem 16), ya no la v1.
    expect(screen.getByRole("link", { name: "Configurar saldo" })).toHaveAttribute("href", "/saldo/configurar");
    expect(screen.queryByRole("region", { name: "Registrar un ingreso" })).toBeNull();
  });

  it("mes sin ingresos ni ajustes: lo dice", async () => {
    montar(
      apiConEstado({
        "GET /api/saldo": ok(saldoInventado({ del_mes: [], ajustes_del_mes: { total_centavos: 0, cantidad: 0 } })),
      }),
    );
    const lista = await hojaLista();
    expect(within(lista).getByRole("heading", { level: 2, name: "Sin ingresos ni ajustes en septiembre" })).toBeVisible();
    expect(within(lista).queryByRole("list")).toBeNull();
  });

  it("sin red al abrir: lo dice y deja volver a intentar", async () => {
    let veces = 0;
    const { usuario } = montar(
      apiConEstado({
        "GET /api/saldo": () => (++veces === 1 ? "sin-red" : ok(saldoInventado())),
      }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("No hay conexión con la app.");
    await usuario.click(screen.getByRole("button", { name: "Volver a intentar" }));
    expect(await hojaSaldo()).toBeVisible();
  });
});
