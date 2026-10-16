/** Estado de la pantalla y coordinación de sus operaciones. */
import { cabeceraCsrf, type Esquemas } from "@/compartido/http/cliente";
import { dato, textoFalla } from "@/compartido/http/dato";
import { useSincronizar } from "@/funcionalidades/sincronizacion/sincronizar";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useSearch } from "wouter";
import { useDatosMovimientos } from "@/funcionalidades/movimientos/cargar";
import { esBandeja, leerFiltros, rutaMovimientos, type Movimiento } from "@/funcionalidades/movimientos/datos";
import { useSesion } from "@/funcionalidades/sesion/sesion";

type MovimientoRevisable = Movimiento | Esquemas["MovimientoDescartado"];
export function useControlMovimientos() {
  const { cliente } = useSesion();
  const busqueda = useSearch();
  const parametro = new URLSearchParams(busqueda).get("mes");
  const mes = parametro === null || parametro === "" ? null : parametro;
  const filtros = leerFiltros(busqueda);
  const { carga, recargar } = useDatosMovimientos(cliente, mes, filtros);
  const alTerminarSincronizacion = useCallback(async () => recargar(true), [recargar]);
  const sincronizacion = useSincronizar(cliente, alTerminarSincronizacion, mes);
  const bandeja = esBandeja(filtros);
  const descartados = filtros.vista === "descartados";
  const contexto = rutaMovimientos(mes, filtros);
  const actual = useRef(contexto);
  actual.current = contexto;
  const revision = useRef(0);
  const recargaActual = useRef(recargar);
  recargaActual.current = recargar;
  const montado = useRef(true);
  const enviando = useRef(false);
  const [seleccion, setSeleccion] = useState<{ movimiento: MovimientoRevisable; restaurar: boolean } | null>(null);
  const [mutando, setMutando] = useState(false);
  const [listaOcupada, setListaOcupada] = useState(false);
  const [resultado, setResultado] = useState<Esquemas["ResultadoDescarte"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { montado.current = true; return () => { montado.current = false; }; }, []);
  useLayoutEffect(() => { ++revision.current; setSeleccion(null); setResultado(null); setError(null); }, [contexto]);
  const navegacionBloqueada = mutando || listaOcupada || sincronizacion.enCurso;
  const bloqueado = navegacionBloqueada || (carga.tipo === "listo" && carga.actualizando);
  const revisar = (movimiento: MovimientoRevisable, restaurar = false) => {
    if (bloqueado || enviando.current) return;
    setResultado(null); setError(null); setSeleccion({ movimiento, restaurar });
  };
  const cambiarDescarte = async () => {
    if (!seleccion || bloqueado || enviando.current) return;
    const { movimiento, restaurar } = seleccion;
    if (!(restaurar ? movimiento.puede_restaurar : movimiento.puede_descartar)) return;
    enviando.current = true; setMutando(true); setResultado(null); setError(null);
    const origen = contexto;
    const turno = revision.current;
    try {
      const respuesta = await dato(cliente.POST(restaurar ? "/api/movimientos/{movimiento_id}/restaurar" : "/api/movimientos/{movimiento_id}/descartar", {
        params: { path: { movimiento_id: movimiento.id }, header: cabeceraCsrf() },
        headers: { "Content-Type": "application/json" },
      }));
      if (!montado.current) return;
      if (actual.current === origen && revision.current === turno) { setSeleccion(null); setResultado(respuesta); }
      await recargaActual.current(true);
    } catch (falla) {
      if (!montado.current) return;
      if (actual.current === origen && revision.current === turno) { setSeleccion(null); setError(textoFalla(falla)); }
      await recargaActual.current(true);
    } finally {
      enviando.current = false;
      if (montado.current) setMutando(false);
    }
  };
  // Cambiar un filtro (también entrar o salir de la bandeja, que no lleva mes)
  // no es cambiar de pantalla: el foco se queda en el filtro.
  const ultimoMes = useRef(mes);
  if (!bandeja && !descartados) ultimoMes.current = mes;
  return { mes, filtros, carga, recargar, sincronizacion, bandeja, descartados, enviando, seleccion, setSeleccion, mutando, setListaOcupada, resultado, setResultado, error, navegacionBloqueada, bloqueado, revisar, cambiarDescarte, ultimoMes };
}
