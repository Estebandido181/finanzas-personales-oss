/** Crear y editar una categoría con el mismo formulario. */
import { cambiosGuardados, categoriaCreada, TEXTOS, tituloEditar } from "@/compartido/textos/textos";
import { claseColor, COLORES, componenteIcono, ICONOS, nombreColor, nombreIcono, } from "@/compartido/ui/categorias";
import { Aviso } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { Dialogo } from "@/compartido/ui/ui/dialogo";
import { Etiqueta, Input } from "@/compartido/ui/ui/input";
import { cn } from "@/compartido/ui/utils";
import { crearCategoria, editarCategoria, type Resultado } from "@/funcionalidades/categorias/cargar";
import { borradorNuevo, cambiosDe, hayErrores, limpiarNombre, MAXIMO_NOMBRE, planBorrado, revisarBorrador, type Borrador, type CategoriaConUso, type ErroresBorrador } from "@/funcionalidades/categorias/datos";
import { useSesion } from "@/funcionalidades/sesion/sesion";
import { Trash2 } from "lucide-react";
import { useId, useRef, useState, type ReactNode } from "react";
import { ErrorCampo } from "./piezas";

const T = TEXTOS.categorias;


// --- Nueva categoría y Editar ----------------------------------------------------------

export function Formulario({
  original,
  categorias,
  alCerrar,
  alTerminar,
  alBorrar,
  alBorrarYa,
}: {
  /** La que se edita; `null` al crear. */
  original: CategoriaConUso | null;
  categorias: CategoriaConUso[];
  alCerrar: () => void;
  alTerminar: (texto: string) => void;
  /** Borrar con confirmación (tiene movimientos o reglas): abre el diálogo de a qué categoría pasan. */
  alBorrar: (categoria: CategoriaConUso) => void;
  /** Borrar al tocar (se puede deshacer): devuelve el error, o `null` si salió bien. */
  alBorrarYa: (categoria: CategoriaConUso) => Promise<string | null>;
}) {
  const { cliente } = useSesion();
  const idFormulario = useId();
  const idNombre = useId();
  const idErrorNombre = useId();
  const nombre = useRef<HTMLInputElement>(null);
  const [borrador, setBorrador] = useState<Borrador>(() =>
    original
      ? { nombre: original.nombre, clase: original.clase, color: original.color, icono: original.icono }
      : borradorNuevo(categorias),
  );
  const [errores, setErrores] = useState<ErroresBorrador>({});
  const [errorApi, setErrorApi] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const cambiar = (cambios: Partial<Borrador>) => {
    setBorrador((antes) => ({ ...antes, ...cambios }));
    setErrorApi(null);
  };
  // Lo dice la API (`se_puede_deshacer_borrado`); la pantalla no lo deduce. La
  // última de su clase no se borra: ahí el diálogo sigue explicándolo.
  const borrarAlTocar =
    original !== null &&
    original.se_puede_deshacer_borrado &&
    planBorrado(original, categorias).tipo !== "ultima";

  const borrar = async (categoria: CategoriaConUso) => {
    if (!borrarAlTocar) {
      alBorrar(categoria);
      return;
    }
    setEnviando(true);
    setErrorApi(null);
    const error = await alBorrarYa(categoria);
    setEnviando(false);
    if (error) setErrorApi(error);
  };

  const enviar = async () => {
    const encontrados = revisarBorrador(borrador, categorias, original?.id ?? null);
    setErrores(encontrados);
    if (hayErrores(encontrados)) {
      if (encontrados.nombre) nombre.current?.focus();
      return;
    }
    let r: Resultado<unknown>;
    const limpio = limpiarNombre(borrador.nombre);
    if (original) {
      const cambios = cambiosDe(original, borrador);
      if (!cambios) {
        alCerrar();
        return;
      }
      setEnviando(true);
      r = await editarCategoria(cliente, original.id, cambios);
    } else {
      setEnviando(true);
      r = await crearCategoria(cliente, { ...borrador, nombre: limpio });
    }
    setEnviando(false);
    if (r.tipo === "sin-sesion") return;
    if (r.tipo === "error") {
      setErrorApi(r.texto);
      return;
    }
    alTerminar(original ? cambiosGuardados(limpio) : categoriaCreada(limpio));
  };

  return (
    <Dialogo
      titulo={original ? tituloEditar(original.nombre) : T.nueva}
      alCerrar={alCerrar}
      amplio
      acciones={
        <>
          {original ? (
            <Button
              type="button"
              variant="ghost"
              className="text-destructive computador:mr-auto computador:-ml-3"
              disabled={enviando}
              onClick={() => void borrar(original)}
            >
              <Trash2 aria-hidden="true" className="size-5" />
              {T.borrarCategoria}
            </Button>
          ) : null}
          <Button type="button" variant="outline" onClick={alCerrar} disabled={enviando}>
            {T.cancelar}
          </Button>
          <Button type="submit" form={idFormulario} disabled={enviando}>
            {original
              ? enviando
                ? T.guardando
                : T.guardar
              : enviando
                ? T.creando
                : T.crear}
          </Button>
        </>
      }
    >
      <form
        id={idFormulario}
        noValidate
        className="flex flex-col gap-(--espacio-grupo)"
        onSubmit={(e) => {
          e.preventDefault();
          void enviar();
        }}
      >
        {original ? (
          // La clase no se cambia al editar: se dice cuál es, sin control.
          <p className="text-muted-foreground">
            {original.clase === "gasto" ? T.claseGasto : T.claseIngreso}
          </p>
        ) : (
          <GrupoOpciones
            leyenda={T.clase}
            columnas="grid-cols-2"
            nombre={`${idFormulario}-clase`}
            valor={borrador.clase}
            alElegir={(clase) => cambiar({ clase })}
            opciones={(["gasto", "ingreso"] as const).map((clase) => ({
              valor: clase,
              contenido: <span className="font-medio">{clase === "gasto" ? T.gasto : T.ingreso}</span>,
              claseOpcion:
                "min-h-(--tactil-min) px-4 bg-secondary border border-borde-suave rounded-hoja has-checked:bg-primary has-checked:text-primary-foreground has-checked:border-transparent has-checked:shadow-boton has-checked:[&>span]:font-fuerte",
            }))}
          />
        )}
        <div className="flex flex-col gap-(--espacio-texto)">
          <Etiqueta htmlFor={idNombre}>{T.nombre}</Etiqueta>
          <Input
            ref={nombre}
            id={idNombre}
            value={borrador.nombre}
            maxLength={MAXIMO_NOMBRE}
            autoComplete="off"
            aria-invalid={errores.nombre ? true : undefined}
            aria-describedby={errores.nombre ? idErrorNombre : undefined}
            onChange={(e) => {
              cambiar({ nombre: e.target.value });
              if (errores.nombre) setErrores((antes) => ({ ...antes, nombre: undefined }));
            }}
          />
          {errores.nombre ? <ErrorCampo id={idErrorNombre}>{errores.nombre}</ErrorCampo> : null}
        </div>
        <GrupoOpciones
          leyenda={T.color}
          elegido={nombreColor(borrador.color)}
          columnas="grid-cols-6"
          nombre={`${idFormulario}-color`}
          valor={borrador.color}
          alElegir={(color) => {
            cambiar({ color });
            setErrores((antes) => ({ ...antes, icono: undefined }));
          }}
          opciones={COLORES.map((color) => ({
            valor: color,
            contenido: <Muestra color={color} icono={borrador.icono} nombre={nombreColor(color)} />,
            claseOpcion: CLASE_MUESTRA,
          }))}
        />
        <GrupoOpciones
          leyenda={T.icono}
          elegido={nombreIcono(borrador.icono)}
          columnas="grid-cols-6"
          nombre={`${idFormulario}-icono`}
          valor={borrador.icono}
          alElegir={(icono) => {
            cambiar({ icono });
            setErrores((antes) => ({ ...antes, icono: undefined }));
          }}
          error={errores.icono}
          opciones={ICONOS.map((icono) => ({
            valor: icono,
            contenido: <Muestra color={borrador.color} icono={icono} nombre={nombreIcono(icono)} />,
            claseOpcion: CLASE_MUESTRA,
          }))}
        />
        {errorApi ? <Aviso tipo="error">{errorApi}</Aviso> : null}
      </form>
    </Dialogo>
  );
}


/** Opción de color o de ícono: cuadro de 44 px; la elegida, con un marco grueso de tinta. */
const CLASE_MUESTRA =
  "size-(--tactil-min) rounded-hoja p-0.5 border-2 border-transparent has-checked:border-foreground";


/** El cuadro de la categoría con ese color e ícono (así se ve cómo quedará). */
function Muestra({ color, icono, nombre }: { color: (typeof COLORES)[number]; icono: (typeof ICONOS)[number]; nombre: string }) {
  const Icono = componenteIcono(icono);
  return (
    <>
      <span
        aria-hidden="true"
        className={cn("grid place-items-center size-full rounded-chip bg-(--c) text-(--cat-icono)", claseColor(color))}
      >
        <Icono className="size-[18px]" />
      </span>
      <span className="sr-only">{nombre}</span>
    </>
  );
}


/**
 * Un grupo de radios nativos (teclado con flechas, sin JavaScript propio):
 * cada opción es una etiqueta que envuelve su radio, oculto a la vista pero
 * no al lector de pantalla. El foco del teclado se ve en la etiqueta.
 */
function GrupoOpciones<V extends string>({
  leyenda,
  elegido,
  columnas,
  nombre,
  valor,
  alElegir,
  opciones,
  error,
}: {
  leyenda: string;
  /** El nombre de lo elegido, junto a la leyenda ("Color · Vino"). */
  elegido?: string;
  columnas: string;
  nombre: string;
  valor: V;
  alElegir: (valor: V) => void;
  opciones: { valor: V; contenido: ReactNode; claseOpcion: string }[];
  error?: string;
}) {
  const idError = useId();
  return (
    <fieldset aria-describedby={error ? idError : undefined} className="flex flex-col gap-(--espacio-texto)">
      <legend className="font-fuerte mb-(--espacio-texto)">
        {leyenda}
        {elegido ? <span className="font-normal text-muted-foreground"> · {elegido}</span> : null}
      </legend>
      <div className={cn("grid gap-2 w-fit max-w-full", columnas)}>
        {opciones.map((o) => (
          <label
            key={o.valor}
            className={cn(
              "relative inline-flex items-center justify-center cursor-pointer",
              "has-focus-visible:outline-(length:--borde-foco) has-focus-visible:outline-solid has-focus-visible:outline-ring has-focus-visible:outline-offset-2",
              o.claseOpcion,
            )}
          >
            <input
              type="radio"
              name={nombre}
              value={o.valor}
              checked={o.valor === valor}
              onChange={() => alElegir(o.valor)}
              className="sr-only"
            />
            {o.contenido}
          </label>
        ))}
      </div>
      {error ? <ErrorCampo id={idError}>{error}</ErrorCampo> : null}
    </fieldset>
  );
}
