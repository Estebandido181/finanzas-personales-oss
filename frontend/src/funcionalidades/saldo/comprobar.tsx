import { useLayoutEffect, useId, useRef, useState } from "react";
import { TriangleAlert } from "lucide-react";
import { cabeceraCsrf, type Esquemas } from "@/compartido/http/cliente";
import { Aviso, AvisoConTitulo, Ayuda, Hoja } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { Etiqueta, Input } from "@/compartido/ui/ui/input";
import { fechaYHora, hoyColombia, pesos } from "@/compartido/formatos/formato";
import { Monto } from "@/compartido/ui/cifras";
import { dato, FallaPeticion as FallaImportacion, textoFalla } from "@/compartido/http/dato";
import { useSesion } from "@/funcionalidades/sesion/sesion";
import { leerMonto } from "@/funcionalidades/saldo/datos";

type Comprobacion = Esquemas["ComprobacionSaldo"];
type Entrada = Esquemas["ComprobarSaldoEntrada"];

/** Composición funcional con las piezas de libreta existentes. El diagnóstico
 * nunca se persiste y solo el servidor calcula diferencias y cobertura. */
export function ComprobarSaldo({ contexto, token, tipo, deshabilitado = false, inicial = null, valorInicial = "", alInvalidar }: {
  contexto: unknown;
  token?: Entrada["token_analisis"];
  tipo?: Entrada["tipo_analisis"];
  deshabilitado?: boolean;
  inicial?: Comprobacion | null;
  valorInicial?: string;
  alInvalidar?: (estado: 409 | 410) => void;
}) {
  const { cliente } = useSesion();
  const id = useId();
  const [valor, setValor] = useState(valorInicial);
  const [resultado, setResultado] = useState<Comprobacion | null>(inicial);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [obsoleto, setObsoleto] = useState(false);
  const turno = useRef(0);
  const peticion = useRef<AbortController | null>(null);
  const anterior = useRef({ contexto, token, tipo, deshabilitado, inicial });
  useLayoutEffect(() => {
    // Cancela el contexto anterior antes de que la nueva vista habilite un
    // envío: un cleanup pasivo podría abortar esa petición recién iniciada.
    // El primer efecto puede llegar después de un envío válido. Solo un
    // cambio real invalida esa petición; el desmontaje siempre la cancela.
    const cambio = anterior.current.contexto !== contexto || anterior.current.token !== token || anterior.current.tipo !== tipo || anterior.current.deshabilitado !== deshabilitado || anterior.current.inicial !== inicial;
    if (cambio) {
      ++turno.current;
      peticion.current?.abort();
      setResultado(null);
      setError(null); setOcupado(false); setObsoleto(false);
    }
    anterior.current = { contexto, token, tipo, deshabilitado, inicial };
    return () => { ++turno.current; peticion.current?.abort(); };
  }, [contexto, token, tipo, deshabilitado, inicial]);

  async function comprobar() {
    if (ocupado || deshabilitado || obsoleto) return;
    setResultado(null); setError(null);
    const lectura = leerMonto(valor, { permitirCero: true });
    if (lectura.tipo === "error") { setError(lectura.texto); return; }
    const actual = ++turno.current;
    const controlador = new AbortController();
    peticion.current = controlador;
    setOcupado(true);
    try {
      const respuesta = await dato(cliente.POST("/api/saldo/comprobar", {
        params: { header: cabeceraCsrf() },
        body: { saldo_real_centavos: lectura.centavos, ...(token ? { token_analisis: token, tipo_analisis: tipo } : {}) },
        signal: controlador.signal,
      }));
      if (turno.current === actual) setResultado(respuesta);
    } catch (falla) {
      if (turno.current !== actual) return;
      const caducado = falla instanceof FallaImportacion && (falla.estado === 409 || falla.estado === 410);
      setObsoleto(caducado && !!token);
      setError(caducado && token ? "La revisión cambió o venció. Vuelve a analizar los archivos antes de comprobar." : textoFalla(falla));
      if (token && falla instanceof FallaImportacion && (falla.estado === 409 || falla.estado === 410)) alInvalidar?.(falla.estado);
    } finally {
      if (turno.current === actual) setOcupado(false);
    }
  }
  return <Hoja aria-labelledby={`${id}-titulo`}>
    <h2 id={`${id}-titulo`}>Comprobar saldo</h2>
    <form className="mt-4 space-y-4" noValidate onSubmit={(e) => { e.preventDefault(); void comprobar(); }}>
      <div className="space-y-2">
        <Etiqueta htmlFor={id}>Escribe el saldo que ves ahora en Bancolombia</Etiqueta>
        <Input id={id} inputMode="decimal" autoComplete="off" className="font-montos text-lg" value={valor}
          disabled={deshabilitado || ocupado || obsoleto} aria-invalid={!!error} aria-describedby={`${id}-ayuda${error ? ` ${id}-error` : ""}`}
          onChange={(e) => { ++turno.current; peticion.current?.abort(); setValor(e.target.value); setResultado(null); setError(null); }} />
        <Ayuda id={`${id}-ayuda`}>Punto para los miles y coma para los centavos. La hora se registra al comprobar. Esto no cambia tu saldo ni crea un ajuste.</Ayuda>
      </div>
      <Button type="submit" disabled={deshabilitado || ocupado || obsoleto}>{ocupado ? "Comprobando…" : "Comprobar saldo"}</Button>
      {ocupado ? <p role="status">Comparando con el saldo de la app…</p> : null}
      {error ? <div id={`${id}-error`}><Aviso tipo="error">{error}</Aviso></div> : null}
      {resultado && !deshabilitado ? <DiagnosticoSaldo resultado={resultado} /> : null}
    </form>
  </Hoja>;
}

function Cifra({ titulo, valor, signo = false }: { titulo: string; valor: number | null; signo?: boolean }) {
  return valor === null ? null : <div className="flex flex-col gap-2 computador:flex-row computador:justify-between computador:gap-3">
    <span>{titulo}</span><Monto>{pesos(valor, { conSigno: signo })}</Monto>
  </div>;
}

export function DiagnosticoSaldo({ resultado: r }: { resultado: Comprobacion }) {
  const id = useId();
  return <div className="mt-4 space-y-4" role="status">
    <Ayuda>Recibido por la app el {fechaYHora(r.recibido_en, hoyColombia())}. Es la hora de recepción del saldo que escribiste; la app no consultó el banco.</Ayuda>
    {r.estado === "sin_configuracion" ? <Aviso tipo="info">Configura primero tu saldo para poder compararlo.</Aviso> : <>
      <div className="space-y-3">
        <Cifra titulo="Saldo que escribiste del banco" valor={r.saldo_real_centavos} />
        <Cifra titulo={r.origen === "actual" ? "Saldo actual en la app" : "Saldo de la app después de confirmar"} valor={r.saldo_app_centavos} />
        <Cifra titulo="Diferencia: banco menos app" valor={r.diferencia_centavos} signo />
      </div>
      <Aviso tipo="info">{!r.verificacion_independiente || r.diferencia_forzada_por_inicial
        ? "El saldo inicial se calculó a partir del saldo que escribiste. Esta coincidencia no es una comprobación independiente."
        : r.coincide ? "Los saldos coinciden en esta comprobación. Esto no garantiza que estén todos los movimientos."
        : "Los saldos tienen una diferencia. La app no la ajustó ni atribuyó a intereses o redondeos."}</Aviso>
      {r.origen !== "actual" ? <div className="space-y-3">
        <Cifra titulo="Saldo de la app antes de confirmar" valor={r.saldo_antes_centavos} />
        <Cifra titulo="Saldo de la app después de confirmar" valor={r.saldo_despues_centavos} />
        <Cifra titulo="Impacto de esta importación" valor={r.efecto_conciliacion_centavos} signo />
        <Cifra titulo="Resto sin explicar" valor={r.resto_no_explicado_centavos} signo />
        {r.contribuciones ? <details><summary className="min-h-(--tactil-min) cursor-pointer font-medio">Ver qué cambia el saldo</summary><div className="mt-3 space-y-3">
          <Cifra titulo="Movimientos agregados" valor={r.contribuciones.agregados_centavos} signo />
          <Cifra titulo="Montos corregidos" valor={r.contribuciones.corregidos_centavos} signo />
          <Cifra titulo="Cambios en ajustes" valor={r.contribuciones.ajustes_centavos} signo />
          <Cifra titulo="Cambio del saldo inicial" valor={r.contribuciones.cambio_inicial_centavos} signo />
          <Cifra titulo="Otros cambios" valor={r.contribuciones.otros_centavos} signo />
        </div></details> : null}
      </div> : null}
      {r.desglose_despues ? <details><summary className="min-h-(--tactil-min) cursor-pointer font-medio">Ver el desglose del saldo comparado</summary><div className="mt-3 space-y-3">
        <Cifra titulo="Saldo inicial" valor={r.desglose_despues.saldo_inicial_centavos} />
        <Cifra titulo="Ingresos" valor={r.desglose_despues.ingresos_centavos} />
        <Cifra titulo="Gastos" valor={r.desglose_despues.gastos_centavos} />
        <Cifra titulo="Ajustes" valor={r.desglose_despues.ajustes_centavos} signo />
      </div></details> : null}
    </>}
    <Ayuda>{r.pendientes.preguntas} preguntas pendientes; {r.pendientes.no_en_banco} movimientos por revisar que no están en el banco; {r.pendientes.sin_categoria} sin categorizar.</Ayuda>
    <AvisoConTitulo tipo="advertencia" icono={TriangleAlert} titulo="Revisa la cobertura" idTitulo={id}>{r.cobertura.advertencia}</AvisoConTitulo>
    <Ayuda>Si cambió el saldo del banco o respondiste una pregunta, comprueba otra vez con el saldo que ves ahora.</Ayuda>
  </div>;
}
