/** Estado de la pantalla y coordinación de sus operaciones. */
import { useDeshacer } from "@/compartido/deshacer/usar";
import { categoriaRestaurada, TEXTOS } from "@/compartido/textos/textos";
import { borrarCategoria, borrarRegla, useDatosCategorias } from "@/funcionalidades/categorias/cargar";
import { textoBorrada, type CategoriaConUso, type Regla } from "@/funcionalidades/categorias/datos";
import { useSesion } from "@/funcionalidades/sesion/sesion";
import { useState } from "react";

const T = TEXTOS.categorias;


type Abierto =
  | { tipo: "nueva" }
  | { tipo: "editar"; categoria: CategoriaConUso }
  | { tipo: "borrar"; categoria: CategoriaConUso };
export function useControlCategorias() {
  const { cliente } = useSesion();
  const { carga, recargar } = useDatosCategorias(cliente);
  const [abierto, setAbierto] = useState<Abierto | null>(null);
  const [resultado, setResultado] = useState<string | null>(null);
  const [borrandoRegla, setBorrandoRegla] = useState<number | null>(null);
  // Borrar una regla, o una categoría sin movimientos ni reglas (la API dice
  // `se_puede_deshacer_borrado`), es tocar y deshacer: sin diálogo (ítem 38).
  const deshacer = useDeshacer(cliente, () => recargar(true));

  /** Algo salió bien: se cierra el diálogo, se dice qué pasó y se recarga. */
  const terminar = (texto: string) => {
    deshacer.limpiar();
    setAbierto(null);
    setResultado(texto);
    void recargar(true);
  };

  const borrarReglaYa = async (regla: Regla) => {
    setResultado(null);
    deshacer.limpiar();
    setBorrandoRegla(regla.id);
    const r = await borrarRegla(cliente, regla.id);
    setBorrandoRegla(null);
    if (r.tipo === "sin-sesion") return;
    if (r.tipo === "error") {
      deshacer.mostrarError(r.texto);
      void recargar(true);
      return;
    }
    deshacer.ofrecer({
      deshacer: r.datos.deshacer,
      texto: T.reglaBorrada,
      restaurado: () => T.reglaRestaurada,
    });
    void recargar(true);
  };

  /** Borra sin confirmar. Devuelve el error para mostrarlo en el diálogo, o `null` si salió bien. */
  const borrarCategoriaYa = async (categoria: CategoriaConUso): Promise<string | null> => {
    const r = await borrarCategoria(cliente, categoria.id, null);
    if (r.tipo === "sin-sesion") return null;
    if (r.tipo === "error") return r.texto;
    const texto = textoBorrada(categoria.nombre, r.datos);
    if (r.datos.deshacer) {
      setAbierto(null);
      setResultado(null);
      deshacer.ofrecer({
        deshacer: r.datos.deshacer,
        texto,
        restaurado: () => categoriaRestaurada(categoria.nombre),
      });
      void recargar(true);
    } else {
      terminar(texto);
    }
    return null;
  };
  return { carga, recargar, abierto, setAbierto, resultado, setResultado, borrandoRegla, deshacer, terminar, borrarReglaYa, borrarCategoriaYa };
}
