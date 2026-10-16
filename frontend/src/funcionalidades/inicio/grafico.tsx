/**
 * "¿En qué se fue?" (SISTEMA.md, "Gráfico"): gasto por categoría en barras
 * (por defecto) o en dona, con la MISMA lista en las dos vistas. El dibujo es
 * decorativo para el lector de pantalla; la información está en la lista.
 *
 * Todo con SVG y clases propias, sin librería de gráficos: la CSP no permite
 * estilos en línea. El largo de cada barra es una clase `w-[N%]` (N entero de
 * 0 a 100, generadas en estilos.css) y las tajadas de la dona son `path` con
 * el `d` calculado en datos.ts.
 */
import { ChartBarDecreasing, ChartPie } from "lucide-react";
import { useId } from "react";
import { Link } from "wouter";
import { Hoja, Segmentos, Vacio } from "@/compartido/ui/libreta";
import { cn } from "@/compartido/ui/utils";
import { useVistaGrafico, type VistaGrafico } from "@/compartido/tema/grafico";
import { TEXTOS } from "@/compartido/textos/textos";
import { estiloCategoria } from "@/compartido/ui/categorias";
import { anchoBarra, esSinCategorizar, tajadasDona, type GastoCategoria } from "@/funcionalidades/inicio/datos";

import { pesos, porcentaje } from "@/compartido/formatos/formato";
import { ChipCategoria, Monto, NombreCifra, SubrayadoDoble } from "@/compartido/ui/cifras";

const OPCIONES_VISTA: readonly { valor: VistaGrafico; texto: string; icono: typeof ChartPie }[] = [
  { valor: "barras", texto: TEXTOS.inicio.barras, icono: ChartBarDecreasing },
  { valor: "dona", texto: TEXTOS.inicio.dona, icono: ChartPie },
];

/**
 * Clases de ancho de las barras, escritas enteras para que Tailwind las
 * genere (ver `@source inline` en estilos.css): 0 %, 1 %, …, 100 %.
 */
export function claseAncho(porcentajeEntero: number): string {
  return `w-[${porcentajeEntero}%]`;
}

export function EnQueSeFue({
  categorias,
  totalCentavos,
  nombreMes,
}: {
  categorias: readonly GastoCategoria[];
  totalCentavos: number;
  /** "septiembre" */
  nombreMes: string;
}) {
  const [vista, elegirVista] = useVistaGrafico();
  const idTitulo = useId();
  const idVerComo = useId();
  const dona = vista === "dona";
  const mayor = categorias.reduce((m, c) => Math.max(m, c.centavos), 0);

  return (
    <Hoja aria-labelledby={idTitulo}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-2 mb-(--espacio-cabeza-hoja) pb-3 border-b-[3px] border-double border-regla">
        <h2 id={idTitulo}>{TEXTOS.inicio.enQueSeFue}</h2>
        <Link href="/movimientos" className="inline-flex items-center min-h-(--tactil-min) text-sm font-medio underline">
          {TEXTOS.inicio.verMovimientos}
        </Link>
      </div>

      {categorias.length === 0 ? (
        <Vacio icono={ChartBarDecreasing}>
          <p className="font-fuerte">No hay gastos en {nombreMes}.</p>
        </Vacio>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 mb-(--espacio-cabeza-hoja)">
            <span id={idVerComo} className="text-muted-foreground text-sm font-medio">
              {TEXTOS.inicio.verComo}
            </span>
            <Segmentos
              opciones={OPCIONES_VISTA}
              valor={vista}
              alElegir={elegirVista}
              idEtiqueta={idVerComo}
              enFila
            />
          </div>

          {dona ? <Dona categorias={categorias} totalCentavos={totalCentavos} /> : null}

          <ul aria-label={`Gasto por categoría en ${nombreMes}`}>
            {categorias.map((c) => (
              <FilaCategoria
                key={c.nombre}
                categoria={c}
                ancho={anchoBarra(c.centavos, mayor)}
                dona={dona}
              />
            ))}
          </ul>
          <div className="flex justify-between items-baseline gap-3 pt-3 mt-2 border-t border-border font-fuerte">
            <span>{TEXTOS.inicio.totalGastado}</span>
            <SubrayadoDoble>
              <Monto>{pesos(totalCentavos)}</Monto>
            </SubrayadoDoble>
          </div>
        </>
      )}
    </Hoja>
  );
}

function FilaCategoria({
  categoria: { nombre, centavos, porcentaje: pct, categoria },
  ancho,
  dona,
}: {
  categoria: GastoCategoria;
  ancho: number;
  dona: boolean;
}) {
  const vacia = esSinCategorizar(nombre);
  return (
    <li
      className={cn(
        "grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 items-center py-(--espacio-fila-grafico)",
        "[grid-template-areas:'nombre_monto'_'pista_pista'] not-first:border-t not-first:border-renglon",
        dona
          ? "computador:grid-cols-[minmax(0,1fr)_4.5rem_minmax(8.5rem,auto)]"
          : "computador:grid-cols-[11.5rem_minmax(0,1fr)_auto]",
        "computador:[grid-template-areas:'nombre_pista_monto']",
      )}
    >
      <ChipCategoria nombre={nombre} categoria={categoria} className="[grid-area:nombre]" />
      <Monto className="[grid-area:monto] text-right">{pesos(centavos)}</Monto>
      <span
        className={cn(
          "[grid-area:pista] flex items-center gap-2",
          dona && "pl-[calc(24px+var(--espacio-2))] computador:pl-0 computador:justify-end",
        )}
      >
        {dona ? null : (
          <span
            aria-hidden="true"
            className={cn(
              "h-2.5 min-w-[2px] rounded-r-barra",
              claseAncho(ancho),
              estiloCategoria(categoria).color,
              vacia
                ? "bg-transparent border-[1.5px] border-dashed border-(--cat-sin-categorizar)"
                : "bg-(--c)",
            )}
          />
        )}
        <span className="text-muted-foreground text-sm min-w-[4ch] whitespace-nowrap">
          {porcentaje(pct)}
        </span>
      </span>
    </li>
  );
}

function Dona({
  categorias,
  totalCentavos,
}: {
  categorias: readonly GastoCategoria[];
  totalCentavos: number;
}) {
  return (
    <div className="relative w-[min(15rem,100%)] mx-auto mt-2 mb-6">
      <svg
        viewBox="-120 -120 240 240"
        aria-hidden="true"
        focusable="false"
        className="block w-full h-auto overflow-visible"
      >
        {tajadasDona(categorias).map(({ nombre, categoria, d }) => (
          <path
            key={nombre}
            d={d}
            data-categoria={nombre}
            className={cn(
              estiloCategoria(categoria).color,
              categoria === null
                ? "fill-none stroke-(--cat-sin-categorizar) stroke-[1.5] [stroke-dasharray:4_3]"
                : "fill-(--c) stroke-card stroke-2 [stroke-linejoin:round]",
            )}
          />
        ))}
      </svg>
      <div aria-hidden="true" className="absolute inset-0 grid place-content-center text-center gap-1">
        <NombreCifra>{TEXTOS.inicio.totalGastado}</NombreCifra>
        <Monto className="text-lg font-fuerte">{pesos(totalCentavos)}</Monto>
      </div>
    </div>
  );
}
