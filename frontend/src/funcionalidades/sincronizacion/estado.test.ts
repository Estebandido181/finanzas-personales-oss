import { describe, expect, it } from "vitest";
import { sincronizacionCorrecta, sincronizacionFallida } from "@/pruebas/inicio-inventado";
import { textoResultado, vistaSincronizacion } from "./estado";
const SIN_NADA = { nuevos: 0, duplicados: 0, no_reconocidos: 0, errores: 0, rechazados_autenticacion: 0 };

describe("estado de la sincronización", () => {
  const HOY = "2026-09-30";

  it("nunca se ha sincronizado", () => {
    expect(vistaSincronizacion({ en_curso: false, ultima: null, ultima_correcta_en: null, debe_sincronizar_al_abrir: false }, HOY)).toEqual({
      tipo: "nunca",
      texto: "Todavía no se ha sincronizado.",
    });
  });

  it("correcta", () => {
    expect(vistaSincronizacion(sincronizacionCorrecta(), HOY)).toEqual({
      tipo: "correcta",
      texto: "Sincronizado hoy a las 6:02 a. m.",
    });
  });

  it("con errores de algunos correos cuenta como correcta", () => {
    const estado = sincronizacionCorrecta();
    estado.ultima!.estado = "con_errores";
    expect(vistaSincronizacion(estado, HOY).tipo).toBe("correcta");
  });

  it("fallida por el permiso de Gmail, con la última correcta", () => {
    expect(vistaSincronizacion(sincronizacionFallida(), HOY)).toEqual({
      tipo: "fallida",
      texto: "Falló la sincronización. Última correcta: 28 de septiembre, 12:00 p. m.",
      codigo: "autorizacion_gmail",
      desde: "28 de septiembre",
      mensajeApi: "Mensaje inventado de la API para este error.",
    });
  });

  it("fallida sin ninguna correcta antes", () => {
    const vista = vistaSincronizacion(sincronizacionFallida(null, "error_inesperado"), HOY);
    expect(vista).toMatchObject({ tipo: "fallida", texto: "Falló la sincronización. Todavía no hay ninguna sincronización correcta.",
      desde: null, });
  });
});

describe("resultado de «Sincronizar ahora»", () => {
  it("sin nada nuevo", () => {
    expect(textoResultado(SIN_NADA)).toBe("Sincronización terminada: no hay movimientos nuevos.");
  });

  it("los nuevos, en singular y plural; los duplicados no se mencionan", () => {
    expect(textoResultado({ ...SIN_NADA, nuevos: 1, duplicados: 5 })).toBe(
      "Sincronización terminada: 1 movimiento nuevo.",
    );
    expect(textoResultado({ ...SIN_NADA, nuevos: 4 })).toBe("Sincronización terminada: 4 movimientos nuevos.");
  });

  it("con errores (TEXTOS.md)", () => {
    expect(textoResultado({ ...SIN_NADA, nuevos: 4, errores: 2 })).toBe(
      "Sincronización terminada: 4 movimientos nuevos y 2 correos que no se pudieron leer: " +
        "se reintentan en la próxima sincronización.",
    );
  });

  it("los no reconocidos (también los rechazados) y los errores", () => {
    expect(textoResultado({ ...SIN_NADA, nuevos: 4, no_reconocidos: 1 })).toBe(
      "Sincronización terminada: 4 movimientos nuevos y 1 correo no reconocido (ver No reconocidos).",
    );
    expect(
      textoResultado({ ...SIN_NADA, nuevos: 2, no_reconocidos: 1, rechazados_autenticacion: 1, errores: 1 }),
    ).toBe(
      "Sincronización terminada: 2 movimientos nuevos y 2 correos no reconocidos (ver No reconocidos) " +
        "y 1 correo que no se pudo leer: se reintenta en la próxima sincronización.",
    );
  });
});
