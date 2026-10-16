/**
 * El aviso de «Deshacer» (ítem 38). Usa el aviso con título de la libreta
 * (fondo `aviso-*`, ícono, texto en negrita y una acción): no es una
 * notificación flotante (SISTEMA.md: los resultados se muestran cerca de donde
 * se hicieron) sino el resultado del borrado, en la misma pantalla, que
 * desaparece cuando se acaba el tiempo que mandó el servidor.
 *
 * Recibe el foco cuando aparece o cambia: el botón que borró ya no está.
 */
import { CircleAlert, CircleCheck, Undo2 } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { AvisoConTitulo } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { MARCA_AVISO_DESHACER, type EstadoDeshacer } from "@/compartido/deshacer/usar";
import { cn } from "@/compartido/ui/utils";
import { TEXTOS } from "@/compartido/textos/textos";

export function AvisoDeshacer({
  estado,
  alDeshacer,
  alPausar,
  alReanudar,
  className,
}: {
  estado: EstadoDeshacer | null;
  alDeshacer: () => void;
  /** La cuenta se pausa mientras el cursor o el foco (de un control del aviso) estén encima. */
  alPausar?: () => void;
  alReanudar?: () => void;
  className?: string;
}) {
  const id = useId();
  const aviso = useRef<HTMLElement>(null);
  const fase = estado?.fase;
  const texto = estado?.texto;
  useEffect(() => {
    // Solo cuando aparece o cambia lo que dice, no mientras se deshace.
    if (fase && fase !== "deshaciendo") aviso.current?.focus();
  }, [fase, texto]);

  const [cursor, setCursor] = useState(false);
  const [foco, setFoco] = useState(false);
  const pausado = cursor || foco;
  const accion = useRef({ alPausar, alReanudar });
  accion.current = { alPausar, alReanudar };
  useEffect(() => {
    if (!fase) return;
    if (pausado) accion.current.alPausar?.();
    else accion.current.alReanudar?.();
  }, [pausado, fase]);

  if (!estado) return null;
  const error = estado.fase === "error";
  return (
    <AvisoConTitulo
      ref={aviso}
      tabIndex={-1}
      onMouseEnter={() => setCursor(true)}
      onMouseLeave={() => setCursor(false)}
      // El foco que se le da al aviso al aparecer no pausa: solo el de sus controles (teclado).
      onFocus={(e) => setFoco(e.target !== e.currentTarget)}
      onBlur={() => setFoco(false)}
      {...{ [MARCA_AVISO_DESHACER]: "" }}
      className={cn("focus:outline-none", className)}
      tipo={error ? "error" : "exito"}
      icono={error ? CircleAlert : CircleCheck}
      titulo={estado.texto}
      idTitulo={id}
      alerta={error}
      resultado={!error}
      acciones={
        estado.fase === "oferta" || estado.fase === "deshaciendo" ? (
          <Button type="button" disabled={estado.fase === "deshaciendo"} onClick={alDeshacer}>
            <Undo2 aria-hidden="true" className="size-5" />
            {estado.fase === "deshaciendo" ? TEXTOS.deshacer.deshaciendo : TEXTOS.deshacer.boton}
          </Button>
        ) : undefined
      }
    />
  );
}
