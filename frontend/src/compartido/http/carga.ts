import { useCallback, useEffect, useRef, useState } from "react";
import { textoFalla } from "@/compartido/http/dato";

export type Carga<T> =
  | { tipo: "cargando" }
  | { tipo: "listo"; datos: T }
  | { tipo: "error"; mensaje: string };
export function useCarga<T>(obtener: () => Promise<T>) {
  const [carga, setCarga] = useState<Carga<T>>({ tipo: "cargando" });
  const numero = useRef(0);
  const recargar = useCallback(async () => {
    const turno = ++numero.current;
    try {
      const datos = await obtener();
      if (turno === numero.current) setCarga({ tipo: "listo", datos });
    } catch (error) {
      if (turno === numero.current)
        setCarga({ tipo: "error", mensaje: textoFalla(error) });
    }
  }, [obtener]);
  useEffect(() => {
    setCarga({ tipo: "cargando" });
    void recargar();
    return () => {
      numero.current++;
    };
  }, [recargar]);
  return { carga, recargar };
}
