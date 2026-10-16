import { useId } from "react";
import { Link } from "wouter";
import { Ayuda, Contador, Hoja, Segmentos } from "@/compartido/ui/libreta";
import { useContadorNoReconocidos } from "@/funcionalidades/sincronizacion/contador";
import { BotonCerrarSesion, CLASE_PESTANA, OPCIONES_TEMA } from "@/app/navegacion/marco";
import { NOMBRE_EN_MAS, seccion } from "@/app/navegacion/secciones";
import { useTema } from "@/compartido/tema/preferencias";
import { TEXTOS } from "@/compartido/textos/textos";
import { Encabezado, Pila } from "@/compartido/ui/pantalla";

/** "Más" (celular): lo que no cabe en la barra inferior (prototipo mas.html). */
export function Mas() {
  const contador = useContadorNoReconocidos();
  const [tema, elegirTema] = useTema();
  const idApariencia = useId();
  const enlaces = [seccion("no-reconocidos"), seccion("categorias")];
  return (
    <Pila>
      <Encabezado titulo={TEXTOS.mas.titulo} />
      <Hoja>
        <ul className="[&>li+li]:border-t [&>li+li]:border-renglon">
          {enlaces.map(({ id, ruta, nombre, icono: Icono }) => (
            <li key={id}>
              <Link href={ruta} className={CLASE_PESTANA}>
                <Icono aria-hidden="true" className="size-5" />
                <span>{NOMBRE_EN_MAS[id] ?? nombre}</span>
                {id === "no-reconocidos" && contador ? <Contador cantidad={contador} /> : null}
              </Link>
            </li>
          ))}
        </ul>
      </Hoja>
      <Hoja aria-labelledby={idApariencia}>
        <h2 id={idApariencia}>{TEXTOS.apariencia.titulo}</h2>
        <Ayuda className="mt-(--espacio-texto) mb-(--espacio-cabeza-hoja)">
          {TEXTOS.apariencia.ayuda}
        </Ayuda>
        <Segmentos
          opciones={OPCIONES_TEMA}
          valor={tema}
          alElegir={elegirTema}
          idEtiqueta={idApariencia}
        />
      </Hoja>
      <BotonCerrarSesion variante="outline" />
    </Pila>
  );
}
