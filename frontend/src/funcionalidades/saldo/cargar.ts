/**
 * Cómo "Saldo" habla con la API (ítem 16): leer el saldo, registrar un
 * ingreso, ajustar el saldo y borrar un ingreso manual. Todo lo que cambia
 * datos lleva el token CSRF (`cabeceraCsrf`).
 *
 * El frontend no decide qué se puede borrar: lo dice `se_puede_borrar` y, al
 * borrar, la API lo vuelve a comprobar (409 si no se permite).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { cabeceraCsrf, ErrorSinToken, sesionPerdida, type ClienteApi, type Esquemas } from "@/compartido/http/cliente";
import { detalleDe, mensajeDeError } from "@/compartido/http/errores";
import { esSinRed } from "@/compartido/http/respuesta";
import { TEXTOS } from "@/compartido/textos/textos";
import type { Saldo } from "@/funcionalidades/saldo/datos";

export type Carga =
  | { tipo: "cargando" }
  | { tipo: "error"; sinRed: boolean; mensaje: string }
  | { tipo: "listo"; datos: Saldo; actualizando: boolean };

/** Lee la pantalla de saldo (cada lectura trae un `token_ingreso` nuevo). */
export async function leerSaldo(cliente: ClienteApi): Promise<Carga> {
  try {
    const { data, error, response } = await cliente.GET("/api/saldo");
    if (data) return { tipo: "listo", datos: data, actualizando: false };
    return { tipo: "error", sinRed: false, mensaje: mensajeDeError(response.status, detalleDe(error)) };
  } catch (e) {
    if (esSinRed(e)) return { tipo: "error", sinRed: true, mensaje: mensajeDeError(null) };
    return { tipo: "error", sinRed: false, mensaje: TEXTOS.errores.fallaDelServidor };
  }
}

/**
 * Los datos de la pantalla. `recargar(true)` vuelve a pedirlos sin pasar por
 * "Cargando…": la pantalla sigue mostrando lo anterior mientras tanto.
 */
export function useDatosSaldo(cliente: ClienteApi) {
  const [carga, setCarga] = useState<Carga>({ tipo: "cargando" });
  const pedido = useRef(0);

  const recargar = useCallback(
    async (silencioso = false) => {
      const este = ++pedido.current;
      setCarga((antes) =>
        silencioso && antes.tipo === "listo" ? { ...antes, actualizando: true } : { tipo: "cargando" },
      );
      const nueva = await leerSaldo(cliente);
      if (este === pedido.current) setCarga(nueva);
    },
    [cliente],
  );

  useEffect(() => {
    void recargar();
    return () => {
      pedido.current++;
    };
  }, [recargar]);

  return { carga, recargar };
}

/** Resultado de algo que cambia datos. `estado` es el código HTTP del error (o `null` sin red). */
export type Resultado<T> =
  | { tipo: "ok"; datos: T }
  | { tipo: "error"; texto: string; estado: number | null }
  /** La sesión se perdió: la app ya vuelve a "Entrar". */
  | { tipo: "sin-sesion" };

/**
 * Hace la llamada y traduce el resultado. Los errores de la API traen
 * `detalle`, ya escrito para el dueño (por ejemplo, por qué no se puede
 * borrar un ingreso): se muestra tal cual. `textos` cambia el de algún código.
 */
async function enviar<T>(
  llamada: () => Promise<{ data?: T; error?: unknown; response: Response }>,
  textos: Partial<Record<number, string>> = {},
): Promise<Resultado<T>> {
  try {
    const { data, error, response } = await llamada();
    if (response.ok && data !== undefined) return { tipo: "ok", datos: data };
    if (response.status === 401) return { tipo: "sin-sesion" };
    const texto = textos[response.status] ?? mensajeDeError(response.status, detalleDe(error));
    return { tipo: "error", texto, estado: response.status };
  } catch (e) {
    if (e instanceof ErrorSinToken) {
      sesionPerdida();
      return { tipo: "sin-sesion" };
    }
    return {
      tipo: "error",
      texto: esSinRed(e) ? mensajeDeError(null) : TEXTOS.errores.fallaDelServidor,
      estado: null,
    };
  }
}

/** TEXTOS.md, "Ingreso enviado dos veces" (409 del token de un solo uso). */
export const TEXTO_INGRESO_REPETIDO =
  "Este ingreso ya se registró. Revisa la lista antes de registrarlo otra vez.";

export function registrarIngreso(
  cliente: ClienteApi,
  entrada: Esquemas["IngresoEntrada"],
): Promise<Resultado<Esquemas["IngresoRegistrado"]>> {
  return enviar(
    () => cliente.POST("/api/ingresos", { params: { header: cabeceraCsrf() }, body: entrada }),
    { 409: TEXTO_INGRESO_REPETIDO },
  );
}

export function ajustarSaldo(
  cliente: ClienteApi,
  saldoRealCentavos: number,
): Promise<Resultado<Esquemas["Ajuste"]>> {
  return enviar(() =>
    cliente.POST("/api/ajustes", {
      params: { header: cabeceraCsrf() },
      body: { saldo_real_centavos: saldoRealCentavos },
    }),
  );
}

/**
 * Saldo inicial y fecha de inicio. La API lo rechaza con 400 y un `detalle`
 * ya escrito (fecha futura, o ya hay movimientos): se muestra tal cual.
 */
export function configurarSaldo(
  cliente: ClienteApi,
  entrada: Esquemas["ConfigurarSaldoEntrada"],
): Promise<Resultado<Esquemas["ConfiguracionSaldo"]>> {
  return enviar(() =>
    cliente.PUT("/api/saldo/configuracion", { params: { header: cabeceraCsrf() }, body: entrada }),
  );
}

/** 409 (ajuste, de Gmail o anterior al último ajuste) y 404 (ya no existe): el `detalle` de la API. */
export function borrarIngreso(
  cliente: ClienteApi,
  id: number,
): Promise<Resultado<Esquemas["IngresoBorrado"]>> {
  return enviar(() =>
    cliente.DELETE("/api/ingresos/{movimiento_id}", {
      params: { path: { movimiento_id: id }, header: cabeceraCsrf() },
    }),
  );
}
