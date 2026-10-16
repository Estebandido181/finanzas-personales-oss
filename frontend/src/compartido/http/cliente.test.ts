import { afterEach, describe, expect, it, vi } from "vitest";
import { simularApi } from "@/pruebas/api-simulada";
import {
  alCerrarseLaSesion,
  cabeceraCsrf,
  ENCABEZADO_CSRF,
  ErrorSinToken,
  guardarTokenCsrf,
  hayTokenCsrf,
} from "@/compartido/http/cliente";
import { detalleDe, mensajeDeError, mensajeDeErrorAlEntrar } from "@/compartido/http/errores";

afterEach(() => {
  guardarTokenCsrf(null);
  alCerrarseLaSesion(null);
});

describe("token CSRF", () => {
  it("sin token no se arma el encabezado", () => {
    expect(hayTokenCsrf()).toBe(false);
    expect(() => cabeceraCsrf()).toThrow(ErrorSinToken);
  });

  it("con token, el encabezado es X-CSRF-Token", () => {
    guardarTokenCsrf("abc");
    expect(cabeceraCsrf()).toEqual({ [ENCABEZADO_CSRF]: "abc" });
  });

  it("vive solo en memoria: nada en localStorage ni sessionStorage", () => {
    guardarTokenCsrf("abc");
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});

describe("cliente", () => {
  it("pide al mismo origen, con la cookie del mismo sitio", async () => {
    const { cliente, peticiones } = simularApi({ "GET /api/sesion": { estado: 401 } });
    await cliente.GET("/api/sesion");
    const [peticion] = peticiones;
    expect(new URL(peticion!.url).origin).toBe(location.origin);
    expect(peticion!.credentials).toBe("same-origin");
  });

  it("un 401 avisa que la sesión se cerró y borra el token", async () => {
    const aviso = vi.fn();
    alCerrarseLaSesion(aviso);
    guardarTokenCsrf("abc");
    const { cliente } = simularApi({ "GET /api/reporte": { estado: 401 } });
    await cliente.GET("/api/reporte", { params: { query: {} } });
    expect(aviso).toHaveBeenCalledOnce();
    expect(hayTokenCsrf()).toBe(false);
  });

  it("un 401 del login (contraseña incorrecta) no es una sesión cerrada", async () => {
    const aviso = vi.fn();
    alCerrarseLaSesion(aviso);
    const { cliente } = simularApi({
      "POST /api/sesion": { estado: 401, cuerpo: { detalle: "Contraseña incorrecta." } },
    });
    await cliente.POST("/api/sesion", { body: { contrasena: "inventada" } });
    expect(aviso).not.toHaveBeenCalled();
  });

  it("otros errores no cierran la sesión", async () => {
    const aviso = vi.fn();
    alCerrarseLaSesion(aviso);
    guardarTokenCsrf("abc");
    const { cliente } = simularApi({ "GET /api/reporte": { estado: 500 } });
    await cliente.GET("/api/reporte", { params: { query: {} } });
    expect(aviso).not.toHaveBeenCalled();
    expect(hayTokenCsrf()).toBe(true);
  });
});

describe("mensajes de error (TEXTOS.md)", () => {
  it("sin respuesta: sin conexión", () => {
    expect(mensajeDeError(null)).toBe(
      "No hay conexión con la app. Revisa tu internet y vuelve a intentarlo.",
    );
  });

  it("401 fuera del login: sesión cerrada; en el login: contraseña", () => {
    expect(mensajeDeError(401)).toBe("Tu sesión se cerró. Entra de nuevo para seguir.");
    expect(mensajeDeErrorAlEntrar(401)).toBe(
      "Contraseña incorrecta. Revísala y vuelve a intentarlo.",
    );
  });

  it("al entrar, cualquier otro error: «No se pudo entrar…»", () => {
    for (const estado of [403, 415, 500, 503]) {
      expect(mensajeDeErrorAlEntrar(estado)).toBe(
        "No se pudo entrar. Vuelve a intentarlo en unos minutos.",
      );
    }
    expect(mensajeDeErrorAlEntrar(null)).toMatch(/^No hay conexión/);
  });

  it("429: demasiados intentos", () => {
    expect(mensajeDeErrorAlEntrar(429)).toBe(
      "Demasiados intentos fallidos. Espera unos minutos y vuelve a intentarlo.",
    );
  });

  it("otros: el detalle de la API, o un texto general si no viene", () => {
    expect(mensajeDeError(403, "Petición rechazada.")).toBe("Petición rechazada.");
    expect(mensajeDeError(500)).toBe(
      "La app no pudo completar la acción. Vuelve a intentarlo en unos minutos.",
    );
    expect(mensajeDeError(500, "   ")).toMatch(/^La app no pudo/);
  });

  it("detalleDe solo acepta textos", () => {
    expect(detalleDe({ detalle: "x" })).toBe("x");
    expect(detalleDe({ detalle: 3 })).toBeUndefined();
    expect(detalleDe(null)).toBeUndefined();
    expect(detalleDe("x")).toBeUndefined();
  });
});
