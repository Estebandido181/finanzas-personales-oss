/**
 * Deshacer en vez de confirmar (ítem 38). Un borrado que se puede deshacer se
 * hace al tocar; la API responde con `deshacer: {token, segundos}` y la pantalla
 * ofrece «Deshacer» durante esos segundos, ni uno más (el servidor los manda).
 *
 * Hook reutilizable: cada pantalla lo usa con su propio texto y su propio
 * «recargar». El `token` vive solo en este hook (memoria): nunca va a
 * localStorage ni a ningún otro sitio, y se pierde al salir de la pantalla.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { cabeceraCsrf, ErrorSinToken, sesionPerdida, type ClienteApi, type Esquemas } from "@/compartido/http/cliente";
import { detalleDe, mensajeDeError } from "@/compartido/http/errores";
import { esSinRed } from "@/compartido/http/respuesta";
import { TEXTOS } from "@/compartido/textos/textos";

export type Deshacer = Esquemas["Deshacer"];
export type Deshecho = Esquemas["Deshecho"];

/** Lo que el aviso muestra; `null` es que no hay nada que mostrar. */
export type EstadoDeshacer =
  | { fase: "oferta"; texto: string }
  | { fase: "deshaciendo"; texto: string }
  | { fase: "hecho"; texto: string }
  | { fase: "error"; texto: string };

export type ResultadoDeshacer<T = Deshecho> =
  | { tipo: "ok"; datos: T }
  | { tipo: "error"; texto: string }
  /** La sesión se perdió: la app ya vuelve a "Entrar". */
  | { tipo: "sin-sesion" };

/**
 * POST /api/deshacer. 410: venció o ya se usó; 409: ya no se puede (algo
 * cambió). En los dos la API manda el motivo en `detalle`, escrito para el
 * dueño; si no viniera, se usa un texto propio.
 */
export async function restaurar(cliente: ClienteApi, token: string): Promise<ResultadoDeshacer> {
  try {
    const { data, error, response } = await cliente.POST("/api/deshacer", {
      params: { header: cabeceraCsrf() },
      body: { token },
    });
    if (data) return { tipo: "ok", datos: data };
    if (response.status === 401) return { tipo: "sin-sesion" };
    const detalle = detalleDe(error);
    if (response.status === 410) return { tipo: "error", texto: detalle ?? TEXTOS.deshacer.yaNoSePuede };
    if (response.status === 409) return { tipo: "error", texto: detalle ?? TEXTOS.deshacer.algoCambio };
    return { tipo: "error", texto: mensajeDeError(response.status, detalle) };
  } catch (e) {
    if (e instanceof ErrorSinToken) {
      sesionPerdida();
      return { tipo: "sin-sesion" };
    }
    return { tipo: "error", texto: esSinRed(e) ? mensajeDeError(null) : TEXTOS.errores.fallaDelServidor };
  }
}

/** Marca del aviso en el DOM, para no perder el foco cuando desaparece. */
export const MARCA_AVISO_DESHACER = "data-aviso-deshacer";

/** Si el foco estaba en el aviso que se va, pasa al título de la pantalla (nunca al body). */
function rescatarFoco(): void {
  const activo = document.activeElement;
  if (activo?.closest(`[${MARCA_AVISO_DESHACER}]`)) {
    document.querySelector<HTMLElement>("h1")?.focus();
  }
}

export interface OpcionesOfrecer<T = Deshecho> {
  /** Lo que respondió la API al borrar. */
  deshacer: Deshacer;
  /** "Ingreso borrado. El saldo bajó $150.000." */
  texto: string;
  /** Lo que se dice al restaurar, con lo que respondió la API. */
  restaurado: (resultado: T) => string;
}

/**
 * `alRestaurar` vuelve a leer la pantalla. Solo hay un aviso a la vez: ofrecer
 * otro borrado reemplaza al anterior (su token ya no se ofrece).
 */
export function useDeshacer(cliente: ClienteApi, alRestaurar?: (resultado?: Deshecho) => void | Promise<void>) {
  const restaurador = useCallback((token: string) => restaurar(cliente, token), [cliente]);
  return useAvisoDeshacer(restaurador, alRestaurar);
}

/** Temporizador/foco compartidos por borrados38 y decisiones bancarias30.
 * El resultado conserva el tipo real de su endpoint OpenAPI. */
export function useAvisoDeshacer<T>(restaurador: (token: string) => Promise<ResultadoDeshacer<T>>, alRestaurar?: (resultado?: T) => void | Promise<void>) {
  const [estado, setEstado] = useState<EstadoDeshacer | null>(null);
  const token = useRef<string | null>(null);
  const textoRestaurado = useRef<((r: T) => string) | null>(null);
  const reloj = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Cuánto falta y desde cuándo corre (para pausar la cuenta y reanudarla).
  const restante = useRef(0);
  const desde = useRef(0);
  const montado = useRef(true);
  const alRestaurarActual = useRef(alRestaurar);
  alRestaurarActual.current = alRestaurar;

  const pararReloj = () => {
    if (reloj.current !== null) clearTimeout(reloj.current);
    reloj.current = null;
  };

  const programar = () => {
    desde.current = Date.now();
    reloj.current = setTimeout(() => {
      reloj.current = null;
      token.current = null;
      rescatarFoco();
      // Si ya se está deshaciendo, la respuesta decide qué se ve.
      setEstado((antes) => (antes?.fase === "oferta" ? null : antes));
    }, restante.current);
  };

  useEffect(() => {
    montado.current = true;
    return () => {
      montado.current = false;
      pararReloj();
      token.current = null;
    };
  }, []);

  const limpiar = useCallback(() => {
    pararReloj();
    token.current = null;
    textoRestaurado.current = null;
    setEstado(null);
  }, []);

  const ofrecer = useCallback(({ deshacer, texto, restaurado }: OpcionesOfrecer<T>) => {
    pararReloj();
    token.current = deshacer.token;
    textoRestaurado.current = restaurado;
    setEstado({ fase: "oferta", texto });
    restante.current = Math.max(0, deshacer.segundos) * 1000;
    programar();
  }, []);

  /** Pausa la cuenta (foco o cursor sobre el aviso). */
  const pausar = useCallback(() => {
    if (reloj.current === null) return;
    restante.current = Math.max(0, restante.current - (Date.now() - desde.current));
    pararReloj();
  }, []);

  /** Reanuda la cuenta con lo que faltaba. */
  const reanudar = useCallback(() => {
    if (reloj.current !== null || token.current === null) return;
    programar();
  }, []);

  /** Un error que no viene de deshacer (por ejemplo, el 409 de borrar): se muestra en el mismo lugar. */
  const mostrarError = useCallback((texto: string) => {
    pararReloj();
    token.current = null;
    setEstado({ fase: "error", texto });
  }, []);

  const deshacer = useCallback(async () => {
    const actual = token.current;
    if (actual === null) return;
    pararReloj();
    token.current = null;
    setEstado((antes) => (antes ? { fase: "deshaciendo", texto: antes.texto } : antes));
    const r = await restaurador(actual);
    if (!montado.current || r.tipo === "sin-sesion") return;
    if (r.tipo === "error") {
      setEstado({ fase: "error", texto: r.texto });
      // Otra pestaña pudo restaurarlo o cambiarlo: la pantalla muestra lo que hay en el servidor (D44).
      await alRestaurarActual.current?.();
      return;
    }
    setEstado({ fase: "hecho", texto: textoRestaurado.current?.(r.datos) ?? "" });
    await alRestaurarActual.current?.(r.datos);
  }, [restaurador]);

  return { estado, ofrecer, mostrarError, deshacer, limpiar, pausar, reanudar };
}
