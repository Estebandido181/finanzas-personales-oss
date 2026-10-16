import { ChevronLeft, FileSpreadsheet, type LucideIcon } from "lucide-react";
import { Link } from "wouter";
import { Ayuda, Hoja, Nota } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { MarcaNeutra } from "@/compartido/ui/cifras";
import { Encabezado } from "@/compartido/ui/pantalla";

/** Presentación del prototipo aprobado30: solo tokens y piezas de la libreta. */
export function CabeceraImportacion({
  titulo,
  ayuda,
  volver = "/",
  textoVolver = "Inicio",
}: {
  titulo: string;
  ayuda?: string;
  volver?: string;
  textoVolver?: string;
}) {
  return (
    <Encabezado
      titulo={titulo}
      antes={
        <nav aria-label="Volver">
          <Button asChild variant="ghost">
            <Link href={volver}>
              <ChevronLeft aria-hidden="true" className="size-5" />
              {textoVolver}
            </Link>
          </Button>
        </nav>
      }
      debajo={ayuda ? <Ayuda>{ayuda}</Ayuda> : undefined}
    />
  );
}
export function PasosDelBanco() {
  return (
    <Hoja aria-labelledby="pasos-banco">
      <h2 id="pasos-banco">Cómo conseguir el archivo</h2>
      <ol className="list-decimal pl-6 mt-4 space-y-2">
        <li>Entra a la Sucursal Virtual de Bancolombia.</li>
        <li>Toca «Descargar movimientos».</li>
        <li>Elige el rango de fechas.</li>
        <li>Descarga el Excel.</li>
        <li>
          Vuelve aquí y elige el archivo. En el celular también sirve tocar
          Compartir y elegir Finanzas.
        </li>
      </ol>
    </Hoja>
  );
}
export function LimiteDelBanco() {
  return (
    <Nota>
      <p className="font-fuerte">
        Revisa que la descarga incluya todo el periodo que elegiste.
      </p>
      <p>Si faltan movimientos, descarga un rango más corto, por ejemplo un mes.</p>
    </Nota>
  );
}
export function ConteoImportacion({
  icono,
  titulo,
  ayuda,
  cantidad,
}: {
  icono: LucideIcon;
  titulo: string;
  ayuda: string;
  cantidad: number;
}) {
  return (
    <li className="grid grid-cols-[auto_minmax(0,1fr)_auto] gap-3 items-start py-(--espacio-fila) not-first:border-t not-first:border-renglon">
      <MarcaNeutra icono={icono} />
      <div>
        <p className="font-medio">{titulo}</p>
        <p className="text-sm text-muted-foreground">{ayuda}</p>
      </div>
      <span className="font-titulos text-2xl font-fuerte">{cantidad}</span>
    </li>
  );
}
export function ArchivoElegido({ nombre }: { nombre: string }) {
  return (
    <p className="flex gap-3 items-center min-w-0">
      <FileSpreadsheet aria-hidden="true" className="size-5 shrink-0" />
      <span className="[overflow-wrap:anywhere]">{nombre}</span>
    </p>
  );
}
