import { FileSpreadsheet, RefreshCw, Trash2 } from "lucide-react";
import { useId, useRef } from "react";
import { Aviso, Ayuda, Hoja } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { ArchivoElegido, LimiteDelBanco, PasosDelBanco } from "@/funcionalidades/importaciones/piezas";
import { MIME_EXCEL } from "@/pwa/compartir";

export function ElegirExcel({
  archivo,
  ocupado,
  error,
  alElegir,
  alAnalizar,
  alQuitar,
}: {
  archivo: File | null;
  ocupado: boolean;
  error: string | null;
  alElegir: (archivo: File) => void;
  alAnalizar: () => void;
  alQuitar: () => void;
}) {
  const entrada = useRef<HTMLInputElement>(null);
  const id = useId();
  return (
    <>
      <PasosDelBanco />
      <LimiteDelBanco />
      <Hoja aria-labelledby={id}>
        <h2 id={id}>Tu archivo</h2>
        <Ayuda className="mt-4">
          Un archivo a la vez. Si importas dos veces el mismo, no cambia nada.
        </Ayuda>
        <input
          ref={entrada}
          type="file"
          accept={`.xlsx,${MIME_EXCEL}`}
          className="sr-only"
          aria-label="Archivo Excel del banco"
          disabled={ocupado}
          onChange={(evento) => {
            const elegido = evento.currentTarget.files?.[0];
            if (elegido) alElegir(elegido);
            evento.currentTarget.value = "";
          }}
        />
        {archivo ? (
          <div className="mt-4 space-y-4">
            <ArchivoElegido nombre={archivo.name} />
            <div className="flex flex-wrap gap-3">
              <Button onClick={alAnalizar} disabled={ocupado}>
                <RefreshCw aria-hidden="true" className="size-5" />
                {ocupado ? "Analizando…" : "Analizar archivo"}
              </Button>
              <Button variant="outline" onClick={alQuitar} disabled={ocupado}>
                <Trash2 aria-hidden="true" className="size-5" />
                Quitar archivo
              </Button>
              <Button
                variant="ghost"
                onClick={() => entrada.current?.click()}
                disabled={ocupado}
              >
                Elegir otro archivo
              </Button>
            </div>
          </div>
        ) : (
          <Button
            className="mt-4"
            onClick={() => entrada.current?.click()}
            disabled={ocupado}
          >
            <FileSpreadsheet aria-hidden="true" className="size-5" />
            Elegir archivo Excel
          </Button>
        )}
        {error ? (
          <Aviso tipo="error" className="mt-4">
            {error}
          </Aviso>
        ) : null}
      </Hoja>
    </>
  );
}
