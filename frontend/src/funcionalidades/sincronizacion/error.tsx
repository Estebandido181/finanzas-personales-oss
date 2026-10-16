import { Info, TriangleAlert } from "lucide-react";
import { useId } from "react";
import { AvisoConTitulo } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { GUIA_AUTORIZAR_GMAIL, TEXTOS, textoPermisoRechazado } from "@/compartido/textos/textos";
import type { VistaSincronizacion } from "./estado";

/**
 * TEXTOS.md, "Caso del ítem 13": arriba del inicio, con sombra y role="alert".
 * También lo usa "Correos no reconocidos" (ítem 19) cuando el reproceso falla
 * con los mismos códigos: `titulo` cambia solo el título.
 */
export function ErrorSincronizacion({
  vista,
  titulo,
}: {
  vista: Extract<VistaSincronizacion, { tipo: "fallida" }>;
  titulo?: string;
}) {
  const id = useId();
  const textos = TEXTOS.inicio.errorSincronizacion;
  const permiso = vista.codigo === "autorizacion_gmail";
  return (
    <AvisoConTitulo
      tipo="error"
      icono={TriangleAlert}
      titulo={titulo ?? textos.titulo}
      idTitulo={id}
      tituloComoEncabezado
      destacado
      alerta
      acciones={
        permiso ? (
          <Button asChild>
            <a href={GUIA_AUTORIZAR_GMAIL} rel="noopener noreferrer">
              <Info aria-hidden="true" className="size-5" />
              {textos.botonGuia}
            </a>
          </Button>
        ) : undefined
      }
    >
      {permiso ? (
        <>
          <p>{textoPermisoRechazado(vista.desde)}</p>
          <p>
            <strong>{textos.queHacer}</strong> {textos.reautorizar}
          </p>
        </>
      ) : (
        <p>{vista.codigo === "error_inesperado" ? textos.sinCausa : vista.mensajeApi}</p>
      )}
    </AvisoConTitulo>
  );
}
