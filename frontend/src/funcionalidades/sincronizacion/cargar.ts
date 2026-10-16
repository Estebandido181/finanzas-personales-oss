/**
 * Cómo "Correos no reconocidos" habla con la API: leer la lista y «Volver a
 * procesar todos». Los errores usan los mismos textos que «Sincronizar ahora»
 * de Inicio (mensajeDeError, 409 = sincronización en curso).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { cabeceraCsrf, ErrorSinToken, sesionPerdida, type ClienteApi } from "@/compartido/http/cliente";
import { detalleDe, mensajeDeError } from "@/compartido/http/errores";
import { esSinRed } from "@/compartido/http/respuesta";
import { TEXTOS } from "@/compartido/textos/textos";
import { ordenarPorFecha, type CorreoNoReconocido, type ResultadoReproceso } from "@/funcionalidades/sincronizacion/datos";

export type Carga =
  | { tipo: "cargando" }
  | { tipo: "error"; sinRed: boolean; mensaje: string }
  | { tipo: "listo"; correos: CorreoNoReconocido[] };

/** La lista, del más reciente al más antiguo. `recargar(true)` no pasa por "Cargando…". */
export function useNoReconocidos(cliente: ClienteApi, alCambiar: (cantidad: number) => void) {
  const [carga, setCarga] = useState<Carga>({ tipo: "cargando" });
  const pedido = useRef(0);

  const recargar = useCallback(
    async (silencioso = false) => {
      const este = ++pedido.current;
      if (!silencioso) setCarga({ tipo: "cargando" });
      let nueva: Carga;
      try {
        const { data, error, response } = await cliente.GET("/api/no-reconocidos");
        nueva = data
          ? { tipo: "listo", correos: ordenarPorFecha(data.correos) }
          : { tipo: "error", sinRed: false, mensaje: mensajeDeError(response.status, detalleDe(error)) };
      } catch (e) {
        nueva = esSinRed(e)
          ? { tipo: "error", sinRed: true, mensaje: mensajeDeError(null) }
          : { tipo: "error", sinRed: false, mensaje: TEXTOS.errores.fallaDelServidor };
      }
      if (este !== pedido.current) return;
      setCarga(nueva);
      if (nueva.tipo === "listo") alCambiar(nueva.correos.length);
    },
    [cliente, alCambiar],
  );

  useEffect(() => {
    void recargar();
    return () => {
      pedido.current++;
    };
  }, [recargar]);

  return { carga, recargar };
}

export type SalidaReproceso =
  | { tipo: "resultado"; resultado: ResultadoReproceso }
  | { tipo: "error"; texto: string }
  | null;

/**
 * «Volver a procesar todos». Si el reproceso termina (ok, con errores o
 * fallida) se recarga la lista, porque pudo cambiar algo antes del corte.
 * Un 409 (sincronización en curso) o cualquier otro error no la toca.
 */
export function useReprocesar(cliente: ClienteApi, alTerminar: () => Promise<void>) {
  const [enCurso, setEnCurso] = useState(false);
  const [salida, setSalida] = useState<SalidaReproceso>(null);
  const montado = useRef(true);
  useEffect(() => {
    montado.current = true;
    return () => {
      montado.current = false;
    };
  }, []);

  const reprocesar = useCallback(async () => {
    setEnCurso(true);
    setSalida(null);
    let nueva: SalidaReproceso = null;
    let recargar = false;
    try {
      const { data, error, response } = await cliente.POST("/api/no-reconocidos/reprocesar", {
        params: { header: cabeceraCsrf() },
        // Sin cuerpo, pero la API exige JSON en todo lo que cambia datos (415 si no).
        headers: { "Content-Type": "application/json" },
      });
      if (data) {
        recargar = true;
        nueva = { tipo: "resultado", resultado: data };
      } else if (response.status === 409) {
        nueva = { tipo: "error", texto: TEXTOS.inicio.sincronizacionEnCurso };
      } else if (response.status !== 401) {
        nueva = { tipo: "error", texto: mensajeDeError(response.status, detalleDe(error)) };
      }
    } catch (e) {
      if (e instanceof ErrorSinToken) {
        sesionPerdida();
        return;
      }
      nueva = {
        tipo: "error",
        texto: esSinRed(e) ? mensajeDeError(null) : TEXTOS.errores.fallaDelServidor,
      };
    }
    if (recargar) await alTerminar();
    if (!montado.current) return;
    setSalida(nueva);
    setEnCurso(false);
  }, [cliente, alTerminar]);

  return { enCurso, salida, reprocesar };
}
