import { useCallback } from "react";
import { cabeceraCsrf, type ClienteApi, type Esquemas } from "@/compartido/http/cliente";
import { useAvisoDeshacer, type ResultadoDeshacer } from "@/compartido/deshacer/usar";
import { dato, FallaPeticion as FallaImportacion, textoFalla } from "@/compartido/http/dato";
export function useDeshacerConciliacion(
  cliente: ClienteApi,
  alRestaurar: () => Promise<void>,
) {
  const restaurador = useCallback(
    async (
      token: string,
    ): Promise<ResultadoDeshacer<Esquemas["DecisionDeshecha"]>> => {
      try {
        return {
          tipo: "ok",
          datos: await dato(
            cliente.POST("/api/conciliacion/deshacer", {
              params: { header: cabeceraCsrf() },
              body: { token },
            }),
          ),
        };
      } catch (error) {
        return error instanceof FallaImportacion && error.estado === 401
          ? { tipo: "sin-sesion" }
          : { tipo: "error", texto: textoFalla(error) };
      }
    },
    [cliente],
  );
  return useAvisoDeshacer(restaurador, alRestaurar);
}
