import {
  Check,
  CircleCheck,
  Landmark,
  Mail,
  Scale,
  Trash2,
} from "lucide-react";
import { useCallback, useState } from "react";
import { Aviso, Ayuda, Hoja, Nota, Vacio } from "@/compartido/ui/libreta";
import { AvisoDeshacer } from "@/compartido/ui/aviso-deshacer";
import { Button } from "@/compartido/ui/ui/button";
import { cabeceraCsrf, type Esquemas } from "@/compartido/http/cliente";
import { fechaEnFrase, fechaYHora, hoyColombia, pesos } from "@/compartido/formatos/formato";
import { MarcaNeutra, Monto } from "@/compartido/ui/cifras";
import { Pila, useVisibleTras } from "@/compartido/ui/pantalla";
import { useSesion } from "@/funcionalidades/sesion/sesion";
import { CabeceraImportacion } from "@/funcionalidades/importaciones/piezas";
import { dato, textoFalla } from "@/compartido/http/dato";
import { useCarga } from "@/compartido/http/carga";
import { useDeshacerConciliacion } from "@/funcionalidades/importaciones/deshacer";
import { ComprobarSaldo } from "@/funcionalidades/saldo/comprobar";

type Dato = Esquemas["DatoConciliacion"];
type Sugerencia = Esquemas["SugerenciaConciliacion"];
function FilaDato({
  datos,
}: {
  datos: Dato;
}) {
  const fecha =
    datos.origen === "extracto"
      ? fechaEnFrase(datos.fecha_hora, hoyColombia())
      : fechaYHora(datos.fecha_hora, hoyColombia());
  return (
    <li className="grid grid-cols-[auto_minmax(0,1fr)_auto] gap-3 py-(--espacio-fila) not-first:border-t not-first:border-renglon">
      <MarcaNeutra
        icono={
          datos.origen === "extracto" ? Landmark : datos.origen === "manual" ? Scale : Mail
        }
      />
      <div>
        <p className="font-medio [overflow-wrap:anywhere]">
          {datos.etiqueta ? <span>{datos.etiqueta} · </span> : null}
          {datos.descripcion}
        </p>
        {datos.descartado ? <p className="font-fuerte">Descartado</p> : null}
        {datos.nota_descartado ? <Ayuda>{datos.nota_descartado}</Ayuda> : null}
        <p className="text-sm text-muted-foreground">
          {datos.origen === "extracto"
            ? "Del banco"
            : datos.origen === "manual"
              ? "A mano"
              : "Del correo"}{" "}
          · {fecha}
          {datos.destino_ultimos4 ? ` · ${datos.destino_ultimos4}` : ""}
        </p>
      </div>
      <Monto
        className={
          datos.tipo === "ingreso" || (datos.tipo === "ajuste" && datos.monto_centavos > 0)
            ? "text-monto-positivo"
            : datos.tipo === "ajuste" && datos.monto_centavos < 0
              ? "text-monto-negativo"
              : undefined
        }
      >
        {pesos(datos.monto_centavos, {
          conSigno: datos.tipo === "ingreso" || datos.tipo === "ajuste",
        })}
      </Monto>
    </li>
  );
}
function Analisis({ sugerencia }: { sugerencia: Sugerencia }) {
  return (
    <Nota className="mt-4">
      <p>
        <span className="font-fuerte">Análisis. </span>
        {sugerencia.analisis}
      </p>
      <p className="font-fuerte">
        {sugerencia.opcion === null
          ? "No hay una pista clara: elige tú."
          : sugerencia.motivo}
      </p>
    </Nota>
  );
}
function Cargando() {
  return useVisibleTras() ? (
    <p role="status" className="text-muted-foreground">
      Cargando…
    </p>
  ) : null;
}
function Fallo({
  mensaje,
  reintentar,
}: {
  mensaje: string;
  reintentar: () => Promise<void>;
}) {
  return (
    <Hoja>
      <Aviso tipo="error">{mensaje}</Aviso>
      <Button className="mt-4" onClick={() => void reintentar()}>
        Volver a intentar
      </Button>
    </Hoja>
  );
}

export function PreguntasConciliacion() {
  const { cliente } = useSesion();
  const obtener = useCallback(
    () => dato(cliente.GET("/api/conciliacion/preguntas")),
    [cliente],
  );
  const { carga, recargar } = useCarga(obtener);
  const deshacer = useDeshacerConciliacion(cliente, recargar);
  const [ocupada, setOcupada] = useState<number | "lote" | null>(null);
  const [error, setError] = useState<{
    id: number | "lote";
    texto: string;
  } | null>(null);
  const responder = async (id: number | "lote", opcion?: string) => {
    setOcupada(id);
    setError(null);
    try {
      const resultado =
        id === "lote"
          ? await dato(
              cliente.POST("/api/conciliacion/preguntas/aceptar-sugerencias", {
                params: { header: cabeceraCsrf() },
                headers: { "Content-Type": "application/json" },
              }),
            )
          : await dato(
              cliente.POST(
                "/api/conciliacion/preguntas/{pregunta_id}/respuesta",
                {
                  params: { path: { pregunta_id: id }, header: cabeceraCsrf() },
                  body: { opcion: opcion! },
                },
              ),
            );
      deshacer.ofrecer({
        deshacer: resultado.deshacer,
        texto: resultado.resumen,
        restaurado: (restaurado) => restaurado.resumen,
      });
      await recargar();
    } catch (falla) {
      setError({ id, texto: textoFalla(falla) });
      await recargar();
    } finally {
      setOcupada(null);
    }
  };
  return (
    <Pila>
      <CabeceraImportacion
        titulo="¿Es el mismo movimiento?"
        ayuda="La app analiza cada caso y te sugiere una respuesta con su razón. Tú decides con un toque, y puedes deshacerlo."
        volver="/importacion"
        textoVolver="Importación"
      />
      {error &&
      carga.tipo === "listo" &&
      (error.id === "lote"
        ? carga.datos.con_sugerencia === 0
        : !carga.datos.preguntas.some((p) => p.id === error.id)) ? (
        <Aviso tipo="error">{error.texto}</Aviso>
      ) : null}
      <AvisoDeshacer
        estado={deshacer.estado}
        alDeshacer={() => void deshacer.deshacer()}
        alPausar={deshacer.pausar}
        alReanudar={deshacer.reanudar}
      />
      {carga.tipo === "cargando" ? (
        <Cargando />
      ) : carga.tipo === "error" ? (
        <Fallo mensaje={carga.mensaje} reintentar={recargar} />
      ) : (
        <>
          <ComprobarSaldo contexto={carga.datos} deshabilitado={ocupada !== null || deshacer.estado?.fase === "deshaciendo"} />
          {carga.datos.con_sugerencia > 0 ? (
            <Nota
              acciones={
                <Button
                  variant="outline"
                  disabled={ocupada !== null}
                  onClick={() => void responder("lote")}
                >
                  <Check aria-hidden="true" className="size-5" />
                  {ocupada === "lote"
                    ? "Guardando…"
                    : `Aceptar ${carga.datos.con_sugerencia === 1 ? "la sugerencia" : `las ${carga.datos.con_sugerencia} sugerencias`}`}
                </Button>
              }
            >
              <p className="font-fuerte">
                {carga.datos.total === 1
                  ? "Esta pregunta tiene una sugerencia clara."
                  : `${carga.datos.con_sugerencia} de ${carga.datos.total} preguntas tienen una sugerencia clara.`}
              </p>
              <p>Puedes aplicarlas juntas, o responder una por una abajo.</p>
              {error?.id === "lote" ? (
                <Aviso tipo="error">{error.texto}</Aviso>
              ) : null}
            </Nota>
          ) : null}
          {carga.datos.total === 0 ? (
            <Hoja>
              <Vacio icono={CircleCheck} titulo="No hay preguntas pendientes">
                <p>Ya resolviste las diferencias de la importación.</p>
              </Vacio>
            </Hoja>
          ) : (
            carga.datos.preguntas.map((pregunta, indice) => (
              <Hoja
                key={pregunta.id}
                aria-labelledby={`pregunta-${pregunta.id}`}
              >
                <h2 id={`pregunta-${pregunta.id}`}>
                  {indice + 1} de {carga.datos.total} ·{" "}
                  {pregunta.tipo === "mismo_dia_ajuste"
                    ? "¿Ya estaba en el saldo que ajustaste?"
                    : pregunta.tipo === "varios_candidatos"
                      ? "¿Cuál es el mismo?"
                      : "¿Es el mismo?"}
                </h2>
                <ul className="mt-4">
                  <FilaDato datos={pregunta.movimiento} />
                  {pregunta.candidatos.map((candidato, i) => (
                    <FilaDato
                      key={i}
                      datos={candidato}
                    />
                  ))}
                  {pregunta.ajuste ? (
                    <FilaDato datos={pregunta.ajuste} />
                  ) : null}
                </ul>
                <Analisis sugerencia={pregunta.sugerencia} />
                <div className="flex flex-col gap-3 mt-4 computador:flex-row computador:flex-wrap">
                  {pregunta.opciones.map((opcion) => (
                    <div className="flex flex-col gap-1" key={opcion.id}>
                      <Button
                        variant={
                          pregunta.sugerencia.opcion === opcion.id
                            ? "default"
                            : "outline"
                        }
                        disabled={ocupada !== null}
                        onClick={() => void responder(pregunta.id, opcion.id)}
                      >
                        {ocupada === pregunta.id ? "Guardando…" : opcion.texto}
                      </Button>
                      <Ayuda>{opcion.consecuencia}</Ayuda>
                    </div>
                  ))}
                </div>
                {error?.id === pregunta.id ? (
                  <Aviso tipo="error" className="mt-4">
                    {error.texto}
                  </Aviso>
                ) : null}
              </Hoja>
            ))
          )}
        </>
      )}
    </Pila>
  );
}

export function NoEstaEnBanco() {
  const { cliente } = useSesion();
  const obtener = useCallback(
    () => dato(cliente.GET("/api/conciliacion/no-esta-en-el-banco")),
    [cliente],
  );
  const { carga, recargar } = useCarga(obtener);
  const deshacer = useDeshacerConciliacion(cliente, recargar);
  const [ocupada, setOcupada] = useState<number | null>(null);
  const [error, setError] = useState<{ id: number; texto: string } | null>(
    null,
  );
  const responder = async (id: number, opcion: "borrar" | "dejar") => {
    setOcupada(id);
    setError(null);
    try {
      const resultado = await dato(
        cliente.POST(
          "/api/conciliacion/no-esta-en-el-banco/{movimiento_id}/respuesta",
          {
            params: { path: { movimiento_id: id }, header: cabeceraCsrf() },
            body: { opcion },
          },
        ),
      );
      deshacer.ofrecer({
        deshacer: resultado.deshacer,
        texto: resultado.resumen,
        restaurado: (restaurado) => restaurado.resumen,
      });
      await recargar();
    } catch (falla) {
      setError({ id, texto: textoFalla(falla) });
      await recargar();
    } finally {
      setOcupada(null);
    }
  };
  return (
    <Pila>
      <CabeceraImportacion
        titulo="No está en el banco"
        ayuda="Movimientos que llegaron por correo dentro de las fechas del reporte y que el banco no trae. La app nunca los borra sola: te sugiere y tú decides."
        volver="/importacion"
        textoVolver="Importación"
      />
      {error &&
      carga.tipo === "listo" &&
      !carga.datos.movimientos.some((p) => p.id === error.id) ? (
        <Aviso tipo="error">{error.texto}</Aviso>
      ) : null}
      <AvisoDeshacer
        estado={deshacer.estado}
        alDeshacer={() => void deshacer.deshacer()}
        alPausar={deshacer.pausar}
        alReanudar={deshacer.reanudar}
      />
      {carga.tipo === "cargando" ? (
        <Cargando />
      ) : carga.tipo === "error" ? (
        <Fallo mensaje={carga.mensaje} reintentar={recargar} />
      ) : (
        <>
          <ComprobarSaldo contexto={carga.datos} deshabilitado={ocupada !== null || deshacer.estado?.fase === "deshaciendo"} />
          {carga.datos.reporte?.desde && carga.datos.reporte.hasta ? (
            <Ayuda>
              Reporte del{" "}
              {fechaEnFrase(carga.datos.reporte.desde, hoyColombia())} al{" "}
              {fechaEnFrase(carga.datos.reporte.hasta, hoyColombia())}.
            </Ayuda>
          ) : null}
          {carga.datos.reporte?.dia_incompleto && carga.datos.reporte.desde ? (
            <Nota>
              <p>
                El {fechaEnFrase(carga.datos.reporte.desde, hoyColombia())},
                primer día del reporte, puede venir incompleto. Por precaución,
                ese día no se marca como «No está en el banco».
              </p>
            </Nota>
          ) : null}
          {carga.datos.movimientos.length === 0 ? (
            <Hoja>
              <Vacio
                icono={CircleCheck}
                titulo="No hay movimientos por revisar"
              >
                <p>Todo lo del correo dentro del reporte ya está resuelto.</p>
              </Vacio>
            </Hoja>
          ) : (
            carga.datos.movimientos.map((pendiente, indice) => (
              <Hoja
                key={pendiente.id}
                aria-labelledby={`no-banco-${pendiente.id}`}
              >
                <h2 id={`no-banco-${pendiente.id}`}>
                  {indice + 1} de {carga.datos.movimientos.length} · No está en
                  el banco
                </h2>
                <ul className="mt-4">
                  <FilaDato datos={pendiente.movimiento} />
                </ul>
                <Analisis sugerencia={pendiente.sugerencia} />
                <div className="flex flex-col gap-3 mt-4 computador:flex-row computador:flex-wrap">
                  <Button
                    variant={
                      pendiente.sugerencia.opcion === "borrar"
                        ? "default"
                        : "outline"
                    }
                    disabled={ocupada !== null}
                    onClick={() => void responder(pendiente.id, "borrar")}
                  >
                    <Trash2 aria-hidden="true" className="size-5" />
                    {ocupada === pendiente.id
                      ? "Guardando…"
                      : "Borrar movimiento"}
                  </Button>
                  <Button
                    variant={
                      pendiente.sugerencia.opcion === "dejar"
                        ? "default"
                        : "outline"
                    }
                    disabled={ocupada !== null}
                    onClick={() => void responder(pendiente.id, "dejar")}
                  >
                    <Check aria-hidden="true" className="size-5" />
                    Dejarlo: sigue contando en tu saldo
                  </Button>
                </div>
                {error?.id === pendiente.id ? (
                  <Aviso tipo="error" className="mt-4">
                    {error.texto}
                  </Aviso>
                ) : null}
              </Hoja>
            ))
          )}
        </>
      )}
    </Pila>
  );
}
