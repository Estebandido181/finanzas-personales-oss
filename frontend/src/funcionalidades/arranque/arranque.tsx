import { useEffect, useRef, useState, useCallback } from "react";
import { Link, useLocation } from "wouter";
import { Check, Plus, X, TriangleAlert } from "lucide-react";
import { cabeceraCsrf, type Esquemas } from "@/compartido/http/cliente";
import { Aviso, AvisoConTitulo, Ayuda, Hoja, Nota } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { Input } from "@/compartido/ui/ui/input";
import { Dialogo } from "@/compartido/ui/ui/dialogo";
import { Monto, SubrayadoDoble } from "@/compartido/ui/cifras";
import { pesos, fechaEnFrase, hoyColombia } from "@/compartido/formatos/formato";
import { Pila } from "@/compartido/ui/pantalla";
import { useSesion } from "@/funcionalidades/sesion/sesion";
import { leerMonto, RUTA_CONFIGURAR } from "@/funcionalidades/saldo/datos";
import { MIME_EXCEL } from "@/pwa/compartir";
import { dato, textoFalla, FallaPeticion as FallaImportacion } from "@/compartido/http/dato";
import { useCarga } from "@/compartido/http/carga";
import { ArchivoElegido, CabeceraImportacion, ConteoImportacion, PasosDelBanco } from "@/funcionalidades/importaciones/piezas";
import { PorResolver } from "@/funcionalidades/importaciones/detalle";
import { ComprobarSaldo, DiagnosticoSaldo } from "@/funcionalidades/saldo/comprobar";

const fecha = (valor: string) => fechaEnFrase(valor, hoyColombia());

/** Los archivos y el cálculo viven en el servidor. Solo el nombre elegido
 * se conserva en memoria para presentar la lista, sin guardar el contenido. */
export function ArranqueBanco({ extension = false }: { extension?: boolean }) {
  const { cliente } = useSesion();
  const [, navegar] = useLocation();
  const [archivos, setArchivos] = useState<Esquemas["ArchivosHistorial"] | null>(null);
  const [nombres, setNombres] = useState<string[]>([]);
  const [saldo, setSaldo] = useState("");
  const [vista, setVista] = useState<Esquemas["VistaPreviaArranque"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [vencido, setVencido] = useState(false);
  const entrada = useRef<HTMLInputElement>(null);
  const obtenerEstado = useCallback(() => dato(cliente.GET("/api/arranque/estado")), [cliente]);
  const estado = useCarga(obtenerEstado);
  const montado = useRef(true);
  function vencer() {
    setArchivos(null); setNombres([]); setVista(null); setVencido(true);
  }
  function invalidarComprobacion(estado: 409 | 410) {
    setError("La revisión cambió o venció. Revisa los archivos antes de calcular otra vez.");
    if (estado === 410) vencer(); else setVista(null);
  }
  useEffect(() => { montado.current = true; return () => { montado.current = false; }; }, []);
  useEffect(() => {
    if (!archivos && !vista) return;
    const reloj = setTimeout(vencer, (vista?.segundos ?? archivos!.segundos) * 1000);
    return () => clearTimeout(reloj);
  }, [archivos, vista]);
  async function actuar(texto: string, accion: () => Promise<void>) {
    if (ocupado) return;
    setOcupado(texto); setError(null);
    try { await accion(); }
    catch (falla) {
      if (montado.current) {
        setError(textoFalla(falla));
        if (falla instanceof FallaImportacion && falla.estado === 409) setVista(null);
        if (falla instanceof FallaImportacion && falla.estado === 410) vencer();
      }
    }
    finally { if (montado.current) setOcupado(null); }
  }
  async function agregar(archivo: File) {
    await actuar("Leyendo el archivo…", async () => {
      const lista = await dato(cliente.POST("/api/arranque/archivos", {
        params: { header: { ...cabeceraCsrf(), "x-nombre-archivo": encodeURIComponent(archivo.name), ...(archivos && !vencido ? { "x-historial-token": archivos.token } : {}) } },
        headers: { "Content-Type": MIME_EXCEL }, body: "", bodySerializer: () => archivo,
      }));
      if (!montado.current) return;
      // El servidor renumera la lista tras quitar: los nombres siguen el orden
      // de los archivos enviados y no se asocian con un ID persistente.
      setNombres((prev) => [...(vencido ? [] : prev), archivo.name]);
      setArchivos(lista); setVista(null); setVencido(false);
    });
  }
  async function quitar(id: number) {
    if (!archivos) return;
    await actuar("Quitando el archivo…", async () => {
      const lista = await dato(cliente.DELETE("/api/arranque/archivos/{archivo_id}", {
        params: { header: cabeceraCsrf(), path: { archivo_id: id } }, body: { token: archivos.token },
      }));
      if (montado.current) {
        const indice = archivos.archivos.findIndex((a) => a.id === id);
        setNombres((prev) => prev.filter((_, i) => i !== indice));
        setArchivos(lista); setVista(null); setVencido(false);
      }
    });
  }
  async function calcular() {
    if (!archivos || vencido) return;
    const monto = extension && !saldo.trim() ? { tipo: "ok" as const, centavos: 0 } : leerMonto(saldo, { permitirCero: true });
    if (monto.tipo === "error") { setError(monto.texto); return; }
    await actuar("Calculando el saldo inicial y leyendo Gmail…", async () => {
      const previa = await dato(cliente.POST("/api/arranque/calcular", {
        params: { header: cabeceraCsrf() },
        body: { token: archivos.token, modo: extension ? "extension" : "arranque", saldo_actual_centavos: extension ? 0 : monto.centavos, ...(extension && saldo.trim() ? { saldo_real_centavos: monto.centavos } : {}) },
      }));
      if (montado.current) { setVista(previa); setVencido(false); }
    });
  }
  async function confirmar() {
    if (!vista || vencido) return;
    await actuar(extension ? "Extendiendo el historial…" : "Preparando tu historial…", async () => {
      const resultado = await dato(cliente.POST("/api/arranque/confirmar", {
        params: { header: cabeceraCsrf() }, body: { token: vista.token },
      }));
      if (montado.current) navegar(`/arranque/${resultado.importacion.id}`);
    });
  }
  async function cambiar() {
    if (!vista) return;
    await actuar("Descartando el cálculo…", async () => {
      await dato(cliente.DELETE("/api/arranque/analisis", { params: { header: cabeceraCsrf() }, body: { token: vista.token } }));
      if (montado.current) setVista(null);
    });
  }
  async function descartar() {
    if (!archivos) return;
    await actuar("Descartando los archivos…", async () => {
      if (!vencido) await dato(cliente.DELETE("/api/arranque/archivos", { params: { header: cabeceraCsrf() }, body: { token: archivos.token } }));
      if (montado.current) { setArchivos(null); setNombres([]); setVista(null); setVencido(false); }
    });
  }
  if (estado.carga.tipo === "cargando") return <Pila><CabeceraImportacion titulo={extension ? "Extender historial hacia atrás" : "Empieza con tu historial del banco"} /><p role="status">Cargando…</p></Pila>;
  if (estado.carga.tipo === "error") return <Pila><CabeceraImportacion titulo="Historial del banco" /><Aviso tipo="error">{estado.carga.mensaje}</Aviso><Button onClick={() => void estado.recargar()}>Volver a intentar</Button></Pila>;
  if (!(extension ? estado.carga.datos.puede_extender_historial : estado.carga.datos.puede_iniciar_arranque)) return <Pila><CabeceraImportacion titulo="Historial del banco" /><Nota><p>{extension ? "Configura primero tu saldo para extender el historial." : "Ya tienes movimientos registrados. Para agregar meses anteriores, extiende el historial."}</p></Nota><Button asChild><Link href={extension ? "/" : "/extender-historial"}>{extension ? "Volver al inicio" : "Extender historial"}</Link></Button></Pila>;
  return <Pila>
    <CabeceraImportacion titulo={vista ? "Revisa tu saldo inicial" : extension ? "Extender historial hacia atrás" : "Empieza con tu historial del banco"}
      ayuda={vista ? "Así sale el saldo inicial según lo que movió el banco y los avisos del mismo periodo." : extension ? "Sube los meses anteriores a tu fecha de inicio. La app junta los archivos sin repetir movimientos y conserva tu saldo actual." : "Sube el Excel de un mes del banco, agrega los que quieras y escribe tu saldo actual. La app calcula con qué saldo empezaste y junta los avisos de Gmail con lo del banco."} />
    {error ? <Aviso tipo="error">{error}</Aviso> : null}
    {ocupado ? <Aviso tipo="info">{ocupado} Todavía no cierres esta pantalla.</Aviso> : null}
    {vencido ? <Aviso tipo="info">La revisión venció. Elige los archivos otra vez antes de confirmar.</Aviso> : null}
    {vista ? <>
      <Hoja aria-labelledby="calculo-inicial"><h2 id="calculo-inicial">Así sale tu saldo inicial</h2>
        <p className="mt-4 text-muted-foreground">Saldo inicial calculado, al comenzar el {fecha(vista.fecha_inicio_propuesta)}</p>
        <p className="mt-3"><SubrayadoDoble><Monto className="text-3xl">{pesos(vista.saldo_inicial_centavos)}</Monto></SubrayadoDoble></p>
        <div className="mt-4 space-y-3">
          <Fila titulo="Saldo actual" centavos={vista.saldo_actual_centavos} />
          <Fila titulo={`Menos ingresos del ${fecha(vista.desde)} al ${fecha(vista.hasta)}`} centavos={vista.ingresos_centavos} />
          <Fila titulo="Más gastos de ese periodo" centavos={vista.gastos_centavos} />
          <Fila titulo="Otros movimientos del periodo" centavos={vista.otros_movimientos_netos_centavos} />
          <Ayuda>{vista.explicacion_otros_movimientos}</Ayuda>
          {vista.fecha_inicio_anterior ? <Ayuda>Tu fecha de inicio anterior era {fecha(vista.fecha_inicio_anterior)}{vista.saldo_inicial_anterior_centavos !== null ? `, con saldo inicial ${pesos(vista.saldo_inicial_anterior_centavos)}` : ""}.</Ayuda> : null}
          <Fila titulo="Tu saldo quedará en" centavos={vista.saldo_despues_centavos} />
        </div>
      </Hoja>
      {extension ? <ComprobarSaldo contexto={vista} token={vista.token} tipo="arranque" deshabilitado={!!ocupado || vencido} inicial={vista.comprobacion_saldo} valorInicial={saldo} alInvalidar={invalidarComprobacion} />
        : vista.comprobacion_saldo && !vencido && !ocupado ? <Hoja><h2>Saldo usado para empezar</h2><DiagnosticoSaldo resultado={vista.comprobacion_saldo} /></Hoja>
        : <Nota><p>El saldo inicial se calculó a partir del saldo que escribiste. Que el cálculo llegue a ese saldo no es una comprobación independiente.</p></Nota>}
      <AvisoConTitulo tipo={vista.cobertura_verificada ? "exito" : "advertencia"} icono={vista.cobertura_verificada ? Check : TriangleAlert} titulo="Revisa la cobertura del periodo" idTitulo="cobertura-arranque"><p>{vista.advertencia_cobertura}</p>
        {vista.huecos.map((h, i) => <p key={i}>Revisa el periodo del {fecha(h.desde)} al {fecha(h.hasta)}.</p>)}
      </AvisoConTitulo>
      <Nota><p>{vista.filas} movimientos del banco; {vista.filas_solapadas} filas solapadas entre archivos. Se leyeron {vista.correos_leidos} correos del mismo periodo.</p><p>{vista.sin_categoria} movimientos sin categorizar y {vista.preguntas_pendientes} preguntas para revisar después.</p></Nota>
      <div className="flex flex-col gap-3 computador:flex-row">
        <Button disabled={!!ocupado || vencido} onClick={() => void confirmar()}>{extension ? "Extender con este saldo inicial" : "Empezar con este saldo inicial"}</Button>
        <Button variant="outline" disabled={!!ocupado} onClick={() => void cambiar()}>Cambiar archivos o saldo</Button>
      </div>
    </> : <>
      <Hoja aria-labelledby="archivos-arranque"><h2 id="archivos-arranque">1. Excel del banco</h2>
        <Ayuda className="mt-4">Un archivo a la vez. Revisa que cada descarga cubra el periodo que elegiste. Haz que cada descarga empiece el último día de la anterior: el primer día de cada archivo puede venir incompleto. La app los junta sin repetir movimientos.</Ayuda>
        <ul className="mt-4 divide-y divide-renglon">{archivos?.archivos.map((a, indice) => <li key={a.id} className="py-(--espacio-fila) space-y-3">
          <ArchivoElegido nombre={nombres[indice] ?? `Archivo ${a.id}`} />
          <Ayuda>Leído · {a.filas} movimientos{a.desde && a.hasta ? `, del ${fecha(a.desde)} al ${fecha(a.hasta)}` : ""}.</Ayuda>
          <Button variant="ghost" aria-label={`Quitar ${nombres[indice] ?? `archivo ${a.id}`}`} disabled={!!ocupado || vencido} onClick={() => void quitar(a.id)}><X className="size-5" aria-hidden="true" />Quitar</Button>
        </li>)}</ul>
        {!archivos?.archivos.length ? <Ayuda className="mt-4">Todavía no has agregado archivos. Elige el Excel de un mes para empezar.</Ayuda> : null}
        <input ref={entrada} type="file" className="sr-only" aria-label="Archivo Excel del banco" accept={`.xlsx,${MIME_EXCEL}`} disabled={!!ocupado} onChange={(e) => { const archivo = e.currentTarget.files?.[0]; e.currentTarget.value = ""; if (archivo) void agregar(archivo); }} />
        <Button className="mt-4" variant="outline" disabled={!!ocupado} onClick={() => entrada.current?.click()}><Plus aria-hidden="true" className="size-5" />{archivos?.archivos.length && !vencido ? "Agregar otro archivo" : "Elegir archivo"}</Button>
        {archivos ? <Button className="mt-4" variant="ghost" disabled={!!ocupado} onClick={() => void descartar()}>Descartar archivos</Button> : null}
      </Hoja>
      <Hoja aria-labelledby="saldo-arranque"><h2 id="saldo-arranque">{extension ? "2. Revisar el historial" : "2. Saldo actual"}</h2>
        <form className="mt-4 space-y-4" onSubmit={(e) => { e.preventDefault(); void calcular(); }}>
          <div className="space-y-2"><label htmlFor="saldo-actual-arranque" className="font-medio">Escribe el saldo que ves ahora en Bancolombia{extension ? " (opcional)" : ""}</label><Input id="saldo-actual-arranque" inputMode="decimal" autoComplete="off" value={saldo} onChange={(e) => setSaldo(e.target.value)} aria-describedby="ayuda-saldo-arranque" disabled={!!ocupado} /><Ayuda id="ayuda-saldo-arranque">Punto para los miles y coma para los centavos. {extension ? "Se usa para comprobar la diferencia; el servidor conserva tu saldo actual al incorporar el pasado." : "Se usa como referencia para calcular el saldo inicial."} La hora se registra al calcular.</Ayuda></div>
          <Button type="submit" disabled={!!ocupado || vencido || !archivos?.puede_calcular}>Calcular saldo inicial</Button>
        </form>
        {!extension ? <Button asChild variant="ghost" className="mt-4"><Link href={RUTA_CONFIGURAR}>Prefiero empezar sin historial del banco</Link></Button> : null}
      </Hoja>
      <PasosDelBanco />
    </>}
  </Pila>;
}

function Fila({ titulo, centavos }: { titulo: string; centavos: number }) {
  return <div className="flex flex-wrap justify-between gap-3"><span>{titulo}</span><Monto>{pesos(centavos)}</Monto></div>;
}

export function ResultadoArranqueBanco({ id }: { id: number }) {
  const { cliente } = useSesion();
  const obtener = useCallback(() => dato(cliente.GET("/api/arranque/{importacion_id}", { params: { path: { importacion_id: id } } })), [cliente, id]);
  const { carga, recargar } = useCarga(obtener);
  const [dialogo, setDialogo] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resultado = carga.tipo === "listo" ? carga.datos : null;
  const deshacer = async () => {
    setOcupado(true); setError(null);
    try {
      await dato(cliente.POST("/api/arranque/{importacion_id}/deshacer", { params: { path: { importacion_id: id }, header: cabeceraCsrf() }, headers: { "Content-Type": "application/json" } }));
      setDialogo(false); await recargar();
    } catch (falla) { setError(textoFalla(falla)); } finally { setOcupado(false); }
  };
  return <Pila>
    <CabeceraImportacion titulo={resultado?.fase === "deshecho" ? "Historial restaurado" : "Tu historial del banco"} />
    {carga.tipo === "cargando" ? <p role="status">Cargando…</p> : carga.tipo === "error" ? <Aviso tipo="error">{carga.mensaje}<Button className="mt-3" onClick={() => void recargar()}>Volver a intentar</Button></Aviso> : resultado ? <>
      <Aviso tipo="exito">{resultado.fase === "deshecho" ? "Se deshizo la importación y se restauró la configuración anterior." : `Tu historial empieza el ${fecha(resultado.fecha_inicio!)}.`}</Aviso>
      {error ? <Aviso tipo="error">{error}</Aviso> : null}
      <Hoja><h2>Qué pasó</h2><ul className="mt-4"><ConteoImportacion icono={Plus} titulo="Agregados" ayuda="Movimientos que faltaban." cantidad={resultado.importacion.resumen.agregados} /><ConteoImportacion icono={Check} titulo="Ya estaban" ayuda="No se repitieron." cantidad={resultado.importacion.resumen.ya_estaban} /></ul>
        {resultado.saldo_inicial_centavos !== null ? <Fila titulo="Saldo inicial" centavos={resultado.saldo_inicial_centavos} /> : null}
        {resultado.importacion.saldo_centavos !== null ? <Fila titulo="Saldo actual" centavos={resultado.importacion.saldo_centavos} /> : null}
        <div className="flex flex-wrap gap-3 mt-4"><Button asChild><Link href="/">Volver al inicio</Link></Button>{resultado.importacion.se_puede_deshacer ? <Button variant="outline" onClick={() => setDialogo(true)}>Deshacer importación</Button> : resultado.importacion.motivo_no_deshacer ? <Ayuda>{resultado.importacion.motivo_no_deshacer}</Ayuda> : null}</div>
      </Hoja>
      <ComprobarSaldo contexto={resultado} deshabilitado={ocupado} />
      {resultado.fase !== "deshecho" && !resultado.importacion.todo_resuelto ? <PorResolver importacion={resultado.importacion} rutaCategorizar={`/arranque/${id}/categorizar`} /> : null}
      {dialogo ? <Dialogo titulo="Deshacer importación" descripcion="Se restauran los movimientos, el saldo inicial y la fecha de inicio anteriores a esta importación." alCerrar={() => { if (!ocupado) setDialogo(false); }} acciones={<><Button variant="outline" disabled={ocupado} onClick={() => setDialogo(false)}>Cancelar</Button><Button disabled={ocupado} onClick={() => void deshacer()}>{ocupado ? "Deshaciendo…" : "Deshacer importación"}</Button></>}>{error ? <Aviso tipo="error">{error}</Aviso> : null}</Dialogo> : null}
    </> : null}
  </Pila>;
}
