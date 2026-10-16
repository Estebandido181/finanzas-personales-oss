import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
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
import { reiniciarTemaEnMemoria } from "@/compartido/tema/preferencias";

type Correo = Esquemas["CorreoNoReconocido"];
type Resultado = Esquemas["ResultadoReproceso"];

const ok = (cuerpo: unknown): Respuesta => ({ estado: 200, cuerpo });

const CORREOS: Correo[] = [
  { gmail_id: "c1", fecha: "2026-09-29T21:28:00", asunto: "Alertas y Notificaciones" },
  { gmail_id: "c2", fecha: "2026-09-21T11:02:00", asunto: "Bancolombia te informa" },
  { gmail_id: "c3", fecha: "2026-09-03T18:47:00", asunto: "Aviso de transacción" },
];

function resultado(parcial: Partial<Resultado>): Resultado {
  return { estado: "ok", contadores: null, codigo_error: null, mensaje: "Listo.", ...parcial };
}

/** Una API con estado: al reprocesar, `seReconoce` desaparece de la lista. */
function api(opciones: { seReconoce?: string[]; reproceso?: Manejador | Respuesta } = {}) {
  let lista = [...CORREOS];
  const rutas: Record<string, Manejador | Respuesta> = {
    "GET /api/sesion": ok(SESION_INVENTADA),
    "GET /api/no-reconocidos": () => ok({ correos: lista }),
    "POST /api/no-reconocidos/reprocesar":
      opciones.reproceso ??
      (() => {
        const revisados = lista.length;
        const creados = lista.filter((c) => opciones.seReconoce?.includes(c.gmail_id)).length;
        lista = lista.filter((c) => !opciones.seReconoce?.includes(c.gmail_id));
        return ok(
          resultado({
            contadores: {
              revisados,
              movimientos_creados: creados,
              siguen_sin_reconocerse: revisados - creados,
              ya_registrados: 0,
              errores: 0,
            },
          }),
        );
      }),
  };
  return rutas;
}

function montar(rutas: Record<string, Manejador | Respuesta>) {
  const simulada = simularApi(rutas);
  const ubicacion = memoryLocation({ path: "/no-reconocidos", record: true });
  const usuario = userEvent.setup();
  render(<App cliente={simulada.cliente} hook={ubicacion.hook} searchHook={ubicacion.searchHook} />);
  return { ...simulada, usuario };
}

const lista = () => screen.findByRole("heading", { level: 2, name: /correos?$/ });
const asuntos = () =>
  within(screen.getByRole("list")).getAllByRole("listitem").map((li) => li.querySelector("p")!.textContent);

beforeEach(() => {
  reiniciarTemaEnMemoria();
  reiniciarFocoDePantallas();
});
afterEach(() => guardarTokenCsrf(null));

describe("Correos no reconocidos", () => {
  it("muestra asunto y fecha de cada correo, y el botón", async () => {
    montar(api());
    expect(await screen.findByRole("heading", { level: 1, name: "Correos no reconocidos" })).toBeVisible();
    expect((await lista()).textContent).toBe("3 correos");
    expect(asuntos()).toEqual(["Alertas y Notificaciones", "Bancolombia te informa", "Aviso de transacción"]);
    const primera = screen.getAllByRole("listitem").filter((li) => li.textContent?.includes("Alertas y N"))[0]!;
    expect(primera).toHaveTextContent("29 de septiembre de 2026, 9:28");
    expect(screen.getByRole("button", { name: "Volver a procesar todos" })).toBeEnabled();
    expect(document.title).toBe("Correos no reconocidos · Finanzas personales");
  });

  it("reprocesar: el que se reconoce se va, los otros se quedan y se cuentan", async () => {
    const { usuario, peticiones } = montar(api({ seReconoce: ["c2"] }));
    await lista();
    await usuario.click(screen.getByRole("button", { name: "Volver a procesar todos" }));
    const aviso = await screen.findByRole("status");
    expect(aviso).toHaveTextContent(
      "Se volvieron a procesar 3 correos. 1 creó un movimiento nuevo; 2 siguen sin reconocerse.",
    );
    expect((await lista()).textContent).toBe("2 correos");
    expect(asuntos()).toEqual(["Alertas y Notificaciones", "Aviso de transacción"]);
    const envio = peticiones.find((p) => p.method === "POST")!;
    expect(envio.headers.get("X-CSRF-Token") ?? envio.headers.get("x-csrf-token")).toBe(TOKEN_INVENTADO);
  });

  it("un correo que sigue sin reconocerse permanece en la lista", async () => {
    const { usuario } = montar(api({ seReconoce: [] }));
    await lista();
    await usuario.click(screen.getByRole("button", { name: "Volver a procesar todos" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Ninguno creó un movimiento nuevo; 3 siguen sin reconocerse.",
    );
    expect(asuntos()).toHaveLength(3);
  });

  it("mientras procesa, el botón dice «Procesando…» y queda deshabilitado", async () => {
    let responder: (r: Respuesta) => void = () => {};
    const { usuario } = montar(api({ reproceso: () => new Promise<Respuesta>((r) => (responder = r)) }));
    await lista();
    await usuario.click(screen.getByRole("button", { name: "Volver a procesar todos" }));
    expect(await screen.findByRole("button", { name: "Procesando…" })).toBeDisabled();
    responder(ok(resultado({ contadores: { revisados: 3, movimientos_creados: 0, siguen_sin_reconocerse: 3, ya_registrados: 0, errores: 0 } })));
    await waitFor(() => expect(screen.getByRole("button", { name: "Volver a procesar todos" })).toBeEnabled());
  });

  it("si se reconocen todos, queda el estado vacío y el aviso", async () => {
    const { usuario } = montar(api({ seReconoce: ["c1", "c2", "c3"] }));
    await lista();
    await usuario.click(screen.getByRole("button", { name: "Volver a procesar todos" }));
    expect(await screen.findByRole("heading", { level: 2, name: "No hay correos sin reconocer" })).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent("3 crearon un movimiento nuevo.");
    expect(screen.queryByRole("button", { name: "Volver a procesar todos" })).toBeNull();
    expect(screen.getByRole("link", { name: "Volver al inicio" })).toHaveAttribute("href", "/");
  });

  it("sin correos: estado vacío del prototipo, sin botón", async () => {
    const rutas = api();
    rutas["GET /api/no-reconocidos"] = ok({ correos: [] });
    montar(rutas);
    expect(await screen.findByRole("heading", { level: 2, name: "No hay correos sin reconocer" })).toBeVisible();
    expect(screen.getByText(/Todos los avisos de Bancolombia que llegaron se leyeron bien/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Volver a procesar todos" })).toBeNull();
  });

  it("error al cargar: lo dice y deja volver a intentar", async () => {
    let falla = true;
    const rutas = api();
    rutas["GET /api/no-reconocidos"] = () => (falla ? { estado: 500, cuerpo: { detalle: "Error." } } : ok({ correos: CORREOS }));
    const { usuario } = montar(rutas);
    expect(await screen.findByRole("alert")).toHaveTextContent("Error.");
    falla = false;
    await usuario.click(screen.getByRole("button", { name: "Volver a intentar" }));
    expect((await lista()).textContent).toBe("3 correos");
  });

  it("sin red al cargar", async () => {
    const rutas = api();
    rutas["GET /api/no-reconocidos"] = "sin-red";
    montar(rutas);
    expect(await screen.findByRole("alert")).toHaveTextContent("No hay conexión con la app.");
  });

  it("409: hay una sincronización en curso; la lista no cambia", async () => {
    const { usuario } = montar(api({ reproceso: { estado: 409, cuerpo: { detalle: "Hay una sincronización en curso." } } }));
    await lista();
    await usuario.click(screen.getByRole("button", { name: "Volver a procesar todos" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Ya hay una sincronización en curso. Espera a que termine.",
    );
    expect(asuntos()).toHaveLength(3);
    expect(screen.getByRole("button", { name: "Volver a procesar todos" })).toBeEnabled();
  });

  it("falló con permiso de Gmail rechazado: mismo aviso que Sincronizar, con la guía", async () => {
    const { usuario } = montar(
      api({
        reproceso: ok(resultado({ estado: "fallida", codigo_error: "autorizacion_gmail", mensaje: "Gmail rechazó." })),
      }),
    );
    await lista();
    await usuario.click(screen.getByRole("button", { name: "Volver a procesar todos" }));
    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent("Gmail rechazó el permiso de lectura de la app");
    expect(within(aviso).getByRole("link", { name: "Ver cómo autorizar Gmail" })).toBeVisible();
    expect(asuntos()).toHaveLength(3);
  });

  it("falló sin fecha de inicio: muestra el mensaje de la API", async () => {
    const { usuario } = montar(
      api({
        reproceso: ok(
          resultado({ estado: "fallida", codigo_error: "sin_fecha_inicio", mensaje: "Falta configurar el saldo inicial." }),
        ),
      }),
    );
    await lista();
    await usuario.click(screen.getByRole("button", { name: "Volver a procesar todos" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Falta configurar el saldo inicial.");
  });

  it("sin red al reprocesar", async () => {
    const { usuario } = montar(api({ reproceso: "sin-red" }));
    await lista();
    await usuario.click(screen.getByRole("button", { name: "Volver a procesar todos" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No hay conexión con la app.");
  });

  it("el contador del menú se actualiza con la lista", async () => {
    const { usuario } = montar(api({ seReconoce: ["c1"] }));
    await lista();
    const barra = () => screen.getAllByRole("navigation", { name: "Secciones" })[0]!;
    await waitFor(() => expect(within(barra()).getByRole("link", { name: /No reconocidos/ })).toHaveTextContent("3 correos"));
    await usuario.click(screen.getByRole("button", { name: "Volver a procesar todos" }));
    await waitFor(() => expect(within(barra()).getByRole("link", { name: /No reconocidos/ })).toHaveTextContent("2 correos"));
  });
});
