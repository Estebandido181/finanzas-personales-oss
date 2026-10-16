/** Piezas internas reutilizadas por esta funcionalidad. */
import { TEXTOS } from "@/compartido/textos/textos";
import { Aviso } from "@/compartido/ui/libreta";
import { useVisibleTras } from "@/compartido/ui/pantalla";
import { type ClaseMonto } from "@/funcionalidades/saldo/datos";
import { CircleAlert } from "lucide-react";
import { type ReactNode } from "react";

export function Cargando() {
  const visible = useVisibleTras();
  return visible ? (
    <p role="status" className="text-muted-foreground">
      {TEXTOS.app.cargando}
    </p>
  ) : null;
}


export const COLOR_MONTO: Record<ClaseMonto, string | undefined> = {
  suma: "text-monto-positivo",
  resta: "text-monto-negativo",
  neutro: undefined,
};


/** Cabecera de una hoja: título con la doble raya debajo (SISTEMA.md, "Hoja"). */
export function CabezaHoja({
  id,
  titulo,
  children,
}: {
  id: string;
  titulo: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-(--espacio-texto) mb-(--espacio-cabeza-hoja) pb-3 border-b-[3px] border-double border-regla">
      <h2 id={id}>{titulo}</h2>
      {children}
    </div>
  );
}


export function FilaCifra({ nombre, children }: { nombre: string; children: ReactNode }) {
  return (
    <div className="flex justify-between items-baseline gap-3">
      <span>{nombre}</span>
      {children}
    </div>
  );
}


export function Campo({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-(--espacio-texto)">{children}</div>;
}


export function ErrorCampo({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <p id={id} className="flex items-start gap-2 text-destructive text-sm font-fuerte">
      <CircleAlert aria-hidden="true" className="size-5 flex-none" />
      <span>{children}</span>
    </p>
  );
}


/** El resultado de registrar o ajustar, junto al botón (o por qué no se pudo). */
export function Resultado({ mensaje }: { mensaje: Mensaje }) {
  return mensaje ? <Aviso tipo={mensaje.tipo}>{mensaje.texto}</Aviso> : null;
}

export type Mensaje = { tipo: "exito" | "info" | "error"; texto: string } | null;
