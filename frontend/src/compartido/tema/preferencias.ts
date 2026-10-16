/**
 * Apariencia (Sistema, Claro, Oscuro): se recuerda en el dispositivo y se
 * aplica con data-tema en <html>, como en el prototipo (SISTEMA.md, "Modo
 * claro y oscuro"). public/tema-inicial.js la aplica antes de pintar; este
 * módulo la cambia desde la app.
 *
 * localStorage solo guarda esta preferencia (y la vista del gráfico, ítem 13):
 * no son datos financieros. "Sistema" es el valor por defecto y no se guarda.
 */
import { useCallback, useSyncExternalStore } from "react";

export type Tema = "sistema" | "claro" | "oscuro";
export const TEMAS: readonly Tema[] = ["sistema", "claro", "oscuro"];
export const CLAVE_TEMA = "finanzas-tema";
const ATRIBUTO = "data-tema";

function leerAlmacen(): string | null {
  try {
    return localStorage.getItem(CLAVE_TEMA);
  } catch {
    return null;
  }
}

export function leerTema(): Tema {
  const guardado = leerAlmacen();
  return guardado === "claro" || guardado === "oscuro" ? guardado : "sistema";
}

export function aplicarTema(tema: Tema, raiz: HTMLElement = document.documentElement): void {
  if (tema === "sistema") raiz.removeAttribute(ATRIBUTO);
  else raiz.setAttribute(ATRIBUTO, tema);
}

const oyentes = new Set<() => void>();

export function elegirTema(tema: Tema): void {
  try {
    if (tema === "sistema") localStorage.removeItem(CLAVE_TEMA);
    else localStorage.setItem(CLAVE_TEMA, tema);
  } catch {
    /* sin almacenamiento: la elección dura hasta recargar */
  }
  aplicarTema(tema);
  temaEnMemoria = tema;
  oyentes.forEach((avisar) => avisar());
}

let temaEnMemoria: Tema | null = null;

function suscribir(avisar: () => void) {
  oyentes.add(avisar);
  // Otra pestaña cambió la apariencia: se sigue aquí también.
  const alCambiarAlmacen = (evento: StorageEvent) => {
    if (evento.key === CLAVE_TEMA) {
      temaEnMemoria = leerTema();
      aplicarTema(temaEnMemoria);
      avisar();
    }
  };
  window.addEventListener("storage", alCambiarAlmacen);
  return () => {
    oyentes.delete(avisar);
    window.removeEventListener("storage", alCambiarAlmacen);
  };
}

function instantanea(): Tema {
  if (temaEnMemoria === null) temaEnMemoria = leerTema();
  return temaEnMemoria;
}

/** Para las pruebas: olvida lo leído. */
export function reiniciarTemaEnMemoria(): void {
  temaEnMemoria = null;
}

export function useTema(): [Tema, (tema: Tema) => void] {
  const tema = useSyncExternalStore(suscribir, instantanea, () => "sistema" as Tema);
  const cambiar = useCallback((nuevo: Tema) => elegirTema(nuevo), []);
  return [tema, cambiar];
}
