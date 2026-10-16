/**
 * Diálogo (SISTEMA.md, "Diálogo"): hoja inferior en el celular y ventana
 * centrada en el computador, con el velo `velo` detrás.
 *
 * Es el `<dialog>` nativo con `showModal()`, no el `Dialog` de Radix (ver
 * frontend/README.md, "CSP estricta"): Radix inserta un `<style>` al abrirse
 * y la CSP lo bloquea. El nativo ya trae el foco atrapado, Escape y el fondo
 * inerte, sin estilos inyectados. Se muestra mientras está montado: quien lo
 * usa decide cuándo montarlo. Al cerrarse, el foco vuelve a donde estaba.
 */
import { useEffect, useId, useRef, type ReactNode } from "react";
import { cn } from "@/compartido/ui/utils";

export function Dialogo({
  titulo,
  descripcion,
  alCerrar,
  acciones,
  children,
  amplio = false,
}: {
  titulo: string;
  /** El texto que explica la consecuencia (se une con `aria-describedby`). */
  descripcion?: ReactNode;
  /** Escape o «Cancelar». */
  alCerrar: () => void;
  /** Los botones, en el orden del prototipo: «Cancelar» primero. */
  acciones: ReactNode;
  children?: ReactNode;
  /** Más ancho en el computador (formularios con rejillas). */
  amplio?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const idTitulo = useId();
  const idDescripcion = useId();
  const cerrar = useRef(alCerrar);
  cerrar.current = alCerrar;

  useEffect(() => {
    const dialogo = ref.current;
    if (!dialogo) return;
    const antes = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    // jsdom (pruebas de unidad) no tiene showModal: ahí basta con `open`.
    if (typeof dialogo.showModal === "function") {
      if (!dialogo.open) dialogo.showModal();
    } else {
      dialogo.setAttribute("open", "");
    }
    return () => {
      if (typeof dialogo.close === "function" && dialogo.open) dialogo.close();
      if (antes?.isConnected) antes.focus();
    };
  }, []);

  return (
    <dialog
      ref={ref}
      aria-labelledby={idTitulo}
      aria-describedby={descripcion ? idDescripcion : undefined}
      // Escape: lo cierra quien lo montó (así el estado de React manda).
      onCancel={(e) => {
        e.preventDefault();
        cerrar.current();
      }}
      className={cn(
        "papel bg-popover text-popover-foreground border border-borde-hoja shadow-hoja",
        "fixed m-0 mt-auto w-full max-w-none max-h-[100dvh] overflow-y-auto rounded-t-hoja",
        "px-5 pt-6 pb-[calc(var(--espacio-6)+env(safe-area-inset-bottom))]",
        "backdrop:bg-velo",
        "computador:m-auto computador:rounded-hoja computador:max-h-[calc(100dvh-4rem)] computador:p-6",
        amplio ? "computador:w-[min(36rem,calc(100%-2rem))]" : "computador:w-[min(30rem,calc(100%-2rem))]",
      )}
    >
      <div className="flex flex-col gap-4">
        <h2 id={idTitulo}>{titulo}</h2>
        {descripcion ? <div id={idDescripcion}>{descripcion}</div> : null}
        {children}
        <div className="flex flex-col-reverse gap-3 mt-2 computador:flex-row computador:justify-end computador:flex-wrap">
          {acciones}
        </div>
      </div>
    </dialog>
  );
}
