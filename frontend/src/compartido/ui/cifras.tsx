/**
 * Piezas de Inicio que salen del prototipo (diseno/prototipo/componentes.css):
 * monto, subrayado doble, cuadro y chip de categoría. Solo clases de tokens.
 */
import type { LucideIcon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/compartido/ui/utils";
import { estiloCategoria, type ConEstilo } from "@/compartido/ui/categorias";
import { partirMonto } from "@/compartido/formatos/formato";

/** Un monto: letra de máquina de escribir, nunca partido en dos líneas. */
export function Monto({ className, ...props }: ComponentProps<"span">) {
  // El interlineado va fuera de cn(): tailwind-merge borra `leading-*` cuando
  // hay un tamaño `text-*` después, y los montos siempre van a 1,2.
  return (
    <span
      className={`${cn("font-montos tabular-nums whitespace-nowrap", className)} leading-(--interlineado-montos)`}
      {...props}
    />
  );
}

/** Subrayado doble bajo un total, como en contabilidad. */
export function SubrayadoDoble({ children }: { children: ReactNode }) {
  return <span className="border-b-[3px] border-double border-border pb-0.5">{children}</span>;
}

/** Nombre de una cifra ("Gastado en septiembre", "Saldo actual"). */
export function NombreCifra({ className, ...props }: ComponentProps<"p">) {
  return <p className={cn("text-muted-foreground text-sm font-medio", className)} {...props} />;
}

const TAMANO_MARCA = {
  normal: "size-8 [&>svg]:size-[18px]",
  /** Botones de "categorizar en un toque" (SISTEMA.md: chip de 28 px). */
  opcion: "size-7 [&>svg]:size-4",
  pequena: "size-6 [&>svg]:size-3.5",
} as const;

/**
 * Cuadro de color con el ícono de la categoría (decorativo: el nombre va
 * siempre escrito al lado). "Sin categorizar" es hueco y punteado.
 */
export function MarcaCategoria({
  categoria,
  tamano = "normal",
  className,
}: {
  /** Color e ícono de la API; `null` es "Sin categorizar". */
  categoria: ConEstilo | null;
  tamano?: keyof typeof TAMANO_MARCA;
  className?: string;
}) {
  const { color, icono: Icono, vacia } = estiloCategoria(categoria);
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-grid place-items-center flex-none rounded-chip",
        TAMANO_MARCA[tamano],
        color,
        vacia
          ? "bg-transparent text-muted-foreground border-[1.5px] border-dashed border-(--cat-sin-categorizar)"
          : "bg-(--c) text-(--cat-icono)",
        className,
      )}
    >
      <Icono />
    </span>
  );
}

/** Cuadro para lo que no tiene categoría y no es gasto (ingresos y ajustes). */
export function MarcaNeutra({ icono: Icono, className }: { icono: LucideIcon; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-grid place-items-center flex-none rounded-chip border border-input text-muted-foreground",
        TAMANO_MARCA.normal,
        className,
      )}
    >
      <Icono />
    </span>
  );
}

/** Chip pequeño: cuadro de 24 px y nombre (filas del gráfico, reglas). */
export function ChipCategoria({
  nombre,
  categoria,
  className,
}: {
  nombre: string;
  categoria: ConEstilo | null;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2 min-w-0", className)}>
      <MarcaCategoria categoria={categoria} tamano="pequena" />
      <span className="truncate">{nombre}</span>
    </span>
  );
}

/** Un texto con su monto en la letra de los montos ("transferencia de **$3.200**"). */
export function ConMonto({ texto, montoCentavos }: { texto: string; montoCentavos: number | null }) {
  const partes = partirMonto(texto, montoCentavos);
  if (partes.monto === null) return <>{texto}</>;
  return (
    <>
      {partes.antes}
      <Monto>{partes.monto}</Monto>
      {partes.despues}
    </>
  );
}
