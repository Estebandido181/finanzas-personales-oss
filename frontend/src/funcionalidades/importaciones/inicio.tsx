import { useCallback } from "react";
import { Link } from "wouter";
import { Aviso, Hoja, Nota } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { useSesion } from "@/funcionalidades/sesion/sesion";
import { dato } from "@/compartido/http/dato";
import { useCarga } from "@/compartido/http/carga";
import { PasosDelBanco } from "@/funcionalidades/importaciones/piezas";
import { PorResolver } from "@/funcionalidades/importaciones/detalle";

export function ResumenImportacionInicio({ revision }: { revision?: string }) {
  const { cliente } = useSesion();
  const obtener = useCallback(async () => {
    const [estado, ultima, arranque] = await Promise.all([
      dato(cliente.GET("/api/importaciones/estado")),
      dato(cliente.GET("/api/importaciones/ultima")),
      dato(cliente.GET("/api/arranque/estado")),
    ]);
    return { estado, ultima: ultima.importacion, arranque };
  }, [cliente, revision]);
  const { carga, recargar } = useCarga(obtener);
  if (carga.tipo === "cargando") return null;
  if (carga.tipo === "error")
    return (
      <Hoja>
        <Aviso tipo="error">{carga.mensaje}</Aviso>
        <Button
          className="mt-3"
          variant="outline"
          onClick={() => void recargar()}
        >
          Volver a consultar la importación
        </Button>
      </Hoja>
    );
  const { estado, ultima, arranque } = carga.datos;
  return (
    <>
      {arranque.puede_iniciar_arranque || arranque.puede_extender_historial ? <div className="flex flex-wrap gap-3">
        {arranque.puede_iniciar_arranque ? <Button asChild variant="outline"><Link href="/arranque">Empezar con historial del banco</Link></Button> : null}
        {arranque.puede_extender_historial ? <Button asChild variant="outline"><Link href="/extender-historial">Extender historial</Link></Button> : null}
      </div> : null}
      {estado.mostrar_recordatorio ? (
        <Nota
          acciones={
            <Button asChild>
              <Link href="/importar">Importar movimientos del banco</Link>
            </Button>
          }
        >
          <p className="font-fuerte">
            Conviene importar los movimientos del banco
          </p>
          <p>
            {estado.ultima_id === null
              ? "Todavía no importaste el reporte del banco."
              : `Llevas ${estado.movimientos_desde_ultima} movimientos desde la última importación, hace ${estado.semanas_desde_ultima} semanas.`}
          </p>
          <p>
            Revisa que cada descarga cubra el periodo elegido. Importa un
            rango corto para no perder lo más antiguo.
          </p>
          <details>
            <summary className="cursor-pointer min-h-(--tactil-min) flex items-center font-medio">
              Cómo descargar el reporte
            </summary>
            <div className="mt-3">
              <PasosDelBanco />
            </div>
          </details>
        </Nota>
      ) : null}
      {ultima ? (
        <>
          <Hoja aria-labelledby="ultima-importacion">
            <h2 id="ultima-importacion">Última importación del banco</h2>
            <p className="mt-4">
              {ultima.resumen.agregados} agregados, {ultima.resumen.ya_estaban}{" "}
              ya estaban, {ultima.resumen.confirmados} confirmados,{" "}
              {ultima.resumen.corregidos} corregidos.
            </p>
            <div className="flex flex-wrap gap-3 mt-4">
              <Button asChild variant="outline">
                <Link href={`/importaciones/${ultima.id}`}>Ver detalle</Link>
              </Button>
              {ultima.se_puede_deshacer ? (
                <Button asChild variant="outline">
                  <Link href={`/importaciones/${ultima.id}`}>
                    Deshacer importación
                  </Link>
                </Button>
              ) : null}
            </div>
          </Hoja>
          {!ultima.todo_resuelto ? <PorResolver importacion={ultima} /> : null}
        </>
      ) : null}
    </>
  );
}
