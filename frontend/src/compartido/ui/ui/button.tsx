/**
 * Botón de shadcn/ui adaptado al sistema "libreta de cuentas" (SISTEMA.md,
 * "Componentes base"): alto mínimo 44 px, radio 4 px, canto suave y sombra
 * de papel difusa; al presionar se hunde 1 px en el papel.
 *
 * Variantes: default = principal (tinta sepia en claro, mostaza en oscuro),
 * outline = secundario (relleno tono sobre tono), destructive = borrar
 * (tinta roja), ghost = quieto (acciones de fila, sin borde ni sombra). Sin variante `link`: los enlaces sueltos son enlaces.
 */
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/compartido/ui/utils";

export const variantesBoton = cva(
  [
    "inline-flex items-center justify-center gap-2 min-h-(--tactil-min) px-4",
    "font-fuerte leading-[1.2] no-underline cursor-pointer select-none",
    "border border-borde-suave rounded-hoja shadow-boton",
    "transition-[translate,box-shadow] duration-(--duracion-corta) ease-libreta motion-reduce:transition-none",
    "active:translate-y-px active:shadow-none",
    "disabled:cursor-not-allowed disabled:opacity-70 disabled:active:translate-0 disabled:active:shadow-boton",
  ],
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground border-transparent hover:underline underline-offset-3",
        outline: "bg-secondary text-foreground hover:bg-accent",
        destructive:
          "bg-destructive text-destructive-foreground border-transparent hover:underline underline-offset-3",
        ghost:
          "bg-transparent border-transparent shadow-none font-medio px-3 hover:bg-accent active:translate-0",
      },
      size: {
        default: "",
        icono: "w-(--tactil-min) px-0",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface PropsBoton extends ComponentProps<"button">, VariantProps<typeof variantesBoton> {
  /** Pinta el hijo (por ejemplo un enlace) con el aspecto de botón. */
  asChild?: boolean;
}

export function Button({ className, variant, size, asChild = false, ...props }: PropsBoton) {
  const Componente = asChild ? Slot : "button";
  return (
    <Componente
      data-slot="button"
      className={cn(variantesBoton({ variant, size }), className)}
      {...props}
    />
  );
}
