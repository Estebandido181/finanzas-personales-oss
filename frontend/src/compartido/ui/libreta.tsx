/**
 * Piezas propias del sistema "libreta de cuentas" que no existen en shadcn/ui
 * (SISTEMA.md): hoja, aviso, estado vacío, segmentos y contador. Solo usan
 * clases que salen de los tokens (src/estilos.css).
 */
import type { LucideIcon } from "lucide-react";
import { CircleAlert, CircleCheck, Info } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/compartido/ui/utils";
import { correos } from "@/compartido/textos/textos";

/**
 * Una hoja de libro mayor sobre el papel: grano, doble raya roja del margen
 * y sombra difusa de papel. Sin borde de tinta ni sombra sólida.
 */
export function Hoja({ className, ...props }: ComponentProps<"section">) {
  return (
    <section
      className={cn(
        "bg-card hoja-libro text-card-foreground border border-borde-hoja rounded-hoja shadow-hoja p-(--espacio-hoja)",
        className,
      )}
      {...props}
    />
  );
}

/** Texto de ayuda: secundario, 14 px, líneas cortas. */
export function Ayuda({ className, ...props }: ComponentProps<"p">) {
  return <p className={cn("text-muted-foreground text-sm max-w-[60ch]", className)} {...props} />;
}

const FONDO_AVISO = {
  info: "bg-aviso-info",
  error: "bg-aviso-error",
  exito: "bg-aviso-exito",
  advertencia: "bg-aviso-advertencia",
} as const;

const COLOR_ICONO_AVISO = {
  info: "",
  error: "text-destructive",
  exito: "text-exito",
  advertencia: "",
} as const;

/**
 * Aviso corto de una línea. `error` usa role="alert"; `info` y `exito`
 * (resultado de una acción), role="status".
 */
export function Aviso({
  tipo,
  children,
  className,
}: {
  tipo: "info" | "error" | "exito";
  children: ReactNode;
  className?: string;
}) {
  const Icono = tipo === "error" ? CircleAlert : tipo === "exito" ? CircleCheck : Info;
  return (
    <div
      role={tipo === "error" ? "alert" : "status"}
      className={cn(
        "grid grid-cols-[auto_1fr] gap-3 p-5 rounded-hoja text-foreground",
        FONDO_AVISO[tipo],
        className,
      )}
    >
      <Icono aria-hidden="true" className={cn("size-5 mt-0.5", COLOR_ICONO_AVISO[tipo])} />
      <p>{children}</p>
    </div>
  );
}

/**
 * Nota fija de una hoja (prototipo saldo.html: "Sincroniza antes de
 * ajustar…"): fondo de aviso informativo, ícono, texto y, si hay, acciones
 * debajo. Es `role="note"`: está siempre, no es el resultado de una acción.
 */
export function Nota({
  children,
  acciones,
  className,
}: {
  children: ReactNode;
  acciones?: ReactNode;
  className?: string;
}) {
  return (
    <div
      role="note"
      className={cn("grid grid-cols-[auto_1fr] gap-3 p-5 rounded-hoja text-foreground", FONDO_AVISO.info, className)}
    >
      <Info aria-hidden="true" className="size-5 mt-0.5" />
      <div className="flex flex-col gap-2 min-w-0">
        {children}
        {acciones ? <div className="flex flex-wrap gap-3 mt-2">{acciones}</div> : null}
      </div>
    </div>
  );
}

/**
 * Aviso con título, texto y acciones (SISTEMA.md, "Aviso"): los pendientes
 * de Inicio y la sincronización fallida. `destacado` le pone la sombra de hoja
 * (el aviso importante). El título es un h2 cuando el aviso es una sección
 * de la pantalla por sí mismo; si no, un párrafo en negrita.
 */
export function AvisoConTitulo({
  tipo,
  icono: Icono,
  titulo,
  idTitulo,
  tituloComoEncabezado = false,
  destacado = false,
  alerta = false,
  resultado = false,
  acciones,
  accionesApiladas = false,
  children,
  className,
  ...props
}: {
  tipo: "error" | "advertencia" | "exito";
  icono: LucideIcon;
  /** Texto, o texto con un monto en su letra (ítem 17: "Regla creada: transferencias de $3.200…"). */
  titulo: ReactNode;
  idTitulo: string;
  tituloComoEncabezado?: boolean;
  destacado?: boolean;
  /** role="alert": se anuncia apenas aparece. */
  alerta?: boolean;
  /** role="status": el resultado de una acción, cerca de donde se hizo. */
  resultado?: boolean;
  acciones?: ReactNode;
  /** Las acciones una por línea en el celular (ofertas de regla, con textos largos). */
  accionesApiladas?: boolean;
  children?: ReactNode;
} & Omit<ComponentProps<"section">, "role" | "title" | "children">) {
  const Titulo = tituloComoEncabezado ? "h2" : "p";
  return (
    <section
      aria-labelledby={idTitulo}
      role={alerta ? "alert" : resultado ? "status" : undefined}
      {...props}
      className={cn(
        "grid grid-cols-[auto_1fr] gap-3 p-5 rounded-hoja text-foreground",
        FONDO_AVISO[tipo],
        destacado && "shadow-hoja",
        className,
      )}
    >
      <Icono aria-hidden="true" className={cn("size-5 mt-0.5", COLOR_ICONO_AVISO[tipo])} />
      <div className="flex flex-col gap-2 min-w-0">
        <Titulo
          id={idTitulo}
          className={cn(
            "font-texto text-base font-fuerte",
            // Como en el prototipo: el h2 conserva el interlineado de los títulos.
            tituloComoEncabezado ? "leading-(--interlineado-titulos)" : "leading-(--interlineado-texto)",
          )}
        >
          {titulo}
        </Titulo>
        {children}
        {acciones ? (
          <div
            className={cn(
              "flex flex-wrap gap-3 mt-2",
              accionesApiladas && "flex-col items-stretch computador:flex-row computador:items-center",
            )}
          >
            {acciones}
          </div>
        ) : null}
      </div>
    </section>
  );
}

/** Estado vacío: ícono, título, qué hacer y (opcional) una acción. */
export function Vacio({
  icono: Icono,
  titulo,
  children,
  accion,
  idTitulo,
}: {
  icono: LucideIcon;
  /** Sin título si ya lo dice el h1 de la pantalla. */
  titulo?: string;
  children: ReactNode;
  accion?: ReactNode;
  idTitulo?: string;
}) {
  return (
    <div className="text-center px-(--espacio-hoja) py-12 flex flex-col items-center gap-4">
      <Icono aria-hidden="true" className="size-10 text-muted-foreground" />
      {titulo ? <h2 id={idTitulo}>{titulo}</h2> : null}
      <div className="max-w-[44ch] flex flex-col gap-2">{children}</div>
      {accion}
    </div>
  );
}

/**
 * Grupo de botones que se excluyen (Apariencia). Botones nativos con
 * `aria-pressed`, como en el prototipo: sin Radix ni estilos inyectados.
 */
export function Segmentos<T extends string>({
  opciones,
  valor,
  alElegir,
  idEtiqueta,
  nombre,
  compacto = false,
  enFila = false,
}: {
  opciones: readonly { valor: T; texto: string; icono?: LucideIcon }[];
  valor: T;
  alElegir: (valor: T) => void;
  idEtiqueta?: string;
  /** Nombre del grupo si no hay una etiqueta visible ("Mostrar", en Movimientos). */
  nombre?: string;
  /** En la barra lateral: ícono sobre texto, tres en una fila. */
  compacto?: boolean;
  /** Cada botón con su ancho (mínimo 104 px), uno tras otro: "Ver como". */
  enFila?: boolean;
}) {
  return (
    <div
      role="group"
      aria-labelledby={idEtiqueta}
      aria-label={idEtiqueta ? undefined : nombre}
      className={cn(
        enFila ? "flex flex-wrap" : "grid grid-cols-3",
        compacto ? "gap-1" : "gap-2",
      )}
    >
      {opciones.map(({ valor: opcion, texto, icono: Icono }) => (
        <button
          key={opcion}
          type="button"
          aria-pressed={opcion === valor}
          onClick={() => alElegir(opcion)}
          className={cn(
            "inline-flex items-center justify-center min-h-(--tactil-min) cursor-pointer",
            "bg-secondary text-foreground border border-borde-suave rounded-hoja font-medio",
            "aria-pressed:bg-primary aria-pressed:text-primary-foreground",
            "aria-pressed:border-transparent aria-pressed:shadow-boton aria-pressed:font-fuerte",
            compacto ? "flex-col gap-0.5 p-1 min-h-14 text-sm" : "gap-2 px-2",
            enFila && "min-w-26 px-4",
          )}
        >
          {Icono ? <Icono aria-hidden="true" className="size-5" /> : null}
          {texto}
        </button>
      ))}
    </div>
  );
}

/** Contador de correos (en la navegación): se ve el número, se lee "3 correos". */
export function Contador({ cantidad }: { cantidad: number }) {
  return (
    <span className="ml-auto text-sm font-fuerte min-w-6 px-1.5 text-center border border-current rounded-chip">
      <span aria-hidden="true">{cantidad}</span>
      <span className="sr-only"> {correos(cantidad)}</span>
    </span>
  );
}
