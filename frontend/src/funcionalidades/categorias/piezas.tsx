/** Piezas internas reutilizadas por esta funcionalidad. */
import { TEXTOS } from "@/compartido/textos/textos";
import { Aviso } from "@/compartido/ui/libreta";
import { useVisibleTras } from "@/compartido/ui/pantalla";
import { CircleAlert } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

export function Cargando() {
  const visible = useVisibleTras();
  return visible ? (
    <p role="status" className="text-muted-foreground">
      {TEXTOS.app.cargando}
    </p>
  ) : null;
}


/**
 * Resultado de crear, guardar o borrar. Recibe el foco: el botón que abrió
 * el diálogo puede ya no existir (una categoría borrada).
 */
export function AvisoResultado({ texto }: { texto: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, [texto]);
  return (
    <div ref={ref} tabIndex={-1} className="focus:outline-none">
      <Aviso tipo="exito">{texto}</Aviso>
    </div>
  );
}


/** Cabecera de una hoja: título con la doble raya debajo. */
export function CabezaHoja({ id, titulo, children }: { id: string; titulo: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col gap-(--espacio-texto) mb-(--espacio-cabeza-hoja) pb-3 border-b-[3px] border-double border-regla">
      <h2 id={id}>{titulo}</h2>
      {children}
    </div>
  );
}


export function ErrorCampo({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <p id={id} className="flex items-start gap-2 text-destructive text-sm font-fuerte">
      <CircleAlert aria-hidden="true" className="size-5 flex-none" />
      <span>{children}</span>
    </p>
  );
}
