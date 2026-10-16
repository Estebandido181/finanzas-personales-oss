import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation, useSearch } from "wouter";
import { TEXTOS } from "@/compartido/textos/textos";

// La primera pantalla que se muestra no mueve el foco (el navegador lo deja
// al principio de la página). Las siguientes sí: al cambiar de dirección
// (sección o mes), el lector de pantalla anuncia el título nuevo y el teclado
// sigue desde ahí.
//
// Una misma pantalla puede montar su encabezado dos veces (Inicio: primero el
// de "cargando" y luego el del reporte). Eso no es cambiar de pantalla: el
// foco solo se vuelve a poner en el título si estaba en el anterior (que
// desapareció). Si no, se le robaría el foco a quien ya empezó a tabular (por
// ejemplo, desde «Saltar al contenido» justo después de entrar).
let ultimaPantalla: string | null = null;
let tituloEnfocado: HTMLElement | null = null;

/** Para las pruebas. */
export function reiniciarFocoDePantallas(): void {
  ultimaPantalla = null;
  tituloEnfocado = null;
}

function focoPerdidoConElTituloAnterior(): boolean {
  const activo = document.activeElement;
  return (
    tituloEnfocado !== null &&
    !tituloEnfocado.isConnected &&
    (activo === null || activo === document.body)
  );
}

/** Tras cuánto se muestra "Cargando…": si responde antes, no hay parpadeo. */
export const ESPERA_CARGANDO_MS = 300;

/** `true` pasados `ms` milisegundos desde que se montó (para "Cargando…"). */
export function useVisibleTras(ms: number = ESPERA_CARGANDO_MS): boolean {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const reloj = setTimeout(() => setVisible(true), ms);
    return () => clearTimeout(reloj);
  }, [ms]);
  return visible;
}

/**
 * Encabezado de pantalla: el h1 y el título de la pestaña del navegador.
 * `antes` va encima del h1 (el selector de mes de Inicio) y `debajo`, bajo
 * él (el de Movimientos); `children`, a la derecha (o debajo, en el celular).
 *
 * `pantalla` dice qué cuenta como "otra pantalla" para mover el foco al
 * título; por defecto, la dirección completa. Movimientos pasa solo la ruta y
 * el mes: cambiar un filtro no es cambiar de pantalla (el foco se queda en
 * el filtro).
 */
export function Encabezado({
  titulo,
  antes,
  debajo,
  pantalla: pantallaPropia,
  children,
}: {
  titulo: string;
  antes?: ReactNode;
  debajo?: ReactNode;
  pantalla?: string;
  children?: ReactNode;
}) {
  const h1 = useRef<HTMLHeadingElement>(null);
  const [ruta] = useLocation();
  const busqueda = useSearch();
  const pantalla = pantallaPropia ?? `${ruta}?${busqueda}`;
  useEffect(() => {
    document.title = `${titulo} · ${TEXTOS.app.nombre}`;
  }, [titulo]);
  useEffect(() => {
    const otraPantalla = ultimaPantalla !== null && ultimaPantalla !== pantalla;
    if ((otraPantalla || focoPerdidoConElTituloAnterior()) && h1.current) {
      h1.current.focus();
      tituloEnfocado = h1.current;
    }
    ultimaPantalla = pantalla;
  }, [pantalla]);
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex flex-col gap-(--espacio-texto)">
        {antes}
        <h1 ref={h1} tabIndex={-1} className="focus:outline-none">
          {titulo}
        </h1>
        {debajo}
      </div>
      {children}
    </header>
  );
}

/** Pila de bloques de una pantalla: entre bloques, más aire que dentro. */
export function Pila({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-(--espacio-bloques)">{children}</div>;
}
