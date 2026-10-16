/**
 * Cómo Inicio habla con la API: leer el mes (reporte, movimientos y estado
 * de la sincronización, en paralelo) y «Sincronizar ahora».
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { ClienteApi } from "@/compartido/http/cliente";
import { mensajeDeError } from "@/compartido/http/errores";
import { FalloApi, exigir, esSinRed } from "@/compartido/http/respuesta";
import { TEXTOS } from "@/compartido/textos/textos";
import { type Movimiento, type Reporte } from "@/funcionalidades/inicio/datos";
import { type EstadoSincronizacionApi } from "@/funcionalidades/sincronizacion/estado";

export interface DatosInicio {
  reporte: Reporte;
  movimientos: Movimiento[];
  sincronizacion: EstadoSincronizacionApi;
}

export type Carga =
  | { tipo: "cargando" }
  | { tipo: "error"; sinRed: boolean; mensaje: string }
  | { tipo: "listo"; datos: DatosInicio };

/** Lee todo lo de Inicio. `mes` es "aaaa-mm", o `null` para el mes actual. */
export async function leerInicio(cliente: ClienteApi, mes: string | null): Promise<DatosInicio> {
  const consulta = mes ? { params: { query: { mes } } } : {};
  const [reporte, movimientos, sincronizacion] = await Promise.all([
    exigir(cliente.GET("/api/reporte", consulta)),
    exigir(cliente.GET("/api/movimientos", consulta)),
    exigir(cliente.GET("/api/sincronizacion")),
  ]);
  return { reporte, movimientos: movimientos.movimientos, sincronizacion };
}

function cargaConError(error: unknown): Carga {
  if (error instanceof FalloApi) {
    return { tipo: "error", sinRed: false, mensaje: mensajeDeError(error.estado, error.detalle) };
  }
  if (esSinRed(error)) return { tipo: "error", sinRed: true, mensaje: mensajeDeError(null) };
  return { tipo: "error", sinRed: false, mensaje: TEXTOS.errores.fallaDelServidor };
}

/**
 * Los datos del mes. `recargar(true)` vuelve a pedirlos sin pasar por
 * "Cargando…" (tras sincronizar: la pantalla no parpadea).
 */
export function useDatosInicio(cliente: ClienteApi, mes: string | null) {
  const [carga, setCarga] = useState<Carga>({ tipo: "cargando" });
  const pedido = useRef(0);

  const recargar = useCallback(
    async (silencioso = false) => {
      const este = ++pedido.current;
      if (!silencioso) setCarga({ tipo: "cargando" });
      let nueva: Carga;
      try {
        nueva = { tipo: "listo", datos: await leerInicio(cliente, mes) };
      } catch (error) {
        nueva = cargaConError(error);
      }
      // Si mientras tanto se pidió otro mes, esta respuesta ya no sirve.
      if (este === pedido.current) setCarga(nueva);
    },
    [cliente, mes],
  );

  useEffect(() => {
    void recargar();
    return () => {
      pedido.current++;
    };
  }, [recargar]);

  return { carga, recargar };
}
