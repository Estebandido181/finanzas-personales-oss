/** Presentación, edición y resultado de una fila. */
import { Aviso, AvisoConTitulo, Ayuda } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { llevaMarcaDeCategoria, montoDeFila } from "@/funcionalidades/movimientos/presentacion";
import { Check, HandCoins, Info, Pencil, Scale, Tags } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import { hora } from "@/compartido/formatos/formato";
import { TEXTOS } from "@/compartido/textos/textos";
import { ConMonto, MarcaCategoria, MarcaNeutra, Monto } from "@/compartido/ui/cifras";
import { cn } from "@/compartido/ui/utils";
import { nombreTipo, ofertasRegla, origenDe, textoGuardado, type Categoria, type Movimiento, type OfertaRegla, type Origen } from "@/funcionalidades/movimientos/datos";
import { Opciones } from "@/funcionalidades/movimientos/opciones";

const T = TEXTOS.movimientos;


/** Qué pasó en una fila tras tocar una categoría (o crear la regla). */
export type EstadoFila =
  | {
      fase: "guardado";
      categoria: Categoria;
      origenAntes: Origen["tipo"];
      ofrece: boolean;
      /** Falló crear la regla (la categoría sí quedó guardada). */
      errorRegla?: string;
    }
  | { fase: "regla"; categoria: Categoria; texto: string; montoCentavos: number | null }
  | { fase: "error"; texto: string };


export function FilaMovimiento({
  movimiento: m,
  categorias,
  estado,
  abierta,
  ocupada,
  alAbrir,
  alCerrar,
  alElegir,
  alCrearRegla,
  alDescartar,
}: {
  movimiento: Movimiento;
  categorias: Categoria[];
  estado: EstadoFila | null;
  abierta: boolean;
  ocupada: boolean;
  alAbrir: () => void;
  alCerrar: () => void;
  alElegir: (categoria: Categoria) => void;
  alCrearRegla: (estado: Extract<EstadoFila, { fase: "guardado" }>, oferta: OfertaRegla) => void;
  alDescartar: () => void;
}) {
  // Recién categorizada aquí: se muestra con lo elegido (en la bandeja, la fila
  // ya no vuelve en la lista; en un mes, la lista recargada dice lo mismo).
  const elegida = estado && estado.fase !== "error" ? estado.categoria : null;
  const origen: Origen = elegida ? { tipo: "manual", categoria: elegida.nombre } : origenDe(m);
  const pendiente = origen.tipo === "sin-categorizar";
  const monto = montoDeFila(m);
  const categorizable = m.categorizable;
  const conResultado = estado !== null && estado.fase !== "error";
  const mostrarPanel = abierta || conResultado;
  const motivoId = useId();

  return (
    <li
      className={cn(
        "grid grid-cols-[auto_minmax(0,1fr)_auto] gap-x-3 items-start py-(--espacio-fila)",
        "[grid-template-areas:'marca_desc_monto'_'marca_meta_meta'_'marca_origen_accion'_'panel_panel_panel']",
        "not-first:border-t not-first:border-renglon",
        pendiente ? "bg-aviso-advertencia -mx-(--espacio-hoja) px-(--espacio-hoja)" : "last:pb-0",
      )}
    >
      {elegida || llevaMarcaDeCategoria(m) ? (
        <MarcaCategoria categoria={elegida ?? m.categoria} className="[grid-area:marca] mt-0.5" />
      ) : (
        <MarcaNeutra icono={m.tipo === "ingreso" ? HandCoins : Scale} className="[grid-area:marca] mt-0.5" />
      )}
      <p className="[grid-area:desc] font-medio [overflow-wrap:anywhere]">{m.descripcion}</p>
      <p className="[grid-area:meta] text-muted-foreground text-sm">
        {nombreTipo(m.tipo)} · {hora(m.fecha_hora)}
      </p>
      <p className="[grid-area:monto] text-right">
        <Monto
          className={cn(
            monto.clase === "suma" && "text-monto-positivo",
            monto.clase === "resta" && "text-monto-negativo",
          )}
        >
          {monto.texto}
        </Monto>
      </p>
      {origen.tipo !== "no-aplica" ? (
        <p className="[grid-area:origen] self-center mt-1 text-muted-foreground text-sm">
          <ComoSeCategorizo origen={origen} />
        </p>
      ) : null}
      {((categorizable && !abierta) || m.puede_descartar || m.motivo_no_descartar) ? (
        <div className="[grid-area:accion] flex flex-wrap gap-2 justify-end self-center">
          {categorizable && !abierta ? pendiente ? (
            <Button type="button" variant="outline" onClick={alAbrir}>
              {/* Se lee "Categorizar PANADERIA EL TRIGAL" (TEXTOS.md: las acciones de fila llevan el objeto). */}
              <span aria-hidden="true">{T.categorizar}</span>
              <span className="sr-only">{`${T.categorizar} ${m.descripcion}`}</span>
            </Button>
          ) : (
            <Button type="button" variant="ghost" className="-mr-3" onClick={alAbrir}>
              <Pencil aria-hidden="true" className="size-5" />
              <span aria-hidden="true">{T.cambiar}</span>
              <span className="sr-only">{`${T.cambiar} categoría de ${m.descripcion}`}</span>
            </Button>
          ) : null}
          {m.puede_descartar || m.motivo_no_descartar ? <Button type="button" variant="ghost" disabled={ocupada || !m.puede_descartar}
            aria-label={`Descartar ${m.descripcion}`} aria-describedby={m.motivo_no_descartar ? motivoId : undefined} onClick={alDescartar}>Descartar</Button> : null}
        </div>
      ) : null}
      {mostrarPanel || m.motivo_no_descartar ? (
        <div className="[grid-area:panel] mt-4 flex flex-col gap-4">
          {m.motivo_no_descartar ? <Ayuda id={motivoId}>{m.motivo_no_descartar}</Ayuda> : null}
          {estado?.fase === "error" ? <Aviso tipo="error">{estado.texto}</Aviso> : null}
          {abierta ? (
            <Opciones
              categorias={categorias}
              actual={pendiente ? null : (elegida?.id ?? m.categoria?.id ?? null)}
              ocupada={ocupada}
              alElegir={alElegir}
              alCancelar={pendiente ? undefined : alCerrar}
            />
          ) : conResultado ? (
            <Resultado movimiento={m} estado={estado} ocupada={ocupada} alCrearRegla={alCrearRegla} />
          ) : null}
        </div>
      ) : null}
    </li>
  );
}


/** "Transporte, por regla: transferencia a «*3000000001»", "Salud, a mano"… */
function ComoSeCategorizo({ origen }: { origen: Exclude<Origen, { tipo: "no-aplica" }> }) {
  if (origen.tipo === "sin-categorizar") return <>{T.sinCategorizar}</>;
  const Icono = origen.tipo === "manual" ? Pencil : origen.tipo === "desconocido" ? Info : Tags;
  const cola =
    origen.tipo === "manual"
      ? T.aMano
      : origen.tipo === "regla"
        ? <>{T.porRegla} <ConMonto texto={origen.frase} montoCentavos={origen.montoCentavos} /></>
        : origen.tipo === "regla-borrada"
          ? T.porReglaBorrada
          : T.desconocido;
  return (
    <>
      <Icono aria-hidden="true" className="inline size-4 align-[-3px] mr-1" />
      <strong className="font-fuerte">{origen.categoria}</strong>, {cola}
    </>
  );
}


/**
 * Lo que pasó al tocar una categoría: "Guardado en Mercado." con la oferta de
 * la regla, "Cambiado a Antojos…" o "Regla creada: …". Recibe el foco (así el
 * teclado sigue desde aquí: las opciones ya no están).
 */
function Resultado({
  movimiento,
  estado,
  ocupada,
  alCrearRegla,
}: {
  movimiento: Movimiento;
  estado: Exclude<EstadoFila, { fase: "error" }>;
  ocupada: boolean;
  alCrearRegla: (estado: Extract<EstadoFila, { fase: "guardado" }>, oferta: OfertaRegla) => void;
}) {
  const id = useId();
  const aviso = useRef<HTMLElement>(null);
  useEffect(() => {
    aviso.current?.focus();
  }, [estado.fase]);

  if (estado.fase === "regla") {
    return (
      <AvisoConTitulo
        ref={aviso}
        tabIndex={-1}
        className="focus:outline-none"
        tipo="exito"
        icono={Check}
        titulo={<ConMonto texto={estado.texto} montoCentavos={estado.montoCentavos} />}
        idTitulo={id}
        resultado
      />
    );
  }
  const textos = textoGuardado(estado.categoria.nombre, estado.origenAntes);
  return (
    <AvisoConTitulo
      ref={aviso}
      tabIndex={-1}
      className="focus:outline-none"
      tipo="exito"
      icono={Check}
      titulo={textos.titulo}
      idTitulo={id}
      resultado
      accionesApiladas
      acciones={
        estado.ofrece
          ? ofertasRegla(movimiento).map((oferta) => (
              <Button
                key={oferta.condiciones}
                type="button"
                variant="outline"
                className="justify-start text-left"
                disabled={ocupada}
                onClick={() => alCrearRegla(estado, oferta)}
                // "Las dos cosas juntas" se entiende al verla junto a las otras; al oírla, se dice cuáles
                // (el nombre empieza por lo que se ve: así también sirve para el control por voz).
                aria-label={oferta.detalle ? `${oferta.boton}: ${oferta.detalle}` : undefined}
              >
                <span>
                  <ConMonto texto={oferta.boton} montoCentavos={oferta.montoCentavos} />
                </span>
              </Button>
            ))
          : undefined
      }
    >
      {estado.ofrece || estado.origenAntes === "regla" || estado.origenAntes === "regla-borrada" ? (
        <p>{textos.texto}</p>
      ) : null}
      {estado.errorRegla ? (
        <p className="text-destructive font-fuerte" role="alert">
          {estado.errorRegla}
        </p>
      ) : null}
    </AvisoConTitulo>
  );
}
