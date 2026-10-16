import { CircleCheck, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "wouter";
import type { Esquemas } from "@/compartido/http/cliente";
import { Aviso } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { dato, textoFalla } from "@/compartido/http/dato";
import { useSesion } from "@/funcionalidades/sesion/sesion";

type Carga = { tipo: "cargando" } | { tipo: "error"; texto: string } | { tipo: "listo"; datos: Esquemas["EstadoInicio"] };

/** La API decide el total, el texto, las áreas y sus destinos. La revisión
 * vuelve a consultarse tras sincronizar y cada vez que se carga Inicio. */
export function EstadoRevisionesInicio({ revision, ocupado }: { revision: unknown; ocupado: boolean }) {
  const { cliente } = useSesion();
  const [carga, setCarga] = useState<Carga>({ tipo: "cargando" });
  const turno = useRef(0);
  const peticion = useRef<AbortController | null>(null);
  const recargar = useCallback(async () => {
    const actual = ++turno.current;
    peticion.current?.abort();
    setCarga({ tipo: "cargando" });
    if (ocupado) return;
    const controlador = new AbortController();
    peticion.current = controlador;
    try {
      const datos = await dato(cliente.GET("/api/inicio/estado", { signal: controlador.signal }));
      if (actual === turno.current) setCarga({ tipo: "listo", datos });
    } catch (error) {
      if (actual === turno.current) setCarga({ tipo: "error", texto: textoFalla(error) });
    }
  }, [cliente, ocupado, revision]);
  useEffect(() => {
    void recargar();
    return () => { ++turno.current; peticion.current?.abort(); };
  }, [recargar]);

  // Al iniciar una sincronización se retira inmediatamente el estado anterior,
  // incluso antes de que el efecto pueda cancelar una consulta en vuelo.
  if (ocupado || carga.tipo === "cargando") return <p role="status" className="text-muted-foreground">Consultando las revisiones…</p>;
  if (carga.tipo === "error") return <div className="space-y-3">
    <Aviso tipo="error">No se pudieron consultar las revisiones. {carga.texto}</Aviso>
    <Button variant="outline" onClick={() => void recargar()}>Volver a consultar las revisiones</Button>
  </div>;
  const estado = carga.datos;
  if (estado.todo_al_dia) return <p role="status" className="flex items-center gap-2 font-medio"><CircleCheck aria-hidden="true" className="size-5 text-exito" />{estado.texto}</p>;
  return <details>
    <summary className="flex items-center gap-2 min-h-(--tactil-min) cursor-pointer font-medio"><TriangleAlert aria-hidden="true" className="size-5 text-advertencia" />{estado.texto}</summary>
    <ul className="mt-3 flex flex-col gap-2" aria-label="Revisiones pendientes">
      {estado.areas.map((area) => <li key={area.codigo}><Button asChild variant="ghost"><Link href={area.href}>{area.titulo}: {area.cantidad}</Link></Button></li>)}
    </ul>
  </details>;
}
