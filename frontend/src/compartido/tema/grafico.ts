/**
 * Cómo ver "¿En qué se fue?": barras (por defecto) o dona (SISTEMA.md,
 * "Gráfico"). Igual que la apariencia: se recuerda en el dispositivo
 * (localStorage, clave `finanzas-grafico`) y se aplica con `data-grafico` en
 * <html>; public/tema-inicial.js la aplica antes de pintar, así la vista no
 * "salta" al cargar. Es una preferencia, no un dato financiero. "Barras" es el
 * valor por defecto y no se guarda.
 */
import { useCallback, useSyncExternalStore } from "react";

export type VistaGrafico = "barras" | "dona";
export const CLAVE_GRAFICO = "finanzas-grafico";
const ATRIBUTO = "data-grafico";

export function leerVistaGrafico(): VistaGrafico {
  try {
    return localStorage.getItem(CLAVE_GRAFICO) === "dona" ? "dona" : "barras";
  } catch {
    return "barras";
  }
}

export function aplicarVistaGrafico(
  vista: VistaGrafico,
  raiz: HTMLElement = document.documentElement,
): void {
  if (vista === "dona") raiz.setAttribute(ATRIBUTO, "dona");
  else raiz.removeAttribute(ATRIBUTO);
}

const oyentes = new Set<() => void>();
let enMemoria: VistaGrafico | null = null;

export function elegirVistaGrafico(vista: VistaGrafico): void {
  try {
    if (vista === "dona") localStorage.setItem(CLAVE_GRAFICO, "dona");
    else localStorage.removeItem(CLAVE_GRAFICO);
  } catch {
    /* sin almacenamiento: la elección dura hasta recargar */
  }
  aplicarVistaGrafico(vista);
  enMemoria = vista;
  oyentes.forEach((avisar) => avisar());
}

function suscribir(avisar: () => void) {
  oyentes.add(avisar);
  const alCambiarAlmacen = (evento: StorageEvent) => {
    if (evento.key === CLAVE_GRAFICO) {
      enMemoria = leerVistaGrafico();
      aplicarVistaGrafico(enMemoria);
      avisar();
    }
  };
  window.addEventListener("storage", alCambiarAlmacen);
  return () => {
    oyentes.delete(avisar);
    window.removeEventListener("storage", alCambiarAlmacen);
  };
}

function instantanea(): VistaGrafico {
  if (enMemoria === null) enMemoria = leerVistaGrafico();
  return enMemoria;
}

/** Para las pruebas: olvida lo leído. */
export function reiniciarVistaGraficoEnMemoria(): void {
  enMemoria = null;
}

export function useVistaGrafico(): [VistaGrafico, (vista: VistaGrafico) => void] {
  const vista = useSyncExternalStore(suscribir, instantanea, () => "barras" as VistaGrafico);
  const cambiar = useCallback((nueva: VistaGrafico) => elegirVistaGrafico(nueva), []);
  return [vista, cambiar];
}
