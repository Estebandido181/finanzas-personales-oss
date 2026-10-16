/**
 * Marco de la app con sesión: barra lateral en el computador (≥ 900 px) y
 * barra inferior en el celular (SISTEMA.md, "Navegación"). Son componentes
 * propios, fieles al prototipo (diseno/prototipo/inicio.html y mas.html):
 * el `Sidebar` de shadcn/ui arrastra Sheet (Dialog), Tooltip y una cookie
 * propia, que aquí no hacen falta (decisión del ítem 12).
 */
import { LogOut, Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Link, useLocation } from "wouter";
import favicon from "../../../diseno/favicon.svg";
import { Aviso, Contador, Segmentos } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { cn } from "@/compartido/ui/utils";
import { useSesion } from "@/funcionalidades/sesion/sesion";
import { useTema, type Tema } from "@/compartido/tema/preferencias";
import { TEXTOS } from "@/compartido/textos/textos";
import { useContadorNoReconocidos } from "@/funcionalidades/sincronizacion/contador";
import { esSeccionActual, SECCIONES, type Seccion } from "@/app/navegacion/secciones";

export const OPCIONES_TEMA: readonly { valor: Tema; texto: string; icono: typeof Monitor }[] = [
  { valor: "sistema", texto: TEXTOS.apariencia.sistema, icono: Monitor },
  { valor: "claro", texto: TEXTOS.apariencia.claro, icono: Sun },
  { valor: "oscuro", texto: TEXTOS.apariencia.oscuro, icono: Moon },
];

/** Elemento de navegación "pestaña" (barra lateral y lista de "Más"). */
export const CLASE_PESTANA = cn(
  "flex items-center gap-3 min-h-(--tactil-min) px-3 no-underline font-medio",
  "border border-transparent rounded-hoja hover:bg-sidebar-accent",
  "aria-[current=page]:bg-card aria-[current=page]:papel",
  "aria-[current=page]:shadow-boton aria-[current=page]:font-fuerte",
);

export function Marco({ children }: { children: ReactNode }) {
  return (
    <>
      <a
        href="#contenido"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-30 focus:bg-card focus:text-foreground focus:p-3 focus:border focus:border-border focus:rounded-hoja"
      >
        {TEXTOS.app.saltarAlContenido}
      </a>
      <div className="min-h-screen computador:grid computador:grid-cols-[var(--ancho-barra-lateral)_minmax(0,1fr)]">
        <BarraLateral />
        <main
          id="contenido"
          tabIndex={-1}
          className={cn(
            "max-w-(--ancho-contenido) px-(--espacio-pagina) pt-8",
            "pb-[calc(var(--alto-barra-inferior)+var(--espacio-10))]",
            "computador:pt-12 computador:pb-16 focus:outline-none",
          )}
        >
          {children}
        </main>
      </div>
      <BarraInferior />
    </>
  );
}

function useActual(): (ruta: string) => boolean {
  const [ubicacion] = useLocation();
  return (ruta) => esSeccionActual(ruta, ubicacion);
}

function BarraLateral() {
  const actual = useActual();
  const contador = useContadorNoReconocidos();
  const [tema, elegirTema] = useTema();
  const idApariencia = useId();
  return (
    <aside className="hidden computador:block bg-sidebar text-sidebar-foreground border-r border-sidebar-border">
      <div className="sticky top-0 h-screen overflow-y-auto flex flex-col gap-6 pt-8 px-4 pb-6">
        <Link
          href="/"
          className="flex items-center gap-3 px-3 min-h-(--tactil-min) no-underline font-titulos text-xl font-[600]"
        >
          <img src={favicon} alt="" className="size-8" />
          {TEXTOS.app.marca}
        </Link>
        <nav aria-label={TEXTOS.app.secciones} className="flex flex-col gap-1">
          {SECCIONES.filter((s) => s.enLateral).map((s) => (
            <ElementoLateral
              key={s.id}
              seccion={s}
              actual={actual(s.ruta)}
              contador={s.id === "no-reconocidos" ? contador : null}
            />
          ))}
        </nav>
        <div className="mt-auto flex flex-col gap-3">
          <p id={idApariencia} className="text-muted-foreground text-sm">
            {TEXTOS.apariencia.titulo}
          </p>
          <Segmentos
            opciones={OPCIONES_TEMA}
            valor={tema}
            alElegir={elegirTema}
            idEtiqueta={idApariencia}
            compacto
          />
          <BotonCerrarSesion variante="ghost" />
        </div>
      </div>
    </aside>
  );
}

function ElementoLateral({
  seccion: { ruta, nombre, icono: Icono },
  actual,
  contador,
}: {
  seccion: Seccion;
  actual: boolean;
  contador: number | null;
}) {
  return (
    <Link href={ruta} aria-current={actual ? "page" : undefined} className={CLASE_PESTANA}>
      <Icono aria-hidden="true" className="size-5" />
      <span>{nombre}</span>
      {contador ? <Contador cantidad={contador} /> : null}
    </Link>
  );
}

function BarraInferior() {
  const actual = useActual();
  // Lo que solo se alcanza desde «Más» (No reconocidos) deja «Más» marcada.
  const enMas = SECCIONES.filter((s) => !s.enInferior && s.enLateral);
  return (
    <nav
      aria-label={TEXTOS.app.secciones}
      className={cn(
        "computador:hidden fixed inset-x-0 bottom-0 z-10 grid grid-cols-5",
        "h-(--alto-barra-inferior) pb-[env(safe-area-inset-bottom)] bg-card papel border-t border-borde-hoja",
        "shadow-barra",
      )}
    >
      {SECCIONES.filter((s) => s.enInferior).map(({ id, ruta, nombreCorto, icono: Icono }) => (
        <Link
          key={id}
          href={ruta}
          aria-current={
            actual(ruta) || (id === "mas" && enMas.some((s) => actual(s.ruta))) ? "page" : undefined
          }
          className={cn(
            "relative flex flex-col items-center justify-center gap-0.5 min-h-(--tactil-min)",
            "text-sm leading-[1.1] no-underline text-muted-foreground",
            "aria-[current=page]:text-foreground aria-[current=page]:font-fuerte",
            // Raya gruesa de tinta arriba: marca la sección sin depender del color.
            "aria-[current=page]:before:absolute aria-[current=page]:before:-top-px",
            "aria-[current=page]:before:inset-x-[18%] aria-[current=page]:before:h-[3px]",
            "aria-[current=page]:before:bg-foreground aria-[current=page]:before:content-['']",
          )}
        >
          <Icono aria-hidden="true" className="size-[22px]" />
          <span>{nombreCorto}</span>
        </Link>
      ))}
    </nav>
  );
}

/** "Cerrar sesión": mientras dura dice "Cerrando sesión…"; si falla, lo dice debajo. */
export function BotonCerrarSesion({
  variante,
  className,
}: {
  variante: "ghost" | "outline";
  className?: string;
}) {
  const { salir } = useSesion();
  const [enCurso, setEnCurso] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const montado = useRef(true);
  useEffect(
    () => () => {
      montado.current = false;
    },
    [],
  );
  return (
    <div className={className}>
      <Button
        type="button"
        variant={variante}
        disabled={enCurso}
        className={variante === "outline" ? "w-full" : "justify-start"}
        onClick={async () => {
          setEnCurso(true);
          setError(null);
          const mensaje = await salir();
          // Si cerró, este botón ya no existe (la app volvió a "Entrar").
          if (montado.current) {
            setEnCurso(false);
            setError(mensaje);
          }
        }}
      >
        <LogOut aria-hidden="true" className="size-5" />
        {enCurso ? TEXTOS.cerrarSesion.botonEnCurso : TEXTOS.cerrarSesion.boton}
      </Button>
      {error ? (
        <Aviso tipo="error" className="mt-3">
          {error}
        </Aviso>
      ) : null}
    </div>
  );
}
