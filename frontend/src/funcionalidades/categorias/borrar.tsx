/** Diálogo para borrar una categoría y elegir su destino. */
import { TEXTOS, tituloBorrarCategoria } from "@/compartido/textos/textos";
import { Aviso } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { Dialogo } from "@/compartido/ui/ui/dialogo";
import { Etiqueta } from "@/compartido/ui/ui/input";
import { Selector } from "@/compartido/ui/ui/selector";
import { borrarCategoria } from "@/funcionalidades/categorias/cargar";
import { botonBorrar, planBorrado, textoBorrada, type CategoriaConUso } from "@/funcionalidades/categorias/datos";
import { useSesion } from "@/funcionalidades/sesion/sesion";
import { Trash2 } from "lucide-react";
import { useId, useState } from "react";

const T = TEXTOS.categorias;


// --- Borrar ------------------------------------------------------------------------------

export function BorrarCategoria({
  categoria,
  categorias,
  alCerrar,
  alTerminar,
}: {
  categoria: CategoriaConUso;
  categorias: CategoriaConUso[];
  alCerrar: () => void;
  alTerminar: (texto: string) => void;
}) {
  const { cliente } = useSesion();
  const idDestino = useId();
  const plan = planBorrado(categoria, categorias);
  const [destino, setDestino] = useState<number | null>(plan.tipo === "mover" ? plan.destinoInicial : null);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const elegido = plan.tipo === "mover" ? plan.destinos.find((c) => c.id === destino) : undefined;

  const borrar = async () => {
    setEnviando(true);
    setError(null);
    const r = await borrarCategoria(cliente, categoria.id, plan.tipo === "mover" ? destino : null);
    setEnviando(false);
    if (r.tipo === "sin-sesion") return;
    if (r.tipo === "error") {
      setError(r.texto);
      return;
    }
    alTerminar(textoBorrada(categoria.nombre, r.datos));
  };

  return (
    <Dialogo
      titulo={tituloBorrarCategoria(categoria.nombre)}
      descripcion={<p>{plan.texto}</p>}
      alCerrar={alCerrar}
      acciones={
        <>
          <Button type="button" variant="outline" onClick={alCerrar} disabled={enviando}>
            {T.cancelar}
          </Button>
          {plan.tipo === "ultima" ? null : (
            <Button type="button" variant="destructive" onClick={() => void borrar()} disabled={enviando}>
              <Trash2 aria-hidden="true" className="size-5" />
              {enviando ? T.borrando : botonBorrar(plan, elegido)}
            </Button>
          )}
        </>
      }
    >
      {plan.tipo === "mover" ? (
        <div className="flex flex-col gap-(--espacio-texto)">
          <Etiqueta htmlFor={idDestino}>{T.pasarA}</Etiqueta>
          <Selector id={idDestino} value={destino ?? ""} onChange={(e) => setDestino(Number(e.target.value))}>
            {plan.destinos.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nombre}
              </option>
            ))}
          </Selector>
        </div>
      ) : null}
      {error ? <Aviso tipo="error">{error}</Aviso> : null}
    </Dialogo>
  );
}
