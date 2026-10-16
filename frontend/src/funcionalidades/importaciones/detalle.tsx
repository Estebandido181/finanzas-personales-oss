import {
  Check,
  CircleCheck,
  FileSpreadsheet,
  Pencil,
  Plus,
  Undo2,
} from "lucide-react";
import { useCallback, useState } from "react";
import { Link } from "wouter";
import { Aviso, Ayuda, Hoja, Vacio } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { Dialogo } from "@/compartido/ui/ui/dialogo";
import { cabeceraCsrf, type Esquemas } from "@/compartido/http/cliente";
import { fechaEnFrase, fechaYHora, hoyColombia } from "@/compartido/formatos/formato";
import { GrupoCategorizable } from "@/funcionalidades/movimientos/grupo";
import { categorizarGrupo } from "@/funcionalidades/movimientos/cargar";
import { Pila, useVisibleTras } from "@/compartido/ui/pantalla";
import { useSesion } from "@/funcionalidades/sesion/sesion";
import { CabeceraImportacion, ConteoImportacion } from "@/funcionalidades/importaciones/piezas";
import { dato, textoFalla } from "@/compartido/http/dato";
import { useCarga } from "@/compartido/http/carga";
import { ComprobarSaldo } from "@/funcionalidades/saldo/comprobar";

function Cargando() {
  return useVisibleTras() ? (
    <p role="status" className="text-muted-foreground">
      Cargando…
    </p>
  ) : null;
}
export function PorResolver({
  importacion,
  rutaCategorizar,
}: {
  importacion: Esquemas["DetalleImportacion"];
  rutaCategorizar?: string;
}) {
  return (
    <Hoja aria-labelledby="resolver-importacion">
      <h2 id="resolver-importacion">Por resolver</h2>
      <ul className="mt-4 divide-y divide-renglon">
        {importacion.preguntas_pendientes > 0 ? (
          <li className="py-(--espacio-fila)">
            <p className="font-medio">
              {importacion.preguntas_pendientes}{" "}
              {importacion.preguntas_pendientes === 1
                ? "pregunta"
                : "preguntas"}
              : ¿es el mismo?
            </p>
            <Ayuda>
              El correo y el banco traen un movimiento parecido. La app te
              sugiere una respuesta y tú decides.
            </Ayuda>
            <Button asChild variant="outline" className="mt-3">
              <Link href="/conciliacion/preguntas">Responder preguntas</Link>
            </Button>
          </li>
        ) : null}
        {importacion.no_en_banco_pendientes > 0 ? (
          <li className="py-(--espacio-fila)">
            <p className="font-medio">
              {importacion.no_en_banco_pendientes}{" "}
              {importacion.no_en_banco_pendientes === 1
                ? "movimiento no está"
                : "movimientos no están"}{" "}
              en el banco
            </p>
            <Ayuda>
              Llegaron por correo y el reporte no los trae. Nunca se borran
              solos.
            </Ayuda>
            <Button asChild variant="outline" className="mt-3">
              <Link href="/conciliacion/no-esta-en-el-banco">
                Revisar movimientos
              </Link>
            </Button>
          </li>
        ) : null}
        {importacion.sin_categoria > 0 ? (
          <li className="py-(--espacio-fila)">
            <p className="font-medio">
              {importacion.sin_categoria}{" "}
              {importacion.sin_categoria === 1 ? "movimiento" : "movimientos"}{" "}
              sin categoría
            </p>
            <Ayuda>
              Están agrupados por descripción para categorizarlos juntos.
            </Ayuda>
            <Button asChild className="mt-3">
              <Link href={rutaCategorizar ?? `/importaciones/${importacion.id}/categorizar`}>
                Categorizar lo nuevo
              </Link>
            </Button>
          </li>
        ) : null}
        {importacion.resumen.anteriores > 0 ? (
          <li className="py-(--espacio-fila)">
            <p className="font-medio">
              {importacion.resumen.anteriores}{" "}
              {importacion.resumen.anteriores === 1
                ? "movimiento es anterior"
                : "movimientos son anteriores"}{" "}
              a tu fecha de inicio
            </p>
            <Ayuda>Esas filas no se importaron.</Ayuda>
            {importacion.puede_extender_historial ? (
              <Button asChild variant="outline" className="mt-3">
                <Link href="/extender-historial">Extender historial</Link>
              </Button>
            ) : null}
          </li>
        ) : null}
      </ul>
    </Hoja>
  );
}
export function DetalleBanco({ id }: { id?: number }) {
  const { cliente } = useSesion();
  const obtener = useCallback(
    async () =>
      id === undefined
        ? (await dato(cliente.GET("/api/importaciones/ultima"))).importacion
        : dato(
            cliente.GET("/api/importaciones/{importacion_id}", {
              params: { path: { importacion_id: id } },
            }),
          ),
    [cliente, id],
  );
  const { carga, recargar } = useCarga(obtener);
  const [confirmando, setConfirmando] = useState(false);
  const [ocupada, setOcupada] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const deshacer = async (importacion: Esquemas["DetalleImportacion"]) => {
    setOcupada(true);
    setError(null);
    try {
      await dato(
        cliente.POST("/api/importaciones/{importacion_id}/deshacer", {
          params: {
            path: { importacion_id: importacion.id },
            header: cabeceraCsrf(),
          },
          headers: { "Content-Type": "application/json" },
        }),
      );
      setConfirmando(false);
      await recargar();
    } catch (falla) {
      setError(textoFalla(falla));
    } finally {
      setOcupada(false);
    }
  };
  const importacion = carga.tipo === "listo" ? carga.datos : null;
  return (
    <Pila>
      <CabeceraImportacion
        titulo={
          importacion
            ? `Importación del ${fechaEnFrase(importacion.hecha_en, hoyColombia())}`
            : "La importación"
        }
        ayuda={
          importacion
            ? `Importada el ${fechaYHora(importacion.hecha_en, hoyColombia())}`
            : undefined
        }
      />
      {carga.tipo === "cargando" ? (
        <Cargando />
      ) : carga.tipo === "error" ? (
        <Hoja>
          <Aviso tipo="error">{carga.mensaje}</Aviso>
          <Button className="mt-4" onClick={() => void recargar()}>
            Volver a intentar
          </Button>
        </Hoja>
      ) : !importacion ? (
        <Hoja>
          <Vacio
            icono={FileSpreadsheet}
            titulo="Todavía no has importado movimientos"
            accion={
              <Button asChild>
                <Link href="/importar">Importar movimientos del banco</Link>
              </Button>
            }
          >
            <p>
              Descarga el Excel de la Sucursal Virtual y súbelo aquí para
              completar tus cuentas.
            </p>
          </Vacio>
        </Hoja>
      ) : (
        <>
          {error && !confirmando ? <Aviso tipo="error">{error}</Aviso> : null}
          {importacion.deshecha_en ? (
            <Aviso tipo="exito">
              Importación deshecha. Los movimientos y el saldo volvieron a como
              estaban.
            </Aviso>
          ) : null}
          <Hoja aria-labelledby="paso-importacion">
            <h2 id="paso-importacion">Qué pasó</h2>
            {importacion.reporte.desde && importacion.reporte.hasta ? (
              <Ayuda className="mt-4">
                Reporte del{" "}
                {fechaEnFrase(importacion.reporte.desde, hoyColombia())} al{" "}
                {fechaEnFrase(importacion.reporte.hasta, hoyColombia())}.
              </Ayuda>
            ) : null}
            <ul className="mt-4">
              <ConteoImportacion
                icono={Plus}
                titulo="Agregados"
                ayuda="Los trae el banco y la app no los tenía."
                cantidad={importacion.resumen.agregados}
              />
              <ConteoImportacion
                icono={Check}
                titulo="Ya estaban"
                ayuda="Ya estaban confirmados con el banco. No se repitieron."
                cantidad={importacion.resumen.ya_estaban}
              />
              <ConteoImportacion
                icono={Check}
                titulo="Confirmados"
                ayuda="Llegaron por correo o los registraste tú. El banco los confirmó sin repetirlos."
                cantidad={importacion.resumen.confirmados}
              />
              <ConteoImportacion
                icono={Pencil}
                titulo="Corregidos"
                ayuda="Estaban registrados con otro monto. Quedó el monto del banco."
                cantidad={importacion.resumen.corregidos}
              />
            </ul>
            <div className="flex justify-between gap-4 border-t-[3px] border-double border-border pt-3">
              <span>Filas del reporte</span>
              <span className="font-titulos text-xl font-fuerte">
                {importacion.resumen.filas}
              </span>
            </div>
            {importacion.se_puede_deshacer ? (
              <>
                <Ayuda className="mt-4">
                  Deshacer quita {importacion.resumen.agregados}{" "}
                  {importacion.resumen.agregados === 1
                    ? "movimiento agregado"
                    : "movimientos agregados"}
                  {" y restaura "}
                  {importacion.resumen.corregidos}{" "}
                  {importacion.resumen.corregidos === 1
                    ? "movimiento corregido"
                    : "movimientos corregidos"}
                  .
                </Ayuda>
                <Button
                  variant="outline"
                  className="mt-4"
                  onClick={() => setConfirmando(true)}
                >
                  <Undo2 aria-hidden="true" className="size-5" />
                  Deshacer importación
                </Button>
              </>
            ) : importacion.motivo_no_deshacer ? (
              <Ayuda className="mt-4">{importacion.motivo_no_deshacer}</Ayuda>
            ) : null}
          </Hoja>
          {importacion.todo_resuelto && !importacion.deshecha_en ? (
            <Hoja>
              <Vacio icono={CircleCheck} titulo="Preguntas resueltas">
                <p>Terminaste las revisiones de esta importación. Esto no garantiza que el saldo coincida con Bancolombia.</p>
              </Vacio>
            </Hoja>
          ) : !importacion.deshecha_en ? (
            <PorResolver importacion={importacion} />
          ) : null}
          <ComprobarSaldo contexto={importacion} deshabilitado={ocupada} />
          {confirmando ? (
            <Dialogo
              titulo="Deshacer esta importación"
              descripcion={
                <p>
                  {importacion.resumen.agregados === 1
                    ? "Se quita 1 movimiento agregado"
                    : `Se quitan ${importacion.resumen.agregados} movimientos agregados`}
                  {" y se restauran "}
                  {importacion.resumen.corregidos}{" "}
                  {importacion.resumen.corregidos === 1
                    ? "movimiento corregido"
                    : "movimientos corregidos"}
                  . Para volver a importarlos tendrás que subir el archivo otra
                  vez.
                </p>
              }
              alCerrar={() => {
                if (!ocupada) {
                  setConfirmando(false);
                  setError(null);
                }
              }}
              acciones={
                <>
                  <Button
                    variant="outline"
                    disabled={ocupada}
                    onClick={() => {
                      setConfirmando(false);
                      setError(null);
                    }}
                  >
                    Cancelar
                  </Button>
                  <Button
                    disabled={ocupada}
                    onClick={() => void deshacer(importacion)}
                  >
                    {ocupada ? "Deshaciendo…" : "Sí, deshacer importación"}
                  </Button>
                </>
              }
            >
              {error ? <Aviso tipo="error">{error}</Aviso> : null}
            </Dialogo>
          ) : null}
        </>
      )}
    </Pila>
  );
}
export function CategorizarImportacion({ id, volver = `/importaciones/${id}` }: { id: number; volver?: string }) {
  const { cliente } = useSesion();
  const obtener = useCallback(async () => {
    const [detalle, categorias] = await Promise.all([
      dato(
        cliente.GET("/api/importaciones/{importacion_id}", {
          params: { path: { importacion_id: id } },
        }),
      ),
      dato(cliente.GET("/api/categorias")),
    ]);
    return { detalle, categorias: categorias.categorias };
  }, [cliente, id]);
  const { carga, recargar } = useCarga(obtener);
  return (
    <Pila>
      <CabeceraImportacion
        titulo="Categoriza lo nuevo"
        ayuda="Estos movimientos entraron del banco y ninguna regla los categoriza. Están agrupados por descripción: elige una categoría y se aplica a todo el grupo."
        volver={volver}
        textoVolver="Importación"
      />
      {carga.tipo === "cargando" ? (
        <Cargando />
      ) : carga.tipo === "error" ? (
        <Hoja>
          <Aviso tipo="error">{carga.mensaje}</Aviso>
          <Button className="mt-4" onClick={() => void recargar()}>
            Volver a intentar
          </Button>
        </Hoja>
      ) : carga.datos.detalle.sin_categoria === 0 ? (
        <Hoja>
          <Vacio icono={CircleCheck} titulo="Todo categorizado">
            <p>Los movimientos nuevos ya tienen categoría.</p>
          </Vacio>
        </Hoja>
      ) : (
        <Hoja aria-labelledby="grupos-importacion">
          <h2 id="grupos-importacion">
            {carga.datos.detalle.grupos.length}{" "}
            {carga.datos.detalle.grupos.length === 1 ? "grupo" : "grupos"} sin
            categoría
          </h2>
          <ul className="mt-4">
            {carga.datos.detalle.grupos.map((grupo, indice) => (
              <GrupoCategorizable
                key={grupo.clave}
                grupo={grupo}
                categorias={carga.datos.categorias}
                inicialmenteAbierto={indice === 0}
                alCategorizar={(g, c, modo) =>
                  categorizarGrupo(cliente, g, c.id, modo)
                }
              />
            ))}
          </ul>
        </Hoja>
      )}
      <Button asChild variant="outline">
        <Link href={volver}>
          Ver el resultado de la importación
        </Link>
      </Button>
    </Pila>
  );
}
