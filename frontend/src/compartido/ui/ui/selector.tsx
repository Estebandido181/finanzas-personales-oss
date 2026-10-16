/**
 * Selector (SISTEMA.md, "Selector"): el `<select>` nativo con el aspecto de un
 * campo (alto 44 px, borde `input`, fondo de hoja, sombra interior) y una
 * flecha de tinta. Nativo y no el `Select` de Radix: en el celular abre la
 * rueda del sistema, y el de Radix inserta un `<style>` que la CSP bloquea
 * (ver frontend/README.md, "CSP estricta").
 */
import { ChevronDown } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "@/compartido/ui/utils";

export function Selector({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <span className={cn("relative block", className)}>
      <select
        data-slot="selector"
        className={cn(
          "block w-full min-h-(--tactil-min) pl-3 pr-10 py-2 appearance-none cursor-pointer",
          "bg-card text-foreground border border-input rounded-hoja shadow-campo",
          "focus-visible:outline-offset-0 focus-visible:border-ring",
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 size-5"
      />
    </span>
  );
}
