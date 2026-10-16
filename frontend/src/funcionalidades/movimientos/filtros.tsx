/** Navegación por mes y selección de filtros. */
import { mesSiguienteVisible } from "@/compartido/formatos/mes";
import { Segmentos } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { Etiqueta } from "@/compartido/ui/ui/input";
import { Selector } from "@/compartido/ui/ui/selector";
import { ChevronLeft, ChevronRight, CircleDashed } from "lucide-react";
import { useId } from "react";
import { Link, useLocation } from "wouter";
import { mesActualColombia, nombreMesCorto, tituloMes } from "@/compartido/formatos/formato";
import { segmentoSinCategorizar, TEXTOS } from "@/compartido/textos/textos";
import { type DatosDelMes } from "@/funcionalidades/movimientos/cargar";
import { conCategoria, conVista, rutaMovimientos, type Categoria, type Filtros, type Vista } from "@/funcionalidades/movimientos/datos";

const T = TEXTOS.movimientos;


/** "‹ Agosto  Septiembre de 2026" (y "Octubre ›" en un mes pasado). Conserva los filtros. */
export function SelectorMes({ reporte, filtros }: { reporte: DatosDelMes["reporte"]; filtros: Filtros }) {
  const siguiente = mesSiguienteVisible(reporte, mesActualColombia());
  const anterior = reporte.mes_anterior;
  return (
    <nav aria-label={TEXTOS.inicio.cambiarDeMes} className="flex flex-wrap items-center gap-2">
      {anterior ? (
        <Button asChild variant="ghost" className="-ml-3">
          <Link href={rutaMovimientos(anterior, filtros)} rel="prev">
            <ChevronLeft aria-hidden="true" className="size-5" />
            {nombreMesCorto(anterior)}
          </Link>
        </Button>
      ) : null}
      <span className="font-fuerte">{tituloMes(reporte.mes)}</span>
      {siguiente ? (
        <Button asChild variant="ghost">
          <Link href={rutaMovimientos(siguiente, filtros)} rel="next">
            {nombreMesCorto(siguiente)}
            <ChevronRight aria-hidden="true" className="size-5" />
          </Link>
        </Button>
      ) : null}
    </nav>
  );
}


export function PanelFiltros({
  filtros,
  mes,
  categorias,
  pendientes,
}: {
  filtros: Filtros;
  mes: string | null;
  categorias: Categoria[];
  pendientes: number;
}) {
  const [, navegar] = useLocation();
  const idCategoria = useId();
  const opciones: { valor: Vista; texto: string; icono?: typeof CircleDashed }[] = [
    { valor: "todos", texto: T.todos },
    { valor: "gastos", texto: T.gastos },
    { valor: "ingresos", texto: T.ingresos },
    { valor: "sin-categorizar", texto: segmentoSinCategorizar(pendientes), icono: CircleDashed },
    { valor: "descartados", texto: "Descartados" },
  ];
  return (
    <section aria-label={T.filtros} className="flex flex-col gap-4">
      <Segmentos
        opciones={opciones}
        valor={filtros.vista}
        alElegir={(vista) => navegar(rutaMovimientos(mes, conVista(filtros, vista)))}
        nombre={T.mostrar}
        enFila
      />
      <div className="flex flex-col gap-(--espacio-texto) max-w-80">
        <Etiqueta htmlFor={idCategoria}>{T.categoria}</Etiqueta>
        <Selector
          id={idCategoria}
          value={filtros.categoria === null ? "" : String(filtros.categoria)}
          onChange={(e) => {
            const valor = e.target.value === "" ? null : Number(e.target.value);
            navegar(rutaMovimientos(mes, conCategoria(filtros, valor)));
          }}
        >
          <option value="">{T.todasLasCategorias}</option>
          {/* Ítem 15: también las de ingreso, en su grupo. */}
          {(["gasto", "ingreso"] as const).map((clase) => (
            <optgroup key={clase} label={clase === "gasto" ? T.categoriasDeGasto : T.categoriasDeIngreso}>
              {categorias
                .filter((c) => c.clase === clase)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.nombre}
                  </option>
                ))}
            </optgroup>
          ))}
        </Selector>
      </div>
    </section>
  );
}
