/**
 * Correos no reconocidos (ítem 19). Sigue el prototipo aprobado
 * (diseno/prototipo/no-reconocidos.html y no-reconocidos-vacio.html) y
 * TEXTOS.md, "Correos no reconocidos".
 *
 * Muestra asunto y fecha de cada correo (el cuerpo no se guarda) y un botón
 * que los vuelve a procesar todos. La API decide qué pasa con cada uno: un
 * correo que ahora sí se reconoce se va de la lista y crea su movimiento; uno
 * que sigue sin reconocerse permanece. Reprocesar de a uno no se muestra en el
 * prototipo, así que no se ofrece.
 */
import { CircleAlert, CircleCheck, MailQuestionMark, RefreshCw, WifiOff } from "lucide-react";
import { Link } from "wouter";
import { Aviso, Ayuda, Hoja, Vacio } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { MarcaNeutra } from "@/compartido/ui/cifras";
import { useActualizarContadorNoReconocidos } from "@/funcionalidades/sincronizacion/contador";
import {
  useNoReconocidos,
  useReprocesar,
  type SalidaReproceso,
} from "@/funcionalidades/sincronizacion/cargar";
import { fechaDelCorreo, textoReproceso, type CorreoNoReconocido } from "@/funcionalidades/sincronizacion/datos";
import { useSesion } from "@/funcionalidades/sesion/sesion";
import { correos, TEXTOS } from "@/compartido/textos/textos";
import { Encabezado, Pila, useVisibleTras } from "@/compartido/ui/pantalla";
import { ErrorSincronizacion } from "@/funcionalidades/sincronizacion/error";

const T = TEXTOS.noReconocidos;

export function NoReconocidos() {
  const { cliente } = useSesion();
  const actualizarContador = useActualizarContadorNoReconocidos();
  const { carga, recargar } = useNoReconocidos(cliente, actualizarContador);
  const { enCurso, salida, reprocesar } = useReprocesar(cliente, () => recargar(true));
  const hayCorreos = carga.tipo === "listo" && carga.correos.length > 0;

  return (
    <Pila>
      <Encabezado titulo={T.titulo} debajo={<Ayuda>{T.ayuda}</Ayuda>}>
        {hayCorreos ? (
          <Button type="button" disabled={enCurso} onClick={() => void reprocesar()}>
            <RefreshCw aria-hidden="true" className="size-5" />
            {enCurso ? T.procesando : T.volverAProcesar}
          </Button>
        ) : null}
      </Encabezado>
      <Resultado salida={salida} />
      {carga.tipo === "cargando" ? (
        <Cargando />
      ) : carga.tipo === "error" ? (
        <Hoja>
          <Vacio
            icono={carga.sinRed ? WifiOff : CircleAlert}
            accion={
              <Button type="button" onClick={() => void recargar()}>
                {TEXTOS.errores.volverAIntentar}
              </Button>
            }
          >
            <p role="alert">{carga.mensaje}</p>
          </Vacio>
        </Hoja>
      ) : carga.correos.length === 0 ? (
        <SinCorreos />
      ) : (
        <Lista correos={carga.correos} />
      )}
    </Pila>
  );
}

function Cargando() {
  const visible = useVisibleTras();
  return visible ? (
    <p role="status" className="text-muted-foreground">
      {TEXTOS.app.cargando}
    </p>
  ) : null;
}

/** El aviso de lo que pasó al volver a procesar (o por qué no se pudo). */
function Resultado({ salida }: { salida: SalidaReproceso }) {
  if (salida === null) return null;
  if (salida.tipo === "error") return <Aviso tipo="error">{salida.texto}</Aviso>;
  const { estado, contadores, codigo_error: codigo, mensaje } = salida.resultado;
  if (estado === "fallida" || contadores === null) {
    // Mismos códigos y mensajes que «Sincronizar ahora» de Inicio.
    return (
      <ErrorSincronizacion
        titulo={T.errorTitulo}
        vista={{
          tipo: "fallida",
          texto: "",
          codigo: codigo ?? "error_inesperado",
          desde: null,
          mensajeApi: mensaje,
        }}
      />
    );
  }
  const texto = textoReproceso(contadores);
  return (
    <Aviso tipo={texto.tipo}>
      <span className="font-fuerte">{texto.titulo}</span>
      {texto.detalle ? ` ${texto.detalle}` : null}
    </Aviso>
  );
}

function Lista({ correos: lista }: { correos: CorreoNoReconocido[] }) {
  return (
    <Hoja aria-labelledby="titulo-lista">
      <h2
        id="titulo-lista"
        className="pb-3 border-b border-border font-texto text-base font-fuerte tracking-normal leading-(--interlineado-texto)"
      >
        {correos(lista.length)}
      </h2>
      <ul>
        {lista.map((correo) => (
          <li
            key={correo.gmail_id}
            className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 items-start py-(--espacio-fila) last:pb-0 not-first:border-t not-first:border-renglon"
          >
            <MarcaNeutra icono={MailQuestionMark} className="mt-0.5" />
            <div className="min-w-0">
              <p className="font-medio [overflow-wrap:anywhere]">{correo.asunto}</p>
              <p className="text-muted-foreground text-sm">{fechaDelCorreo(correo.fecha)}</p>
            </div>
          </li>
        ))}
      </ul>
    </Hoja>
  );
}

function SinCorreos() {
  return (
    <Hoja>
      <Vacio
        icono={CircleCheck}
        titulo={T.vacioTitulo}
        accion={
          <Button asChild variant="outline">
            <Link href="/">{T.volverAlInicio}</Link>
          </Button>
        }
      >
        <p>{T.vacioTexto}</p>
      </Vacio>
    </Hoja>
  );
}
