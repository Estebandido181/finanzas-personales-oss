import { FileQuestionMark } from "lucide-react";
import { Link } from "wouter";
import { Hoja, Vacio } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { TEXTOS } from "@/compartido/textos/textos";
import { Encabezado, Pila } from "@/compartido/ui/pantalla";

/** Una dirección dentro de /app que no es ninguna sección. */
export function NoEncontrada() {
  return (
    <Pila>
      <Encabezado titulo={TEXTOS.noEncontrada.titulo} />
      <Hoja>
        <Vacio
          icono={FileQuestionMark}
          accion={
            <Button asChild variant="outline">
              <Link href="/">{TEXTOS.noEncontrada.boton}</Link>
            </Button>
          }
        >
          <p>{TEXTOS.noEncontrada.texto}</p>
        </Vacio>
      </Hoja>
    </Pila>
  );
}
