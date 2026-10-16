/** Hojas de categorías y reglas. */
import { TEXTOS } from "@/compartido/textos/textos";
import { ChipCategoria, ConMonto, MarcaCategoria } from "@/compartido/ui/cifras";
import { Ayuda, Hoja, Vacio } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { partesFrase, textoUso, type CategoriaConUso, type Clase, type Regla } from "@/funcionalidades/categorias/datos";
import { Pencil, Tags, Trash2 } from "lucide-react";
import { useId } from "react";
import { Link } from "wouter";
import { CabezaHoja } from "./piezas";

const T = TEXTOS.categorias;


export function HojaCategorias({
  clase,
  categorias,
  alEditar,
}: {
  clase: Clase;
  categorias: CategoriaConUso[];
  alEditar: (categoria: CategoriaConUso) => void;
}) {
  const id = useId();
  const titulo = clase === "gasto" ? T.deGasto : T.deIngreso;
  return (
    <Hoja aria-labelledby={id}>
      <CabezaHoja id={id} titulo={titulo} />
      <ul aria-labelledby={id}>
        {categorias.map((c) => (
          <li
            key={c.id}
            className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 py-(--espacio-fila) first:pt-0 last:pb-0 not-first:border-t not-first:border-renglon"
          >
            <span className="flex items-center gap-3 min-w-0">
              <MarcaCategoria categoria={c} />
              <span className="min-w-0">
                <span className="block font-medio [overflow-wrap:anywhere]">{c.nombre}</span>
                <span className="block text-muted-foreground text-sm">{textoUso(c.movimientos_mes)}</span>
              </span>
            </span>
            <Button type="button" variant="ghost" className="-mr-3" onClick={() => alEditar(c)}>
              <Pencil aria-hidden="true" className="size-5" />
              {/* Se lee "Editar Mercado" (TEXTOS.md: las acciones de fila llevan el objeto). */}
              <span aria-hidden="true">{T.editar}</span>
              <span className="sr-only">{`${T.editar} ${c.nombre}`}</span>
            </Button>
          </li>
        ))}
      </ul>
    </Hoja>
  );
}


export function HojaReglas({
  reglas,
  borrandoId,
  alBorrar,
}: {
  reglas: Regla[];
  borrandoId: number | null;
  alBorrar: (regla: Regla) => void;
}) {
  const id = useId();
  return (
    <Hoja aria-labelledby={id}>
      <CabezaHoja id={id} titulo={T.reglas}>
        <Ayuda>{T.ayudaReglas}</Ayuda>
      </CabezaHoja>
      {reglas.length === 0 ? (
        <SinReglas />
      ) : (
        <ul aria-labelledby={id}>
          {reglas.map((r) => (
            <li
              key={r.id}
              className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 py-(--espacio-fila) first:pt-0 last:pb-0 not-first:border-t not-first:border-renglon"
            >
              <p className="[overflow-wrap:anywhere]">
                <FraseRegla regla={r} />
              </p>
              <Button
                type="button"
                variant="ghost"
                className="-mr-3 text-destructive"
                disabled={borrandoId === r.id}
                onClick={() => alBorrar(r)}
              >
                <Trash2 aria-hidden="true" className="size-5" />
                <span aria-hidden="true">{borrandoId === r.id ? T.borrando : T.borrar}</span>
                <span className="sr-only">{T.borrarRegla}</span>
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Hoja>
  );
}


/** "Si es una **compra** en «x», va a [Mercado]" (la frase de la API, con el chip). */
function FraseRegla({ regla }: { regla: Regla }) {
  const partes = partesFrase(regla);
  if (!partes.chip) return <ConMonto texto={partes.frase} montoCentavos={regla.monto_centavos} />;
  return (
    <>
      {partes.antes}
      <strong className="font-fuerte">{partes.tipo}</strong>
      {/* Ítem 17: "de $3.200", "por $400.000": el monto, en la letra de los montos. */}
      <ConMonto texto={partes.resto} montoCentavos={regla.monto_centavos} />
      {T.vaA}{" "}
      <ChipCategoria
        nombre={regla.categoria.nombre}
        categoria={regla.categoria}
        className="align-middle font-fuerte [&>span:last-child]:whitespace-normal"
      />
    </>
  );
}


function SinReglas() {
  const t = T.sinReglas;
  const id = useId();
  return (
    <Vacio
      icono={Tags}
      titulo={t.titulo}
      idTitulo={id}
      accion={
        <Button asChild variant="outline">
          <Link href="/movimientos">{t.boton}</Link>
        </Button>
      }
    >
      <p>{t.texto}</p>
    </Vacio>
  );
}
