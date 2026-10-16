import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// tailwind-merge debe conocer los nombres propios del tema (estilos.css) para
// saber que `text-sm` y `text-muted-foreground` no chocan, o que `shadow-boton`
// y `shadow-none` sí.
const unir = extendTailwindMerge({
  extend: {
    theme: {
      text: ["sm", "base", "lg", "xl", "2xl", "3xl", "monto-grande"],
      font: ["titulos", "texto", "montos"],
      "font-weight": ["normal", "medio", "fuerte"],
      radius: ["hoja", "chip", "barra"],
      shadow: ["hoja", "boton", "campo", "barra"],
      breakpoint: ["computador"],
      ease: ["libreta"],
    },
  },
});

/** Une clases de Tailwind resolviendo conflictos (la `cn` de shadcn/ui). */
export function cn(...entradas: ClassValue[]): string {
  return unir(clsx(entradas));
}
