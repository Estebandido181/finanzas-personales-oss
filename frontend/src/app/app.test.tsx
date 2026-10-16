import { render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { memoryLocation } from "wouter/memory-location";
import { guardarTokenCsrf } from "@/compartido/http/cliente";
import { reiniciarFocoDePantallas } from "@/compartido/ui/pantalla";
import { saldoInventado } from "@/pruebas/saldo-inventado";
import {
  SESION_INVENTADA,
  simularApi,
  TOKEN_INVENTADO,
  type Manejador,
  type Respuesta,
} from "@/pruebas/api-simulada";
import { reiniciarTemaEnMemoria } from "@/compartido/tema/preferencias";
import { mesActualColombia, tituloMes } from "@/compartido/formatos/formato";
import { useSincronizarAlAbrir } from "@/funcionalidades/sincronizacion/sincronizar";
import { App } from "@/app/app";

/** Inicio se titula con el mes actual ("Septiembre de 2026"). */
const TITULO_INICIO = tituloMes(mesActualColombia());

const SIN_SESION = { estado: 401, cuerpo: { detalle: "Inicia sesión para continuar." } };
const CON_SESION = { estado: 200, cuerpo: SESION_INVENTADA };
const SIN_CORREOS = { estado: 200, cuerpo: { correos: [] } };
const TRES_CORREOS = {
  estado: 200,
  cuerpo: {
    correos: [1, 2, 3].map((n) => ({
      gmail_id: `correo-inventado-${n}`,
      fecha: "2026-09-29",
      asunto: "Asunto inventado",
    })),
  },
};

function montar(rutas: Record<string, Manejador | Respuesta>, ruta = "/") {
  const api = simularApi(rutas);
  const ubicacion = memoryLocation({ path: ruta, record: true });
  const usuario = userEvent.setup();
  render(<App cliente={api.cliente} hook={ubicacion.hook} />);
  return { ...api, ubicacion, usuario };
}

beforeEach(() => {
  reiniciarTemaEnMemoria();
  reiniciarFocoDePantallas();
});
afterEach(() => guardarTokenCsrf(null));

describe("entrar", () => {
  it("sin sesión muestra la pantalla de entrar", async () => {
    montar({ "GET /api/sesion": SIN_SESION });
    expect(await screen.findByRole("heading", { level: 1, name: "Finanzas personales" })).toBeVisible();
    expect(screen.getByLabelText("Contraseña")).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Entrar" })).toBeEnabled();
    expect(screen.queryByRole("navigation")).toBeNull();
  });

  it("contraseña vacía: error en el campo, sin llamar a la API", async () => {
    const { usuario, peticiones } = montar({ "GET /api/sesion": SIN_SESION });
    await usuario.click(await screen.findByRole("button", { name: "Entrar" }));
    const campo = screen.getByLabelText("Contraseña");
    expect(campo).toHaveAttribute("aria-invalid", "true");
    expect(campo).toHaveAccessibleDescription("Escribe tu contraseña.");
    expect(peticiones.filter((p) => p.method === "POST")).toHaveLength(0);
  });

  it("contraseña incorrecta: error debajo del campo y el campo se vacía", async () => {
    const { usuario } = montar({
      "GET /api/sesion": SIN_SESION,
      "POST /api/sesion": { estado: 401, cuerpo: { detalle: "Contraseña incorrecta." } },
    });
    await usuario.type(await screen.findByLabelText("Contraseña"), "clave-inventada");
    await usuario.click(screen.getByRole("button", { name: "Entrar" }));
    const campo = await screen.findByLabelText("Contraseña");
    await waitFor(() =>
      expect(campo).toHaveAccessibleDescription(
        "Contraseña incorrecta. Revísala y vuelve a intentarlo.",
      ),
    );
    expect(campo).toHaveValue("");
    expect(campo).toHaveFocus();
  });

  it("demasiados intentos: aviso junto al botón", async () => {
    const { usuario } = montar({
      "GET /api/sesion": SIN_SESION,
      "POST /api/sesion": { estado: 429, cuerpo: { detalle: "Demasiados intentos fallidos." } },
    });
    await usuario.type(await screen.findByLabelText("Contraseña"), "clave-inventada");
    await usuario.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Demasiados intentos fallidos. Espera unos minutos y vuelve a intentarlo.",
    );
    expect(screen.getByLabelText("Contraseña")).not.toHaveAttribute("aria-invalid");
  });

  it("error del servidor al entrar: «No se pudo entrar…»", async () => {
    const { usuario } = montar({
      "GET /api/sesion": SIN_SESION,
      "POST /api/sesion": { estado: 500, cuerpo: { detalle: "Error." } },
    });
    await usuario.type(await screen.findByLabelText("Contraseña"), "clave-inventada");
    await usuario.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No se pudo entrar. Vuelve a intentarlo en unos minutos.",
    );
  });

  it("sin red al entrar: lo dice", async () => {
    const { usuario } = montar({ "GET /api/sesion": SIN_SESION, "POST /api/sesion": "sin-red" });
    await usuario.type(await screen.findByLabelText("Contraseña"), "clave-inventada");
    await usuario.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No hay conexión con la app.");
  });

  it("mientras entra, el botón dice «Entrando…» y queda deshabilitado", async () => {
    let responder: (r: Respuesta) => void = () => {};
    const { usuario } = montar({
      "GET /api/sesion": SIN_SESION,
      "POST /api/sesion": () => new Promise<Respuesta>((r) => (responder = r)),
      "GET /api/no-reconocidos": SIN_CORREOS,
    });
    await usuario.type(await screen.findByLabelText("Contraseña"), "clave-inventada");
    await usuario.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("button", { name: "Entrando…" })).toBeDisabled();
    responder(CON_SESION);
    expect(await screen.findByRole("heading", { level: 1, name: TITULO_INICIO })).toBeVisible();
  });

  it("al entrar envía JSON con la contraseña y muestra la navegación", async () => {
    const { usuario, peticiones } = montar({
      "GET /api/sesion": SIN_SESION,
      "POST /api/sesion": CON_SESION,
      "GET /api/no-reconocidos": SIN_CORREOS,
    });
    await usuario.type(await screen.findByLabelText("Contraseña"), "clave-inventada");
    await usuario.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("heading", { level: 1, name: TITULO_INICIO })).toBeVisible();
    const login = peticiones.find((p) => p.method === "POST")!;
    expect(login.headers.get("content-type")).toBe("application/json");
    expect(await login.json()).toEqual({ contrasena: "clave-inventada" });
    expect(screen.getAllByRole("navigation", { name: "Secciones" })).toHaveLength(2);
  });

  it("entrar cuenta como abrir la app: Inicio puede volver a sincronizar al abrir (ítem 38)", async () => {
    // Una apertura anterior ya sincronizó al abrir.
    const antes = vi.fn(async () => {});
    renderHook(() => useSincronizarAlAbrir(true, antes)).unmount();
    expect(antes).toHaveBeenCalledTimes(1);
    const { usuario } = montar({
      "GET /api/sesion": SIN_SESION,
      "POST /api/sesion": CON_SESION,
      "GET /api/no-reconocidos": SIN_CORREOS,
    });
    await usuario.type(await screen.findByLabelText("Contraseña"), "clave-inventada");
    await usuario.click(screen.getByRole("button", { name: "Entrar" }));
    await screen.findByRole("heading", { level: 1, name: TITULO_INICIO });
    const despues = vi.fn(async () => {});
    renderHook(() => useSincronizarAlAbrir(true, despues));
    expect(despues).toHaveBeenCalledTimes(1);
  });
});

describe("al abrir la app", () => {
  it("con sesión entra directo, sin pasar por la pantalla de entrar", async () => {
    montar({ "GET /api/sesion": CON_SESION, "GET /api/no-reconocidos": SIN_CORREOS });
    expect(await screen.findByRole("heading", { level: 1, name: TITULO_INICIO })).toBeVisible();
    expect(screen.queryByLabelText("Contraseña")).toBeNull();
  });

  it("mientras pregunta, dice «Cargando…», pero solo pasados 300 ms (sin parpadeo)", async () => {
    montar({ "GET /api/sesion": () => new Promise<Respuesta>(() => {}) });
    expect(screen.queryByRole("status")).toBeNull();
    expect(await screen.findByRole("status")).toHaveTextContent("Cargando…");
  });

  it("si el servidor falla (5xx), lo dice en vez de pedir la contraseña", async () => {
    let falla = true;
    const { usuario } = montar({
      "GET /api/sesion": () => (falla ? { estado: 500 } : CON_SESION),
      "GET /api/no-reconocidos": SIN_CORREOS,
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La app no pudo completar la acción. Vuelve a intentarlo en unos minutos.",
    );
    expect(screen.queryByLabelText("Contraseña")).toBeNull();
    falla = false;
    await usuario.click(screen.getByRole("button", { name: "Volver a intentar" }));
    expect(await screen.findByRole("heading", { level: 1, name: TITULO_INICIO })).toBeVisible();
  });

  it("sin red: lo dice y deja volver a intentar", async () => {
    let conRed = false;
    const { usuario } = montar({
      "GET /api/sesion": () => (conRed ? CON_SESION : "sin-red"),
      "GET /api/no-reconocidos": SIN_CORREOS,
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("No hay conexión con la app.");
    conRed = true;
    await usuario.click(screen.getByRole("button", { name: "Volver a intentar" }));
    expect(await screen.findByRole("heading", { level: 1, name: TITULO_INICIO })).toBeVisible();
  });
});

describe("navegación", () => {
  it("marca la sección actual con aria-current y cambia al tocar otra", async () => {
    const { usuario, ubicacion } = montar({
      "GET /api/sesion": CON_SESION,
      "GET /api/no-reconocidos": SIN_CORREOS,
    });
    const [lateral, inferior] = await screen.findAllByRole("navigation", { name: "Secciones" });
    expect(within(inferior!).getByRole("link", { name: "Inicio" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await usuario.click(within(inferior!).getByRole("link", { name: "Saldo" }));
    expect(ubicacion.history?.at(-1)).toBe("/saldo");
    const h1 = await screen.findByRole("heading", { level: 1, name: "Saldo" });
    expect(h1).toHaveFocus(); // al cambiar de sección, el foco va al título
    expect(within(lateral!).getByRole("link", { name: "Saldo" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(lateral!).getByRole("link", { name: "Inicio" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("Saldo ya tiene su pantalla (ítem 16)", async () => {
    montar(
      {
        "GET /api/sesion": CON_SESION,
        "GET /api/no-reconocidos": SIN_CORREOS,
        "GET /api/saldo": { estado: 200, cuerpo: saldoInventado() },
      },
      "/saldo",
    );
    expect(await screen.findByRole("region", { name: "Registrar un ingreso" })).toBeVisible();
  });

  it("una dirección desconocida lo dice y ofrece volver al inicio", async () => {
    montar({ "GET /api/sesion": CON_SESION, "GET /api/no-reconocidos": SIN_CORREOS }, "/no-existe");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Esta página no existe" }),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "Volver al inicio" })).toBeVisible();
  });

  it("el contador de no reconocidos se lee como «3 correos»", async () => {
    montar({ "GET /api/sesion": CON_SESION, "GET /api/no-reconocidos": TRES_CORREOS });
    const [lateral] = await screen.findAllByRole("navigation", { name: "Secciones" });
    expect(
      await within(lateral!).findByRole("link", { name: /^No reconocidos\s*3 correos$/ }),
    ).toBeVisible();
  });

  it("si el contador falla, la navegación sigue sin él", async () => {
    montar({ "GET /api/sesion": CON_SESION, "GET /api/no-reconocidos": "sin-red" });
    const [lateral] = await screen.findAllByRole("navigation", { name: "Secciones" });
    expect(within(lateral!).getByRole("link", { name: "No reconocidos" })).toBeVisible();
  });
});

describe("Más, apariencia y cerrar sesión", () => {
  it("la apariencia se elige con botones aria-pressed y se aplica a <html>", async () => {
    const { usuario } = montar(
      { "GET /api/sesion": CON_SESION, "GET /api/no-reconocidos": SIN_CORREOS },
      "/mas",
    );
    // Hay dos grupos "Apariencia": el de la barra lateral y el de "Más" (el último).
    const grupo = (await screen.findAllByRole("group", { name: "Apariencia" })).at(-1)!;
    const oscuro = within(grupo).getByRole("button", { name: "Oscuro" });
    expect(within(grupo).getByRole("button", { name: "Sistema" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await usuario.click(oscuro);
    expect(oscuro).toHaveAttribute("aria-pressed", "true");
    expect(document.documentElement.dataset.tema).toBe("oscuro");
    expect(localStorage.getItem("finanzas-tema")).toBe("oscuro");
  });

  it("cerrar sesión envía DELETE con el token CSRF y vuelve a entrar", async () => {
    const { usuario, peticiones } = montar(
      {
        "GET /api/sesion": CON_SESION,
        "GET /api/no-reconocidos": SIN_CORREOS,
        "DELETE /api/sesion": { estado: 204 },
      },
      "/mas",
    );
    await screen.findByRole("heading", { level: 1, name: "Más" });
    const [, botonDeMas] = screen.getAllByRole("button", { name: "Cerrar sesión" });
    await usuario.click(botonDeMas!);
    expect(await screen.findByLabelText("Contraseña")).toBeVisible();
    const cierre = peticiones.find((p) => p.method === "DELETE")!;
    expect(cierre.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
  });

  it("si el servidor falla al cerrar sesión, lo dice en un aviso y sigue dentro", async () => {
    const { usuario } = montar(
      {
        "GET /api/sesion": CON_SESION,
        "GET /api/no-reconocidos": SIN_CORREOS,
        "DELETE /api/sesion": { estado: 500 },
      },
      "/mas",
    );
    await screen.findByRole("heading", { level: 1, name: "Más" });
    const [, botonDeMas] = screen.getAllByRole("button", { name: "Cerrar sesión" });
    await usuario.click(botonDeMas!);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No se pudo cerrar la sesión. Vuelve a intentarlo en unos minutos.",
    );
    expect(screen.getByRole("heading", { level: 1, name: "Más" })).toBeVisible();
  });

  it("si cerrar sesión falla sin red, lo dice y sigue dentro", async () => {
    const { usuario } = montar(
      {
        "GET /api/sesion": CON_SESION,
        "GET /api/no-reconocidos": SIN_CORREOS,
        "DELETE /api/sesion": "sin-red",
      },
      "/mas",
    );
    await screen.findByRole("heading", { level: 1, name: "Más" });
    const [, botonDeMas] = screen.getAllByRole("button", { name: "Cerrar sesión" });
    await usuario.click(botonDeMas!);
    expect(await screen.findByRole("alert")).toHaveTextContent("No hay conexión con la app.");
    expect(screen.getByRole("heading", { level: 1, name: "Más" })).toBeVisible();
  });

  it("un 401 con la sesión abierta vuelve a entrar con «Tu sesión se cerró»", async () => {
    // Cualquier llamada con 401 estando dentro (aquí, la del contador).
    montar({ "GET /api/sesion": CON_SESION, "GET /api/no-reconocidos": SIN_SESION });
    expect(
      await screen.findByText("Tu sesión se cerró. Entra de nuevo para seguir."),
    ).toBeVisible();
    expect(screen.getByLabelText("Contraseña")).toBeVisible();
  });

  it("cerrar sesión cuando ya se había cerrado por fuera: lo dice", async () => {
    const { usuario } = montar(
      {
        "GET /api/sesion": CON_SESION,
        "GET /api/no-reconocidos": SIN_CORREOS,
        "DELETE /api/sesion": SIN_SESION,
      },
      "/mas",
    );
    await screen.findByRole("heading", { level: 1, name: "Más" });
    const [, botonDeMas] = screen.getAllByRole("button", { name: "Cerrar sesión" });
    await usuario.click(botonDeMas!);
    expect(
      await screen.findByText("Tu sesión se cerró. Entra de nuevo para seguir."),
    ).toBeVisible();
  });
});
