/**
 * Cuántos correos no reconocidos hay, para el contador de la navegación
 * (barra lateral y "Más"). Se pide una vez al entrar. Si falla, el contador
 * simplemente no aparece: no es información crítica y la pantalla de No
 * reconocidos (ítem 19) mostrará su propio error. Esa pantalla lo actualiza
 * con `useActualizarContadorNoReconocidos` cuando carga o reprocesa la lista.
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useSesion } from "@/funcionalidades/sesion/sesion";

const Contexto = createContext<number | null>(null);
const ContextoActualizar = createContext<(cantidad: number) => void>(() => {});

export function ProveedorContadorNoReconocidos({ children }: { children: ReactNode }) {
  const { cliente } = useSesion();
  const [cantidad, setCantidad] = useState<number | null>(null);

  useEffect(() => {
    let vigente = true;
    cliente
      .GET("/api/no-reconocidos")
      .then(({ data }) => {
        if (vigente && data) setCantidad(data.correos.length);
      })
      .catch(() => {
        /* sin red: sin contador */
      });
    return () => {
      vigente = false;
    };
  }, [cliente]);

  return (
    <ContextoActualizar.Provider value={setCantidad}>
      <Contexto.Provider value={cantidad}>{children}</Contexto.Provider>
    </ContextoActualizar.Provider>
  );
}

/** `null` mientras carga o si falló; el número si ya llegó. */
export function useContadorNoReconocidos(): number | null {
  return useContext(Contexto);
}

/** Para la pantalla de No reconocidos: deja el contador al día con la lista. */
export function useActualizarContadorNoReconocidos(): (cantidad: number) => void {
  return useContext(ContextoActualizar);
}
