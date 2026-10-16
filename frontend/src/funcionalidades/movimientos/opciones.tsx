/**
 * Categorizar en un toque: un botón por categoría (2 columnas en el celular,
 * 5 en el computador). La usan Movimientos (una fila) y el grupo de
 * movimientos iguales (ítem 38; el ítem 30 la reutiliza para lo importado).
 */
import { useId } from "react";
import { Button } from "@/compartido/ui/ui/button";
import { MarcaCategoria } from "@/compartido/ui/cifras";
import { cn } from "@/compartido/ui/utils";
import { TEXTOS } from "@/compartido/textos/textos";
import type { Categoria } from "@/funcionalidades/movimientos/datos";

const T = TEXTOS.movimientos;

export function Opciones({
  categorias,
  actual,
  ocupada,
  alElegir,
  alCancelar,
  pregunta = T.elegir,
}: {
  categorias: Categoria[];
  /** Al cambiar, la categoría que tiene ahora: va marcada (`aria-pressed`). */
  actual: number | null;
  ocupada: boolean;
  alElegir: (categoria: Categoria) => void;
  alCancelar?: () => void;
  /** Lo que se pregunta sobre los botones. */
  pregunta?: string;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-2">
      <p id={id} className="font-fuerte">
        {pregunta}
      </p>
      <div role="group" aria-labelledby={id} className="grid grid-cols-2 computador:grid-cols-5 gap-2">
        {categorias.map((c) => (
          <button
            key={c.id}
            type="button"
            disabled={ocupada}
            aria-pressed={actual === null ? undefined : c.id === actual}
            onClick={() => alElegir(c)}
            className={cn(
              "flex items-center gap-2 min-h-(--tactil-min) py-1 pl-1 pr-2 text-left text-sm font-medio leading-[1.2]",
              "bg-card text-foreground border border-input rounded-hoja cursor-pointer",
              "hover:bg-accent hover:border-border disabled:cursor-wait disabled:opacity-70",
              "aria-pressed:bg-primary aria-pressed:text-primary-foreground aria-pressed:border-transparent",
              "aria-pressed:shadow-boton aria-pressed:font-fuerte",
            )}
          >
            <MarcaCategoria categoria={c} tamano="opcion" />
            <span className="min-w-0 [overflow-wrap:anywhere]">{c.nombre}</span>
          </button>
        ))}
      </div>
      {alCancelar ? (
        <p className="flex justify-end">
          <Button type="button" variant="ghost" className="-mr-3" onClick={alCancelar} disabled={ocupada}>
            {T.cancelar}
          </Button>
        </p>
      ) : null}
    </div>
  );
}
