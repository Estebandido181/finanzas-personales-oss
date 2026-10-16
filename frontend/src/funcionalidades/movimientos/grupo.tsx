/**
 * Un grupo de movimientos iguales (ítem 38): "COBRO VIAJE TRANSPORTE MASIVO ·
 * 20 veces", que se categoriza con un toque y guarda su regla. Reutilizable:
 * solo sabe del grupo (lo arma el servidor) y de qué hacer al elegir la
 * categoría (`alCategorizar`); el ítem 30 lo usa igual para lo importado.
 *
 * Mientras se muestra, el grupo conserva su resultado ("20 movimientos
 * categorizados en Transporte. Regla creada: …") aunque el servidor ya no lo
 * devuelva; quien lo usa lo sigue dibujando hasta que se cambie de pantalla.
 */
import { Check, CircleDashed, Repeat } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Aviso, AvisoConTitulo, Segmentos } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { pesos, fechaEnFrase, hoyColombia } from "@/compartido/formatos/formato";
import { MarcaCategoria, MarcaNeutra, Monto } from "@/compartido/ui/cifras";
import { cn } from "@/compartido/ui/utils";
import {
  botonCategorizarGrupo,
  preguntaGrupo,
  vecesDelGrupo,
  grupoCategorizado,
  TEXTOS,
} from "@/compartido/textos/textos";
import type { Esquemas } from "@/compartido/http/cliente";
import type { ResultadoCategorizarGrupo } from "@/funcionalidades/movimientos/cargar";
import {
  categoriasDeGrupo,
  nombreTipo,
  textoGrupoCategorizado,
  textoReglaDelGrupo,
  type Categoria,
  type GrupoPendientes,
} from "@/funcionalidades/movimientos/datos";
import { Opciones } from "@/funcionalidades/movimientos/opciones";

type Fase =
  | { tipo: "cerrado" }
  | { tipo: "abierto"; error?: string }
  | { tipo: "guardando" }
  | {
      tipo: "listo";
      categoria: Categoria;
      titulo: string;
      regla: string | null;
    };

function esGrupoBanco(grupo: GrupoPendientes | Esquemas["GrupoImportacion"]): grupo is Esquemas["GrupoImportacion"] {
  return "reglas_propuestas" in grupo;
}

export function GrupoCategorizable<
  T extends GrupoPendientes | Esquemas["GrupoImportacion"],
>({
  grupo,
  categorias,
  alCategorizar,
  alTerminar,
  inicialmenteAbierto = false,
}: {
  grupo: T;
  inicialmenteAbierto?: boolean;
  /** Todas las categorías; el grupo ofrece solo las de su clase. */
  categorias: Categoria[];
  /** Hace la llamada (`categorizarGrupo`) y devuelve lo que respondió el servidor. */
  alCategorizar: (
    grupo: T,
    categoria: Categoria,
    modo?: Esquemas["CategorizarGrupoEntrada"]["modo_regla"],
  ) => Promise<ResultadoCategorizarGrupo>;
  /** Ya categorizado: quien lo muestra puede recargar la lista. */
  alTerminar?: (grupo: T) => void;
}) {
  const banco = esGrupoBanco(grupo) ? grupo : null;
  const propuestas = banco?.reglas_propuestas ?? [];
  const [modo, setModo] = useState<
    Esquemas["CategorizarGrupoEntrada"]["modo_regla"]
  >(propuestas[0]?.modo ?? "exacta");
  const [fase, setFase] = useState<Fase>({
    tipo: inicialmenteAbierto ? "abierto" : "cerrado",
  });
  const idResultado = useId();
  const aviso = useRef<HTMLElement>(null);
  useEffect(() => {
    // El botón que se tocó ya no está: el foco pasa al resultado.
    if (fase.tipo === "listo") aviso.current?.focus();
  }, [fase.tipo]);

  const elegir = async (categoria: Categoria) => {
    setFase({ tipo: "guardando" });
    const r = await alCategorizar(grupo, categoria, modo);
    if (r.tipo === "sin-sesion") return;
    if (r.tipo === "error") {
      setFase({ tipo: "abierto", error: r.texto });
      return;
    }
    const textos: { titulo: string; regla: string | null } = grupo.regla
      ? textoGrupoCategorizado(
          { ...grupo, regla: grupo.regla },
          categoria.nombre,
          r.datos,
        )
      : {
          titulo:
            r.datos.categorizados === 0
              ? TEXTOS.movimientos.grupos.yaNoHay
              : grupoCategorizado(r.datos.categorizados, categoria.nombre),
          regla: null,
        };
    if (propuestas.length && r.datos.regla_guardada && r.datos.regla)
      textos.regla = `Regla creada: ${r.datos.regla.frase} van a ${categoria.nombre}.`;
    setFase({ tipo: "listo", categoria, ...textos });
    alTerminar?.(grupo);
  };

  const listo = fase.tipo === "listo" ? fase : null;
  const abierto = fase.tipo === "abierto" || fase.tipo === "guardando";

  return (
    <li
      className={cn(
        "grid grid-cols-[auto_minmax(0,1fr)_auto] gap-x-3 items-start py-(--espacio-fila)",
        "[grid-template-areas:'marca_desc_monto'_'marca_meta_meta'_'marca_accion_accion'_'panel_panel_panel']",
        "not-first:border-t not-first:border-renglon",
        listo
          ? "last:pb-0"
          : "bg-aviso-advertencia -mx-(--espacio-hoja) px-(--espacio-hoja)",
      )}
    >
      {listo ? (
        <MarcaCategoria
          categoria={listo.categoria}
          className="[grid-area:marca] mt-0.5"
        />
      ) : (
        <MarcaNeutra
          icono={banco ? CircleDashed : Repeat}
          className="[grid-area:marca] mt-0.5"
        />
      )}
      <p className="[grid-area:desc] font-medio [overflow-wrap:anywhere]">
        {grupo.descripcion}
      </p>
      <p className="[grid-area:meta] text-muted-foreground text-sm">
        {banco ? (
          <>
            Apareció {vecesDelGrupo(grupo.cuantos)}
            {banco.desde !== banco.hasta
              ? ` entre el ${fechaEnFrase(banco.desde, hoyColombia())} y el ${fechaEnFrase(banco.hasta, hoyColombia())}`
              : ""}
            . {grupo.cuantos === 1 ? "Suma" : "Suman"}{" "}
            <Monto>
              {pesos(grupo.suma_centavos, { conSigno: !grupo.es_gasto })}
            </Monto>
            . ¿Qué es?
          </>
        ) : (
          <>
            {nombreTipo(grupo.tipo)} · {vecesDelGrupo(grupo.cuantos)}
          </>
        )}
      </p>
      {!banco ? (
        <p className="[grid-area:monto] text-right">
          {/* Un grupo es todo de gastos o todo de ingresos (lo garantiza el servidor). */}
          <Monto className={cn(!grupo.es_gasto && "text-monto-positivo")}>
            {pesos(grupo.suma_centavos, { conSigno: !grupo.es_gasto })}
          </Monto>
        </p>
      ) : null}
      {fase.tipo === "cerrado" ? (
        <div className="[grid-area:accion] flex justify-end self-center mt-1">
          <Button
            type="button"
            variant="outline"
            onClick={() => setFase({ tipo: "abierto" })}
          >
            {/* Se lee "Categorizar las 20 COBRO VIAJE…" (TEXTOS.md: las acciones de fila llevan el objeto). */}
            <span aria-hidden="true">
              {botonCategorizarGrupo(grupo.cuantos)}
            </span>
            <span className="sr-only">{`${botonCategorizarGrupo(grupo.cuantos)} de ${grupo.descripcion}`}</span>
          </Button>
        </div>
      ) : null}
      {abierto || listo ? (
        <div className="[grid-area:panel] mt-4 flex flex-col gap-4">
          {fase.tipo === "abierto" && fase.error ? (
            <Aviso tipo="error">{fase.error}</Aviso>
          ) : null}
          {abierto ? (
            <>
              {propuestas.length ? (
                <>
                  <p className="text-muted-foreground text-sm">
                    Elige cómo categorizar las siguientes descripciones del
                    banco.
                  </p>
                  <fieldset disabled={fase.tipo === "guardando"}>
                    <Segmentos
                      nombre="Regla para las siguientes importaciones"
                      opciones={propuestas.map((p) => ({
                        valor: p.modo,
                        texto: p.frase,
                      }))}
                      valor={modo}
                      alElegir={setModo}
                      enFila
                    />
                  </fieldset>
                </>
              ) : grupo.regla ? (
                <p className="text-muted-foreground text-sm">
                  {textoReglaDelGrupo({ ...grupo, regla: grupo.regla })}
                </p>
              ) : null}
              <Opciones
                categorias={categoriasDeGrupo(grupo, categorias)}
                actual={null}
                ocupada={fase.tipo === "guardando"}
                alElegir={(c) => void elegir(c)}
                alCancelar={() => setFase({ tipo: "cerrado" })}
                pregunta={preguntaGrupo(banco ? 1 : grupo.cuantos)}
              />
            </>
          ) : listo ? (
            <AvisoConTitulo
              ref={aviso}
              tabIndex={-1}
              className="focus:outline-none"
              tipo="exito"
              icono={Check}
              titulo={listo.titulo}
              idTitulo={idResultado}
              resultado
            >
              {listo.regla ? <p>{listo.regla}</p> : null}
            </AvisoConTitulo>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
