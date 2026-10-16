/**
 * Campo de shadcn/ui adaptado (SISTEMA.md, "Campo"): alto 44 px, borde
 * `input` (se conserva: ≥ 3:1), fondo de hoja, sombra interior leve (hundido
 * en el papel) y foco con borde y anillo `ring`. Con error:
 * borde de 2 px en tinta roja (`aria-invalid`).
 */
import type { ComponentProps } from "react";
import { cn } from "@/compartido/ui/utils";

export function Input({ className, type, ...props }: ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "block w-full min-h-(--tactil-min) px-3 py-2",
        "bg-card text-foreground border border-input rounded-hoja shadow-campo",
        "placeholder:text-muted-foreground placeholder:opacity-100",
        "focus-visible:outline-offset-0 focus-visible:border-ring",
        "aria-invalid:border-2 aria-invalid:border-destructive",
        className,
      )}
      {...props}
    />
  );
}

/** Etiqueta siempre visible arriba del campo (nunca solo placeholder). */
export function Etiqueta({ className, ...props }: ComponentProps<"label">) {
  return <label className={cn("block font-fuerte text-base", className)} {...props} />;
}
