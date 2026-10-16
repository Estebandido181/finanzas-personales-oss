/**
 * Categorías y reglas (ítem 15). Sigue los prototipos aprobados
 * (diseno/prototipo/categorias.html y categorias-borrar.html) y TEXTOS.md,
 * "Categorías y reglas".
 *
 * Tres hojas: "Categorías de gasto" y "Categorías de ingreso" (a la
 * izquierda en el computador) y "Reglas". "Nueva categoría" y "Editar" abren
 * el mismo formulario (nombre, color e ícono; al crear, también si es de
 * gasto o de ingreso); "Borrar categoría" abre el diálogo que elige a qué
 * categoría de la misma clase pasan sus movimientos y reglas. Los diálogos
 * son el `<dialog>` nativo (components/ui/dialogo.tsx).
 */
import { TEXTOS } from "@/compartido/textos/textos";
import { AvisoDeshacer } from "@/compartido/ui/aviso-deshacer";
import { Hoja, Vacio } from "@/compartido/ui/libreta";
import { Encabezado, Pila } from "@/compartido/ui/pantalla";
import { Button } from "@/compartido/ui/ui/button";
import { deLaClase } from "@/funcionalidades/categorias/datos";
import { CircleAlert, Plus, WifiOff } from "lucide-react";
import { BorrarCategoria } from "./borrar";
import { useControlCategorias } from "./controlador";
import { Formulario } from "./formulario";
import { HojaCategorias, HojaReglas } from "./hojas";
import { AvisoResultado, Cargando } from "./piezas";

const T = TEXTOS.categorias;


export function Categorias() {
  const { carga, recargar, abierto, setAbierto, resultado, setResultado, borrandoRegla, deshacer, terminar, borrarReglaYa, borrarCategoriaYa } = useControlCategorias();


  return (
    <Pila>
      <Encabezado titulo={T.titulo}>
        {carga.tipo === "listo" ? (
          <Button
            type="button"
            onClick={() => {
              setResultado(null);
              setAbierto({ tipo: "nueva" });
            }}
          >
            <Plus aria-hidden="true" className="size-5" />
            {T.nueva}
          </Button>
        ) : null}
      </Encabezado>
      {carga.tipo === "cargando" ? (
        <Cargando />
      ) : carga.tipo === "error" ? (
        <Hoja>
          <Vacio
            icono={carga.sinRed ? WifiOff : CircleAlert}
            accion={
              <Button type="button" onClick={() => void recargar()}>
                {TEXTOS.errores.volverAIntentar}
              </Button>
            }
          >
            <p role="alert">{carga.mensaje}</p>
          </Vacio>
        </Hoja>
      ) : (
        <>
          {resultado ? <AvisoResultado texto={resultado} /> : null}
          <AvisoDeshacer
            estado={deshacer.estado}
            alDeshacer={() => void deshacer.deshacer()}
            alPausar={deshacer.pausar}
            alReanudar={deshacer.reanudar}
          />
          <div
            aria-busy={carga.actualizando}
            className="grid gap-(--espacio-bloques) computador:grid-cols-2 computador:items-start"
          >
            <div className="flex flex-col gap-(--espacio-bloques)">
              {(["gasto", "ingreso"] as const).map((clase) => (
                <HojaCategorias
                  key={clase}
                  clase={clase}
                  categorias={deLaClase(carga.datos.categorias, clase)}
                  alEditar={(categoria) => {
                    setResultado(null);
                    setAbierto({ tipo: "editar", categoria });
                  }}
                />
              ))}
            </div>
            <HojaReglas
              reglas={carga.datos.reglas}
              borrandoId={borrandoRegla}
              alBorrar={(regla) => void borrarReglaYa(regla)}
            />
          </div>
          {abierto?.tipo === "nueva" || abierto?.tipo === "editar" ? (
            <Formulario
              key={abierto.tipo === "editar" ? abierto.categoria.id : "nueva"}
              original={abierto.tipo === "editar" ? abierto.categoria : null}
              categorias={carga.datos.categorias}
              alCerrar={() => setAbierto(null)}
              alTerminar={terminar}
              alBorrar={(categoria) => setAbierto({ tipo: "borrar", categoria })}
              alBorrarYa={borrarCategoriaYa}
            />
          ) : abierto?.tipo === "borrar" ? (
            <BorrarCategoria
              categoria={abierto.categoria}
              categorias={carga.datos.categorias}
              alCerrar={() => setAbierto(null)}
              alTerminar={terminar}
            />
          ) : null}
        </>
      )}
    </Pila>
  );
}
