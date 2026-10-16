/** Registro de ingresos y ajuste de saldo. */
import type { Mensaje } from "./piezas";
import { TEXTOS } from "@/compartido/textos/textos";
import { Ayuda, Hoja, Nota } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { Etiqueta, Input } from "@/compartido/ui/ui/input";
import { ajustarSaldo, registrarIngreso } from "@/funcionalidades/saldo/cargar";
import { fechaElegidaEnFrase, leerMonto, paraCampoFechaHora, resultadoAjuste, revisarFechaHora, textoIngresoRegistrado, type Saldo as DatosSaldo } from "@/funcionalidades/saldo/datos";
import { useSesion } from "@/funcionalidades/sesion/sesion";
import { Plus, Scale } from "lucide-react";
import { useId, useRef, useState, type ReactNode } from "react";
import { CabezaHoja, Campo, ErrorCampo, Resultado } from "./piezas";

const T = TEXTOS.saldo;




// --- Registrar un ingreso ----------------------------------------------------------

export function RegistrarIngreso({ datos, alCambiar, alOcuparse }: { datos: DatosSaldo; alCambiar: () => Promise<void>; alOcuparse: (ocupado: boolean) => void }) {
  const t = T.registrar;
  const { cliente } = useSesion();
  const id = useId();
  const idMonto = useId();
  const idAyudaMonto = useId();
  const idErrorMonto = useId();
  const idFecha = useId();
  const idErrorFecha = useId();
  const idFechaEnFrase = useId();
  const idDescripcion = useId();
  const campoMonto = useRef<HTMLInputElement>(null);
  const campoFecha = useRef<HTMLInputElement>(null);
  const [monto, setMonto] = useState("");
  const [fecha, setFecha] = useState(() => paraCampoFechaHora(datos.ahora));
  const [descripcion, setDescripcion] = useState("");
  const [errorMonto, setErrorMonto] = useState<string | null>(null);
  const [errorFecha, setErrorFecha] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<Mensaje>(null);
  const [enviando, setEnviando] = useState(false);

  const enFrase = fechaElegidaEnFrase(fecha, datos.hoy);

  const enviar = async () => {
    setMensaje(null);
    const lectura = leerMonto(monto);
    const fallaFecha = revisarFechaHora(fecha, datos.fecha_hora_minima);
    setErrorMonto(lectura.tipo === "error" ? lectura.texto : null);
    setErrorFecha(fallaFecha);
    if (lectura.tipo === "error") {
      campoMonto.current?.focus();
      return;
    }
    if (fallaFecha) {
      campoFecha.current?.focus();
      return;
    }
    if (!datos.token_ingreso) {
      setMensaje({ tipo: "error", texto: T.sinToken });
      await alCambiar();
      return;
    }
    setEnviando(true);
    alOcuparse(true);
    try {
    const r = await registrarIngreso(cliente, {
      monto_centavos: lectura.centavos,
      fecha_hora: fecha,
      descripcion: descripcion.trim(),
      token: datos.token_ingreso,
    });
    if (r.tipo === "sin-sesion") return;
    if (r.tipo === "error") {
      setMensaje({ tipo: "error", texto: r.texto });
      // Ya se usó el token (409) o venció (400): se lee uno nuevo, y la lista,
      // por si el primero sí se guardó.
      if (r.estado === 409 || r.estado === 400) await alCambiar();
      return;
    }
    setMonto("");
    setDescripcion("");
    await alCambiar();
    setMensaje({ tipo: "exito", texto: textoIngresoRegistrado(r.datos.monto_centavos) });
    } finally {
      setEnviando(false);
      alOcuparse(false);
    }
  };

  return (
    <Hoja aria-labelledby={id}>
      <CabezaHoja id={id} titulo={t.titulo}>
        <Ayuda>{t.ayuda}</Ayuda>
      </CabezaHoja>
      <form
        noValidate
        className="flex flex-col gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          void enviar();
        }}
      >
        <Campo>
          <Etiqueta htmlFor={idMonto}>{t.monto}</Etiqueta>
          <Input
            ref={campoMonto}
            id={idMonto}
            inputMode="decimal"
            autoComplete="off"
            placeholder={t.ejemploMonto}
            className="font-montos text-lg"
            value={monto}
            aria-invalid={errorMonto ? true : undefined}
            aria-describedby={errorMonto ? `${idErrorMonto} ${idAyudaMonto}` : idAyudaMonto}
            onChange={(e) => {
              setMonto(e.target.value);
              setErrorMonto(null);
            }}
          />
          {errorMonto ? <ErrorCampo id={idErrorMonto}>{errorMonto}</ErrorCampo> : null}
          <Ayuda id={idAyudaMonto}>{t.ayudaMonto}</Ayuda>
        </Campo>
        <Campo>
          <Etiqueta htmlFor={idFecha}>{t.fecha}</Etiqueta>
          <Input
            ref={campoFecha}
            id={idFecha}
            type="datetime-local"
            value={fecha}
            min={datos.fecha_hora_minima ? paraCampoFechaHora(datos.fecha_hora_minima) : undefined}
            max={paraCampoFechaHora(datos.ahora)}
            aria-invalid={errorFecha ? true : undefined}
            aria-describedby={[errorFecha ? idErrorFecha : null, enFrase ? idFechaEnFrase : null].filter(Boolean).join(" ") || undefined}
            onChange={(e) => {
              setFecha(e.target.value);
              setErrorFecha(null);
            }}
          />
          {errorFecha ? <ErrorCampo id={idErrorFecha}>{errorFecha}</ErrorCampo> : null}
          {enFrase ? <Ayuda id={idFechaEnFrase}>{enFrase}</Ayuda> : null}
        </Campo>
        <Campo>
          <Etiqueta htmlFor={idDescripcion}>
            {t.descripcion} <span className="font-normal text-muted-foreground text-sm">{t.opcional}</span>
          </Etiqueta>
          <Input
            id={idDescripcion}
            autoComplete="off"
            placeholder={t.ejemploDescripcion}
            maxLength={datos.maximo_descripcion}
            value={descripcion}
            onChange={(e) => setDescripcion(e.target.value)}
          />
        </Campo>
        <div className="mt-1">
          <Button type="submit" disabled={enviando}>
            <Plus aria-hidden="true" className="size-5" />
            {enviando ? t.enCurso : t.boton}
          </Button>
        </div>
        <Resultado mensaje={mensaje} />
      </form>
    </Hoja>
  );
}


// --- Ajustar el saldo --------------------------------------------------------------

export function AjustarSaldo({
  alCambiar,
  alOcuparse,
  sincronizar,
  resultadoSincronizacion,
}: {
  alCambiar: () => Promise<void>;
  alOcuparse: (ocupado: boolean) => void;
  sincronizar: ReactNode;
  resultadoSincronizacion: Mensaje;
}) {
  const t = T.ajustar;
  const { cliente } = useSesion();
  const id = useId();
  const idCampo = useId();
  const idError = useId();
  const campo = useRef<HTMLInputElement>(null);
  const [valor, setValor] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<Mensaje>(null);
  const [enviando, setEnviando] = useState(false);

  const enviar = async () => {
    setMensaje(null);
    const lectura = leerMonto(valor, { permitirCero: true });
    if (lectura.tipo === "error") {
      setError(lectura.texto);
      campo.current?.focus();
      return;
    }
    setError(null);
    setEnviando(true);
    alOcuparse(true);
    try {
    const r = await ajustarSaldo(cliente, lectura.centavos);
    if (r.tipo === "sin-sesion") return;
    if (r.tipo === "error") {
      setMensaje({ tipo: "error", texto: r.texto });
      return;
    }
    setValor("");
    await alCambiar();
    setMensaje(resultadoAjuste(r.datos));
    } finally {
      setEnviando(false);
      alOcuparse(false);
    }
  };

  return (
    <Hoja aria-labelledby={id}>
      <CabezaHoja id={id} titulo={t.titulo}>
        <Ayuda>{t.ayuda}</Ayuda>
      </CabezaHoja>
      <div className="flex flex-col gap-(--espacio-grupo)">
        <div className="flex flex-col gap-3">
          <Nota acciones={sincronizar}>
            <p>{t.antes}</p>
          </Nota>
          <Resultado mensaje={resultadoSincronizacion} />
        </div>
        <form
          noValidate
          className="flex flex-col gap-5"
          onSubmit={(e) => {
            e.preventDefault();
            void enviar();
          }}
        >
          <Campo>
            <Etiqueta htmlFor={idCampo}>{t.campo}</Etiqueta>
            <Input
              ref={campo}
              id={idCampo}
              inputMode="decimal"
              autoComplete="off"
              className="font-montos text-lg"
              value={valor}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? idError : undefined}
              onChange={(e) => {
                setValor(e.target.value);
                setError(null);
              }}
            />
            {error ? <ErrorCampo id={idError}>{error}</ErrorCampo> : null}
          </Campo>
          <div className="mt-1">
            <Button type="submit" disabled={enviando}>
              <Scale aria-hidden="true" className="size-5" />
              {enviando ? t.enCurso : t.boton}
            </Button>
          </div>
          <Resultado mensaje={mensaje} />
        </form>
      </div>
    </Hoja>
  );
}
