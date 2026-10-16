import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { memoryLocation } from "wouter/memory-location";
import { guardarTokenCsrf, type Esquemas } from "@/compartido/http/cliente";
import { App } from "@/app/app";
import { reiniciarFocoDePantallas } from "@/compartido/ui/pantalla";
import { SESION_INVENTADA, simularApi, TOKEN_INVENTADO, type Manejador, type Respuesta } from "@/pruebas/api-simulada";
import { CATEGORIAS_CON_USO, reglaInventada, reglasInventadas } from "@/pruebas/categorias-inventado";
import { sincronizacionCorrecta } from "@/pruebas/inicio-inventado";
import { reiniciarTemaEnMemoria } from "@/compartido/tema/preferencias";

const ok = (cuerpo: unknown): Respuesta => ({ estado: 200, cuerpo });

/** API inventada con estado: crear, editar y borrar cambian lo que devuelve GET. */
function apiConEstado(segundosParaDeshacer = 10) {
  let categorias = [...CATEGORIAS_CON_USO];
  let reglas = reglasInventadas();
  let siguiente = 50;
  // Lo último que se borró y se puede deshacer (un solo uso, como el token real).
  let restaurar: (() => Esquemas["Deshecho"]) | null = null;
  const deshacerDe = () => ({ token: "token-deshacer-inventado", segundos: segundosParaDeshacer });
  const rutas: Record<string, Manejador | Respuesta> = {
    "GET /api/sesion": ok(SESION_INVENTADA),
    "GET /api/no-reconocidos": ok({ correos: [] }),
    "GET /api/sincronizacion": ok(sincronizacionCorrecta()),
    "GET /api/categorias": () => ok({ mes: "2026-09", categorias }),
    "GET /api/reglas": () => ok({ reglas }),
    "POST /api/categorias": async (p) => {
      const cuerpo = (await p.json()) as Esquemas["CategoriaEntrada"];
      const nueva = { id: siguiente++, ...cuerpo, movimientos_mes: 0, movimientos_total: 0, reglas: 0, se_puede_deshacer_borrado: true };
      categorias = [...categorias, nueva];
      return { estado: 201, cuerpo: { id: nueva.id, nombre: nueva.nombre, clase: nueva.clase, color: nueva.color, icono: nueva.icono } };
    },
    "POST /api/deshacer": () => {
      if (restaurar === null) {
        return { estado: 410, cuerpo: { detalle: "Ya no se puede deshacer: pasó el tiempo o ya se deshizo." } };
      }
      const datos = restaurar();
      restaurar = null;
      return ok(datos);
    },
  };
  for (const c of CATEGORIAS_CON_USO) {
    rutas[`PATCH /api/categorias/${c.id}`] = async (p) => {
      const cambios = (await p.json()) as Esquemas["EditarCategoriaEntrada"];
      categorias = categorias.map((x) =>
        x.id === c.id ? { ...x, ...Object.fromEntries(Object.entries(cambios).filter(([, v]) => v != null)) } : x,
      );
      return ok(categorias.find((x) => x.id === c.id));
    };
    rutas[`DELETE /api/categorias/${c.id}`] = (p) => {
      const destinoId = Number(new URL(p.url).searchParams.get("mover_a"));
      const borrada = categorias.find((x) => x.id === c.id)!;
      const destino = categorias.find((x) => x.id === destinoId);
      const antes = categorias;
      categorias = categorias.filter((x) => x.id !== c.id);
      // Solo una categoría sin movimientos ni reglas se puede deshacer.
      const vacia = borrada.se_puede_deshacer_borrado;
      if (vacia) {
        restaurar = () => {
          categorias = antes;
          return { que: "categoria", id: c.id, saldo_centavos: null };
        };
      }
      return ok({
        movimientos_movidos: borrada.movimientos_total,
        reglas_movidas: borrada.reglas,
        destino: destino
          ? { id: destino.id, nombre: destino.nombre, clase: destino.clase, color: destino.color, icono: destino.icono }
          : null,
        deshacer: vacia ? deshacerDe() : null,
      });
    };
  }
  for (const r of reglasInventadas()) {
    rutas[`DELETE /api/reglas/${r.id}`] = () => {
      const antes = reglas;
      reglas = reglas.filter((x) => x.id !== r.id);
      restaurar = () => {
        reglas = antes;
        return { que: "regla", id: r.id, saldo_centavos: null };
      };
      return ok({ id: r.id, deshacer: deshacerDe() });
    };
  }
  return rutas;
}

function montar(rutas: Record<string, Manejador | Respuesta>) {
  const api = simularApi(rutas);
  const ubicacion = memoryLocation({ path: "/categorias", record: true });
  const usuario = userEvent.setup();
  render(<App cliente={api.cliente} hook={ubicacion.hook} searchHook={ubicacion.searchHook} />);
  return { ...api, usuario };
}

const hoja = (nombre: string) => screen.findByRole("region", { name: nombre });
const dialogo = () => screen.getByRole("dialog");

beforeEach(() => {
  reiniciarTemaEnMemoria();
  reiniciarFocoDePantallas();
});
afterEach(() => guardarTokenCsrf(null));

describe("Categorías y reglas", () => {
  it("muestra las categorías de gasto e ingreso, con su uso, y las reglas como frase", async () => {
    montar(apiConEstado());
    const gasto = await hoja("Categorías de gasto");
    expect(document.title).toBe("Categorías y reglas · Finanzas personales");
    expect(within(gasto).getAllByRole("listitem")).toHaveLength(9);
    expect(within(gasto).getAllByRole("listitem")[0]).toHaveTextContent("Mercado14 movimientos este mes");
    const ingreso = await hoja("Categorías de ingreso");
    expect(within(ingreso).getAllByRole("listitem").map((li) => li.textContent?.split(/\d|Sin/)[0])).toEqual([
      "Sueldo",
      "Préstamos",
      "Otros ingresos",
    ]);
    expect(within(ingreso).getByText("Sin movimientos este mes")).toBeVisible();
    expect(within(ingreso).getByRole("button", { name: "Editar Sueldo" })).toBeVisible();
    const reglas = await hoja("Reglas");
    expect(within(reglas).getAllByRole("listitem")[2]).toHaveTextContent(
      "Si es un ingreso de «EMPRESA EJEMPLO S.A.S.», va a Sueldo",
    );
    expect(within(reglas).getAllByRole("button", { name: "Borrar regla" })).toHaveLength(3);
  });

  it("ítem 17: las reglas por monto y por texto y monto, con la frase de la API y el monto en su letra", async () => {
    const porMonto = reglaInventada({
      id: 24,
      tipo_movimiento: "transferencia",
      campo: "cuenta_destino",
      texto: null,
      monto_centavos: 320_000,
      condiciones: "monto",
      categoria: { id: 3, nombre: "Transporte", clase: "gasto", color: "cat-transporte", icono: "bus" },
      frase: "Si es una transferencia de $3.200, va a Transporte",
    });
    const porLasDos = reglaInventada({
      id: 25,
      tipo_movimiento: "ingreso",
      campo: "quien_envia",
      texto: "carlos ruiz ejemplo",
      monto_centavos: 40_000_000,
      condiciones: "texto_y_monto",
      categoria: { id: 11, nombre: "Préstamos", clase: "ingreso", color: "cat-prestamos", icono: "handshake" },
      frase: "Si es un ingreso de «carlos ruiz ejemplo» por $400.000, va a Préstamos",
    });
    const rutas = apiConEstado();
    rutas["GET /api/reglas"] = ok({ reglas: [...reglasInventadas(), porMonto, porLasDos] });
    montar(rutas);
    const reglas = await hoja("Reglas");
    const filas = within(reglas).getAllByRole("listitem");
    expect(filas[3]).toHaveTextContent("Si es una transferencia de $3.200, va a Transporte");
    expect(within(filas[3]!).getByText("transferencia")).toHaveClass("font-fuerte");
    expect(within(filas[3]!).getByText("$3.200")).toHaveClass("font-montos");
    expect(filas[4]).toHaveTextContent("Si es un ingreso de «CARLOS RUIZ EJEMPLO» por $400.000, va a Préstamos");
    expect(within(filas[4]!).getByText("$400.000")).toHaveClass("font-montos");
  });

  it("crea una categoría de ingreso con color e ícono, con CSRF", async () => {
    const { usuario, peticiones } = montar(apiConEstado());
    await hoja("Reglas");
    await usuario.click(screen.getByRole("button", { name: "Nueva categoría" }));
    const d = dialogo();
    expect(within(d).getByRole("heading", { name: "Nueva categoría" })).toBeVisible();
    // Sin nombre: lo dice en el campo, sin llamar a la API.
    await usuario.click(within(d).getByRole("button", { name: "Crear categoría" }));
    expect(within(d).getByText("Escribe el nombre de la categoría.")).toBeVisible();
    expect(within(d).getByLabelText("Nombre")).toHaveAttribute("aria-invalid", "true");
    await usuario.click(within(d).getByRole("radio", { name: "Ingreso" }));
    await usuario.type(within(d).getByLabelText("Nombre"), "Arriendos cobrados");
    await usuario.click(within(d).getByRole("radio", { name: "Bronce" }));
    await usuario.click(within(d).getByRole("radio", { name: "Casa" }));
    await usuario.click(within(d).getByRole("button", { name: "Crear categoría" }));
    expect(await screen.findByText("Categoría Arriendos cobrados creada.")).toBeVisible();
    expect(screen.queryByRole("dialog")).toBeNull();
    const post = peticiones.find((p) => p.method === "POST" && p.url.endsWith("/api/categorias"))!;
    expect(post.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
    expect(await post.json()).toEqual({
      nombre: "Arriendos cobrados",
      clase: "ingreso",
      color: "cat-otros-ingresos",
      icono: "house",
    });
    await waitFor(async () =>
      expect(within(await hoja("Categorías de ingreso")).getByRole("button", { name: "Editar Arriendos cobrados" })).toBeVisible(),
    );
  });

  it("no deja repetir el par color + ícono ni el nombre", async () => {
    const { usuario, peticiones } = montar(apiConEstado());
    await hoja("Reglas");
    await usuario.click(screen.getByRole("button", { name: "Nueva categoría" }));
    const d = dialogo();
    await usuario.type(within(d).getByLabelText("Nombre"), "mercado");
    await usuario.click(within(d).getByRole("radio", { name: "Canasta" }));
    await usuario.click(within(d).getByRole("button", { name: "Crear categoría" }));
    expect(within(d).getByText("Ya existe una categoría «Mercado». Usa otro nombre.")).toBeVisible();
    expect(within(d).getByText("Otra categoría ya tiene ese color con ese ícono; cambia uno de los dos.")).toBeVisible();
    expect(peticiones.some((p) => p.method === "POST")).toBe(false);
    await usuario.click(within(d).getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("muestra el error de la API en el formulario", async () => {
    const rutas = apiConEstado();
    rutas["PATCH /api/categorias/9"] = { estado: 400, cuerpo: { detalle: "Texto inventado de la API." } };
    const { usuario } = montar(rutas);
    await hoja("Reglas");
    await usuario.click(screen.getByRole("button", { name: "Editar Antojos" }));
    const nombre = within(dialogo()).getByLabelText("Nombre");
    await usuario.clear(nombre);
    await usuario.type(nombre, "Caprichos");
    await usuario.click(within(dialogo()).getByRole("button", { name: "Guardar cambios" }));
    expect(await within(dialogo()).findByRole("alert")).toHaveTextContent("Texto inventado de la API.");
  });

  it("renombra y cambia el ícono: solo envía lo que cambió", async () => {
    const { usuario, peticiones } = montar(apiConEstado());
    await hoja("Reglas");
    await usuario.click(screen.getByRole("button", { name: "Editar Antojos" }));
    const d = dialogo();
    expect(within(d).getByRole("heading", { name: "Editar Antojos" })).toBeVisible();
    // La clase no se cambia al editar.
    expect(within(d).queryByRole("radio", { name: "Ingreso" })).toBeNull();
    expect(within(d).getByText("Categoría de gasto")).toBeVisible();
    const nombre = within(d).getByLabelText("Nombre");
    await usuario.clear(nombre);
    await usuario.type(nombre, "Caprichos");
    await usuario.click(within(d).getByRole("radio", { name: "Monedas" }));
    await usuario.click(within(d).getByRole("button", { name: "Guardar cambios" }));
    expect(await screen.findByText("Cambios guardados en Caprichos.")).toBeVisible();
    const patch = peticiones.find((p) => p.method === "PATCH")!;
    expect(new URL(patch.url).pathname).toBe("/api/categorias/9");
    expect(patch.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
    expect(await patch.json()).toEqual({ nombre: "Caprichos", icono: "coins" });
  });

  it("borrar: elige a qué categoría de la misma clase pasan sus movimientos y reglas", async () => {
    const { usuario, peticiones } = montar(apiConEstado());
    await hoja("Reglas");
    await usuario.click(screen.getByRole("button", { name: "Editar Antojos" }));
    await usuario.click(within(dialogo()).getByRole("button", { name: "Borrar categoría" }));
    const d = dialogo();
    expect(within(d).getByRole("heading", { name: "Borrar la categoría Antojos" })).toBeVisible();
    expect(d).toHaveAccessibleDescription(
      "Antojos tiene 12 movimientos y 1 regla. Elige a qué categoría pasan; los movimientos no se borran.",
    );
    const destino = within(d).getByLabelText("Pasar movimientos y reglas a");
    expect(destino).toHaveDisplayValue("Otros");
    // Solo de gasto y sin ella misma.
    const opciones = within(destino).getAllByRole("option").map((o) => o.textContent);
    expect(opciones).not.toContain("Antojos");
    expect(opciones).not.toContain("Sueldo");
    expect(within(d).getByRole("button", { name: "Borrar y pasar a Otros" })).toBeVisible();
    await usuario.selectOptions(destino, "Compras");
    await usuario.click(within(d).getByRole("button", { name: "Borrar y pasar a Compras" }));
    expect(
      await screen.findByText("Categoría Antojos borrada: 12 movimientos y 1 regla pasaron a Compras."),
    ).toBeVisible();
    const borrar = peticiones.find((p) => p.method === "DELETE")!;
    expect(new URL(borrar.url).pathname).toBe("/api/categorias/9");
    expect(new URL(borrar.url).searchParams.get("mover_a")).toBe("7");
    expect(borrar.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
    await waitFor(async () =>
      expect(within(await hoja("Categorías de gasto")).queryByText("Antojos")).toBeNull(),
    );
  });

  it("borrar una regla es tocar y deshacer: sin confirmación", async () => {
    const { usuario, peticiones } = montar(apiConEstado());
    const reglas = await hoja("Reglas");
    await usuario.click(within(reglas).getAllByRole("button", { name: "Borrar regla" })[2]!);
    expect(screen.queryByRole("dialog")).toBeNull();
    const aviso = await screen.findByRole("status");
    expect(aviso).toHaveTextContent("Regla borrada. Los movimientos que ya categorizó conservan su categoría.");
    expect(within(aviso).getByRole("button", { name: "Deshacer" })).toBeVisible();
    expect(aviso).toHaveFocus();
    const borrar = peticiones.find((p) => p.method === "DELETE")!;
    expect(new URL(borrar.url).pathname).toBe("/api/reglas/23");
    expect(borrar.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
    await waitFor(() => expect(within(reglas).getAllByRole("listitem")).toHaveLength(2));
  });

  it("Deshacer devuelve la regla a la lista", async () => {
    const { usuario, peticiones } = montar(apiConEstado());
    const reglas = await hoja("Reglas");
    const frase = within(reglas).getAllByRole("listitem")[2]!.textContent;
    await usuario.click(within(reglas).getAllByRole("button", { name: "Borrar regla" })[2]!);
    await waitFor(() => expect(within(reglas).getAllByRole("listitem")).toHaveLength(2));
    await usuario.click(await screen.findByRole("button", { name: "Deshacer" }));
    expect(await screen.findByText("Regla restaurada.")).toBeVisible();
    await waitFor(() => expect(within(reglas).getAllByRole("listitem")).toHaveLength(3));
    expect(within(reglas).getAllByRole("listitem")[2]!.textContent).toBe(frase);
    expect(screen.queryByRole("button", { name: "Deshacer" })).toBeNull();
    const post = peticiones.find((p) => p.method === "POST" && new URL(p.url).pathname === "/api/deshacer")!;
    expect(post.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
    expect(await post.json()).toEqual({ token: "token-deshacer-inventado" });
  });

  it("el aviso de deshacer desaparece cuando se acaban los segundos del servidor", async () => {
    const { usuario } = montar(apiConEstado(1));
    const reglas = await hoja("Reglas");
    await usuario.click(within(reglas).getAllByRole("button", { name: "Borrar regla" })[2]!);
    expect(await screen.findByRole("button", { name: "Deshacer" })).toBeVisible();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Deshacer" })).toBeNull(), { timeout: 3000 });
    expect(screen.queryByRole("status")).toBeNull();
    expect(document.activeElement).not.toBe(document.body);
  });

  it("una categoría sin movimientos ni reglas se borra al tocar y se puede deshacer", async () => {
    const { usuario, peticiones } = montar(apiConEstado());
    await hoja("Reglas");
    await usuario.click(screen.getByRole("button", { name: "Editar Préstamos" }));
    await usuario.click(within(dialogo()).getByRole("button", { name: "Borrar categoría" }));
    // Sin segundo diálogo: se borra y se ofrece deshacer.
    expect(await screen.findByText("Categoría Préstamos borrada.")).toBeVisible();
    expect(screen.queryByRole("dialog")).toBeNull();
    const borrar = peticiones.find((p) => p.method === "DELETE")!;
    expect(new URL(borrar.url).pathname).toBe("/api/categorias/11");
    expect(new URL(borrar.url).searchParams.has("mover_a")).toBe(false);
    await waitFor(async () =>
      expect(within(await hoja("Categorías de ingreso")).queryByText("Préstamos")).toBeNull(),
    );

    await usuario.click(screen.getByRole("button", { name: "Deshacer" }));
    expect(await screen.findByText("Categoría Préstamos restaurada.")).toBeVisible();
    await waitFor(async () =>
      expect(within(await hoja("Categorías de ingreso")).getByText("Préstamos")).toBeVisible(),
    );
  });

  it("una categoría con movimientos o reglas sigue pidiendo confirmación (no se deshace)", async () => {
    const { usuario } = montar(apiConEstado());
    await hoja("Reglas");
    await usuario.click(screen.getByRole("button", { name: "Editar Mercado" }));
    await usuario.click(within(dialogo()).getByRole("button", { name: "Borrar categoría" }));
    expect(within(dialogo()).getByRole("heading", { name: "Borrar la categoría Mercado" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Deshacer" })).toBeNull();
  });

  it("un 410 al deshacer dice que ya no se puede", async () => {
    const rutas = apiConEstado();
    const { usuario } = montar({
      ...rutas,
      "POST /api/deshacer": {
        estado: 410,
        cuerpo: { detalle: "Ya no se puede deshacer: pasó el tiempo o ya se deshizo." },
      },
    });
    const reglas = await hoja("Reglas");
    await usuario.click(within(reglas).getAllByRole("button", { name: "Borrar regla" })[2]!);
    await usuario.click(await screen.findByRole("button", { name: "Deshacer" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Ya no se puede deshacer: pasó el tiempo o ya se deshizo.",
    );
    expect(screen.queryByRole("button", { name: "Deshacer" })).toBeNull();
  });

  it("un 409 al deshacer muestra el motivo de la API", async () => {
    const detalle = "No se puede deshacer: la categoría de la regla ya no existe.";
    const rutas = apiConEstado();
    const { usuario } = montar({ ...rutas, "POST /api/deshacer": { estado: 409, cuerpo: { detalle } } });
    const reglas = await hoja("Reglas");
    await usuario.click(within(reglas).getAllByRole("button", { name: "Borrar regla" })[2]!);
    await usuario.click(await screen.findByRole("button", { name: "Deshacer" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(detalle);
  });

  it("sin reglas, dice cómo se crean", async () => {
    const rutas = apiConEstado();
    rutas["GET /api/reglas"] = ok({ reglas: [] });
    montar(rutas);
    const reglas = await hoja("Reglas");
    expect(within(reglas).getByRole("heading", { name: "Todavía no hay reglas" })).toBeVisible();
    expect(within(reglas).getByRole("link", { name: "Ir a Movimientos" })).toHaveAttribute("href", "/movimientos");
  });

  it("si falla al cargar, lo dice y deja volver a intentar", async () => {
    const rutas = apiConEstado();
    rutas["GET /api/reglas"] = "sin-red";
    montar(rutas);
    expect(await screen.findByRole("alert")).toHaveTextContent("No hay conexión con la app.");
    expect(screen.getByRole("button", { name: "Volver a intentar" })).toBeVisible();
  });
});
