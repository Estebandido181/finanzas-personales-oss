/** Listas y estados de presentación de la funcionalidad. */
import { type EstadoDeshacer } from "@/compartido/deshacer/usar";
import { nombreMes } from "@/compartido/formatos/formato";
import { TEXTOS } from "@/compartido/textos/textos";
import { AvisoDeshacer } from "@/compartido/ui/aviso-deshacer";
import { MarcaNeutra, Monto, NombreCifra } from "@/compartido/ui/cifras";
import { Ayuda, Hoja, Vacio } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { cn } from "@/compartido/ui/utils";
import { metaFila, montoConSigno, textoCantidadAjustes, textosListaVacia, tituloLista, type Saldo as DatosSaldo, type FilaDelMes } from "@/funcionalidades/saldo/datos";
import { HandCoins, Scale, Trash2 } from "lucide-react";
import { useId } from "react";
import { CabezaHoja, COLOR_MONTO } from "./piezas";

const T = TEXTOS.saldo;


// --- Ingresos y ajustes del mes ------------------------------------------------------

export function HojaDelMes({
  datos,
  aviso,
  alDeshacer,
  alPausar,
  alReanudar,
  borrandoId,
  alBorrar,
}: {
  datos: DatosSaldo;
  /** El aviso de lo que se borró, con «Deshacer» mientras dure. */
  aviso: EstadoDeshacer | null;
  alDeshacer: () => void;
  alPausar: () => void;
  alReanudar: () => void;
  borrandoId: number | null;
  alBorrar: (fila: FilaDelMes) => void;
}) {
  const id = useId();
  const filas = datos.del_mes;
  const ajustes = datos.ajustes_del_mes ?? { total_centavos: 0, cantidad: 0 };
  const total = montoConSigno(ajustes.total_centavos);
  const cantidad = textoCantidadAjustes(ajustes.cantidad);
  // `nombre_mes` de la API trae el año ("septiembre de 2026"); en la frase va solo el mes.
  const mes = nombreMes(datos.mes);
  const vacia = textosListaVacia(mes);
  return (
    <Hoja aria-labelledby={id}>
      <CabezaHoja id={id} titulo={tituloLista(mes)} />
      <AvisoDeshacer
        estado={aviso}
        alDeshacer={alDeshacer}
        alPausar={alPausar}
        alReanudar={alReanudar}
        className="mb-(--espacio-grupo)"
      />
      {filas.length === 0 ? (
        <Vacio icono={HandCoins} titulo={vacia.titulo}>
          <p>{vacia.texto}</p>
        </Vacio>
      ) : (
        <>
          <div className="flex flex-col gap-(--espacio-texto)">
            <NombreCifra>{T.totalAjustes}</NombreCifra>
            <p>
              <Monto className={cn("text-xl font-fuerte", COLOR_MONTO[total.clase])}>{total.texto}</Monto>
              {cantidad ? <span className="text-muted-foreground text-sm"> {cantidad}</span> : null}
            </p>
          </div>
          <ul aria-labelledby={id} className="mt-(--espacio-grupo)">
            {filas.map((fila) => (
              <Fila
                key={`${fila.tipo}-${fila.id}`}
                fila={fila}
                hoy={datos.hoy}
                borrando={borrandoId === fila.id}
                alBorrar={alBorrar}
              />
            ))}
          </ul>
          <Ayuda className="mt-(--espacio-grupo)">{T.notaBorrar}</Ayuda>
        </>
      )}
    </Hoja>
  );
}


function Fila({
  fila,
  hoy,
  borrando,
  alBorrar,
}: {
  fila: FilaDelMes;
  hoy: string;
  borrando: boolean;
  alBorrar: (fila: FilaDelMes) => void;
}) {
  const monto = montoConSigno(fila.monto_centavos);
  return (
    <li
      className={cn(
        "grid grid-cols-[auto_minmax(0,1fr)_auto] gap-x-3 items-start py-(--espacio-fila) first:pt-0 last:pb-0",
        "[grid-template-areas:'marca_desc_monto'_'marca_meta_meta'_'marca_accion_accion'] not-first:border-t not-first:border-renglon",
      )}
    >
      <MarcaNeutra icono={fila.tipo === "ingreso" ? HandCoins : Scale} className="[grid-area:marca] mt-0.5" />
      <p className="[grid-area:desc] font-medio [overflow-wrap:anywhere]">{fila.descripcion}</p>
      <p className="[grid-area:meta] text-muted-foreground text-sm">{metaFila(fila, hoy)}</p>
      <p className="[grid-area:monto] text-right">
        <Monto className={COLOR_MONTO[monto.clase]}>{monto.texto}</Monto>
      </p>
      {/* Solo donde la API lo permite: el frontend no decide qué se puede borrar. */}
      {fila.tipo === "ingreso" && fila.se_puede_borrar ? (
        <div className="[grid-area:accion] flex justify-end mt-1">
          <Button
            type="button"
            variant="ghost"
            className="-mr-3 text-destructive"
            disabled={borrando}
            onClick={() => alBorrar(fila)}
          >
            <Trash2 aria-hidden="true" className="size-5" />
            <span aria-hidden="true">{borrando ? T.borrando : T.borrar}</span>
            <span className="sr-only">{`${T.borrar} ${fila.descripcion}`}</span>
          </Button>
        </div>
      ) : null}
    </li>
  );
}
