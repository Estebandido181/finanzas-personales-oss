/** Listas y estados de presentación de la funcionalidad. */
import { type Esquemas } from "@/compartido/http/cliente";
import { Ayuda, Hoja, Vacio } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { useSincronizar } from "@/funcionalidades/sincronizacion/sincronizar";
import { Check, CircleDashed, RefreshCw } from "lucide-react";
import { useId, useState, type ComponentProps, type ReactNode } from "react";
import { Link } from "wouter";
import { fechaYHora, hoyColombia, nombreMes, pesos } from "@/compartido/formatos/formato";
import { listaDias, TEXTOS, textosMesVacio } from "@/compartido/textos/textos";
import { Monto } from "@/compartido/ui/cifras";
import { categorizar, categorizarGrupo, type DatosMovimientos } from "@/funcionalidades/movimientos/cargar";
import { agruparPorDia, filasBandeja, filasVisibles, ofrecerRegla, opcionesPara, ordenarGrupos, origenDe, rutaMovimientos, SIN_FILTROS, sinGrupo, textoReglaCreada, textosVacio, type Categoria, type Dia, type GrupoPendientes, type Movimiento, type OfertaRegla } from "@/funcionalidades/movimientos/datos";
import { GrupoCategorizable } from "@/funcionalidades/movimientos/grupo";
import { useSesion } from "@/funcionalidades/sesion/sesion";
import { FilaMovimiento, type EstadoFila } from "./fila";

const T = TEXTOS.movimientos;


export function ListaDescartados({ datos, ocupada, alRestaurar }: {
  datos: Esquemas["MovimientoDescartado"][];
  ocupada: boolean;
  alRestaurar: (movimiento: Esquemas["MovimientoDescartado"]) => void;
}) {
  if (datos.length === 0) return <Hoja><Vacio icono={CircleDashed} titulo="Sin movimientos descartados"><p>Los movimientos que descartes aparecerán aquí para que puedas restaurarlos.</p></Vacio></Hoja>;
  return <Hoja><h2>Descartados</h2><Ayuda>No están incluidos en el saldo. Restaurar recupera el monto actual que ves aquí.</Ayuda>
    <ul aria-label="Movimientos descartados" aria-busy={ocupada} className="mt-4">
      {datos.map((m) => <li key={m.id} className="py-(--espacio-fila) not-first:border-t not-first:border-renglon">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><p className="font-fuerte [overflow-wrap:anywhere]">{m.descripcion}</p><Ayuda>{fechaYHora(m.fecha_hora, hoyColombia())}</Ayuda></div>
          <Monto>{pesos(m.monto_centavos)}</Monto>
        </div>
        {m.motivo_no_restaurar ? <Ayuda className="mt-3">{m.motivo_no_restaurar}</Ayuda> : null}
        <Button type="button" className="mt-3" variant="outline" disabled={ocupada || !m.puede_restaurar}
          aria-label={`Restaurar ${m.descripcion}`} onClick={() => alRestaurar(m)}>Restaurar</Button>
      </li>)}
    </ul>
  </Hoja>;
}


export function Lista({
  datos,
  actualizando,
  mes,
  recargar,
  sincronizacion,
  alRevisar,
  alOcupar,
}: {
  datos: Exclude<DatosMovimientos, { tipo: "descartados" }>;
  actualizando: boolean;
  mes: string | null;
  recargar: (silencioso?: boolean) => Promise<void>;
  sincronizacion: ReturnType<typeof useSincronizar>;
  alRevisar: (movimiento: Movimiento) => void;
  alOcupar: (ocupada: boolean) => void;
}) {
  const { cliente } = useSesion();
  const [estados, setEstados] = useState<ReadonlyMap<number, EstadoFila>>(new Map());
  const [retenidas, setRetenidas] = useState<ReadonlyMap<number, Movimiento>>(new Map());
  const [abiertas, setAbiertas] = useState<ReadonlySet<number>>(new Set());
  const [enCurso, setEnCurso] = useState<number | null>(null);
  // Ítem 38 (solo la bandeja): los grupos que se ven y los que se acaban de
  // categorizar aquí (el servidor ya no los devuelve, pero su resultado sigue a la vista).
  const [gruposHechos, setGruposHechos] = useState<ReadonlyMap<string, GrupoPendientes>>(new Map());
  const [clavesVistas] = useState(() => (datos.tipo === "bandeja" ? datos.grupos.map((g) => g.clave) : []));

  const ponerEstado = (id: number, estado: EstadoFila | null) =>
    setEstados((antes) => {
      const nuevo = new Map(antes);
      if (estado) nuevo.set(id, estado);
      else nuevo.delete(id);
      return nuevo;
    });
  const cambiarAbierta = (id: number, abierta: boolean) =>
    setAbiertas((antes) => {
      const nuevo = new Set(antes);
      if (abierta) nuevo.add(id);
      else nuevo.delete(id);
      return nuevo;
    });

  const elegir = async (m: Movimiento, categoria: Categoria) => {
    const origenAntes = origenDe(m).tipo;
    setEnCurso(m.id);
    alOcupar(true);
    const r = await categorizar(cliente, m.id, categoria.id, false);
    setEnCurso(null);
    alOcupar(false);
    if (r.tipo === "sin-sesion") return;
    if (r.tipo === "error") {
      ponerEstado(m.id, { fase: "error", texto: r.texto });
      return;
    }
    setRetenidas((antes) => new Map(antes).set(m.id, m));
    cambiarAbierta(m.id, false);
    ponerEstado(m.id, { fase: "guardado", categoria, origenAntes, ofrece: ofrecerRegla(m, origenAntes) });
    await recargar(true);
  };

  const crearRegla = async (
    m: Movimiento,
    estado: Extract<EstadoFila, { fase: "guardado" }>,
    oferta: OfertaRegla,
  ) => {
    setEnCurso(m.id);
    alOcupar(true);
    const r = await categorizar(cliente, m.id, estado.categoria.id, true, oferta.condiciones);
    setEnCurso(null);
    alOcupar(false);
    if (r.tipo === "sin-sesion") return;
    if (r.tipo === "error") {
      ponerEstado(m.id, { ...estado, errorRegla: r.texto });
      return;
    }
    ponerEstado(m.id, {
      fase: "regla",
      categoria: estado.categoria,
      texto: textoReglaCreada(m, estado.categoria.nombre, oferta),
      montoCentavos: oferta.montoCentavos,
    });
    await recargar(true);
  };

  const hoy = hoyColombia();
  const bandeja = datos.tipo === "bandeja";
  const mesNombre = datos.tipo === "mes" ? nombreMes(datos.reporte.mes) : null;
  // Los pendientes iguales van en grupos (los arma el servidor); los sueltos siguen como hoy.
  const gruposVisibles =
    datos.tipo === "bandeja"
      ? ordenarGrupos(
          [...datos.grupos, ...[...gruposHechos.values()].filter((h) => !datos.grupos.some((g) => g.clave === h.clave))],
          clavesVistas,
        )
      : [];
  const visibles =
    datos.tipo === "bandeja"
      ? filasBandeja(sinGrupo(datos.pendientes, datos.grupos), retenidas)
      : filasVisibles(datos.delMes, datos.filtradas, retenidas);
  // Fuera de la bandeja, el primer pendiente (sin resultado) ya tiene sus opciones abiertas.
  const sinResultado = (id: number) => (estados.get(id)?.fase ?? "error") === "error";
  const primerPendiente = visibles.find((m) => m.pendiente && sinResultado(m.id))?.id ?? null;
  // En la bandeja no hay "Gastado" por día: solo se ven los pendientes.
  const dias = agruparPorDia(visibles, datos.tipo === "mes" ? datos.delMes : null, hoy);

  if (dias.length === 0 && gruposVisibles.length === 0) {
    const nombreCategoria =
      datos.categorias.find((c) => c.id === datos.filtros.categoria)?.nombre ?? null;
    const vacio = textosVacio(datos.filtros, nombreCategoria, mesNombre ?? "");
    return vacio ? (
      <VacioConTitulo
        icono={datos.filtros.vista === "sin-categorizar" ? Check : CircleDashed}
        titulo={vacio.titulo}
        texto={vacio.texto}
        accion={
          vacio.verTodos ? (
            <Button asChild>
              <Link href={rutaMovimientos(mes, SIN_FILTROS)}>{T.verTodos}</Link>
            </Button>
          ) : undefined
        }
      />
    ) : datos.tipo === "mes" ? (
      <MesVacio
        mes={nombreMes(datos.reporte.mes)}
        esMesActual={datos.reporte.es_mes_actual}
        sincronizacion={sincronizacion}
      />
    ) : null;
  }

  return (
    <>
      {datos.tipo === "bandeja" && gruposVisibles.length > 0 ? (
        <HojaGrupos
          grupos={gruposVisibles}
          categorias={datos.categorias}
          alCategorizar={async (grupo, categoria) => {
            alOcupar(true);
            try { return await categorizarGrupo(cliente, grupo, categoria.id); }
            finally { alOcupar(false); }
          }}
          alTerminar={(grupo) => {
            setGruposHechos((antes) => new Map(antes).set(grupo.clave, grupo));
            void recargar(true);
          }}
        />
      ) : null}
      {dias.length > 0 ? (
        <ul
          aria-label={mesNombre === null ? T.listaBandeja : listaDias(mesNombre)}
          aria-busy={actualizando}
          className="flex flex-col gap-(--espacio-bloques)"
        >
          {dias.map((dia) => (
            <DiaHoja key={dia.fecha} dia={dia}>
              {dia.movimientos.map((m) => {
                const estado = estados.get(m.id) ?? null;
                const pendienteAbierta =
                  m.pendiente && sinResultado(m.id) && (bandeja || m.id === primerPendiente);
                return (
                  <FilaMovimiento
                    key={m.id}
                    movimiento={m}
                    categorias={opcionesPara(m, datos.categorias)}
                    estado={estado}
                    abierta={pendienteAbierta || abiertas.has(m.id)}
                    ocupada={enCurso === m.id}
                    alAbrir={() => {
                      ponerEstado(m.id, null);
                      cambiarAbierta(m.id, true);
                    }}
                    alCerrar={() => {
                      ponerEstado(m.id, null);
                      cambiarAbierta(m.id, false);
                    }}
                    alElegir={(c) => void elegir(m, c)}
                    alCrearRegla={(e, oferta) => void crearRegla(m, e, oferta)}
                    alDescartar={() => alRevisar(m)}
                  />
                );
              })}
            </DiaHoja>
          ))}
        </ul>
      ) : null}
    </>
  );
}


/** Ítem 38: los pendientes iguales, juntos, arriba de los sueltos. */
function HojaGrupos({
  grupos,
  categorias,
  alCategorizar,
  alTerminar,
}: {
  grupos: GrupoPendientes[];
  categorias: Categoria[];
  alCategorizar: ComponentProps<typeof GrupoCategorizable>["alCategorizar"];
  alTerminar: (grupo: GrupoPendientes) => void;
}) {
  const id = useId();
  return (
    <Hoja aria-labelledby={id}>
      <div className="flex flex-col gap-(--espacio-texto) mb-(--espacio-cabeza-hoja) pb-3 border-b-[3px] border-double border-regla">
        <h2 id={id}>{T.grupos.titulo}</h2>
        <Ayuda>{T.grupos.ayuda}</Ayuda>
      </div>
      <ul aria-label={T.grupos.lista}>
        {grupos.map((grupo) => (
          <GrupoCategorizable
            key={grupo.clave}
            grupo={grupo}
            categorias={categorias}
            alCategorizar={alCategorizar}
            alTerminar={alTerminar}
          />
        ))}
      </ul>
    </Hoja>
  );
}


function DiaHoja({ dia, children }: { dia: Dia; children: ReactNode }) {
  return (
    <li>
      <Hoja>
        {/* "Gastado" siempre a la derecha: si no cabe, se parte la fecha, nunca el monto. */}
        <h2 className="flex items-baseline justify-between gap-3 pb-3 border-b border-border font-texto text-base font-fuerte tracking-normal leading-(--interlineado-texto)">
          <span className="min-w-0">{dia.titulo}</span>
          {dia.gastadoCentavos !== null ? (
            <span className="flex-none text-muted-foreground text-sm whitespace-nowrap text-right">
              {T.gastado} <Monto>{pesos(dia.gastadoCentavos)}</Monto>
            </span>
          ) : null}
        </h2>
        <ul>{children}</ul>
      </Hoja>
    </li>
  );
}


function VacioConTitulo({
  icono,
  titulo,
  texto,
  accion,
}: {
  icono: typeof Check;
  titulo: string;
  texto: string;
  accion?: ReactNode;
}) {
  const id = useId();
  return (
    <Hoja aria-labelledby={id}>
      <Vacio icono={icono} titulo={titulo} idTitulo={id} accion={accion}>
        <p>{texto}</p>
      </Vacio>
    </Hoja>
  );
}


/** El mes no tiene movimientos (los mismos textos de Inicio). */
function MesVacio({
  mes,
  esMesActual,
  sincronizacion,
}: {
  mes: string;
  esMesActual: boolean;
  sincronizacion: ReturnType<typeof useSincronizar>;
}) {
  const t = textosMesVacio(mes, esMesActual);
  return (
    <VacioConTitulo
      icono={CircleDashed}
      titulo={t.titulo}
      texto={t.texto}
      accion={
        esMesActual ? (
          <Button
            type="button"
            disabled={sincronizacion.enCurso}
            onClick={() => void sincronizacion.sincronizar()}
          >
            <RefreshCw aria-hidden="true" className="size-5" />
            {sincronizacion.enCurso ? TEXTOS.inicio.sincronizando : TEXTOS.inicio.sincronizarAhora}
          </Button>
        ) : undefined
      }
    />
  );
}
