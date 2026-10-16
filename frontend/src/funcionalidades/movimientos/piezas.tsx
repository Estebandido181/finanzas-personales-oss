/** Piezas internas reutilizadas por esta funcionalidad. */
import { TEXTOS } from "@/compartido/textos/textos";
import { useVisibleTras } from "@/compartido/ui/pantalla";

export function Cargando() {
  const visible = useVisibleTras();
  return visible ? (
    <p role="status" className="text-muted-foreground">
      {TEXTOS.app.cargando}
    </p>
  ) : null;
}
