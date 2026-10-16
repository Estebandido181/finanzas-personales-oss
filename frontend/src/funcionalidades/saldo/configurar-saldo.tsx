/**
 * Configurar saldo (ítem 16): saldo inicial y fecha de inicio. Sigue los
 * prototipos aprobados (diseno/prototipo/configurar-saldo.html, -error.html y
 * -fijo.html) y TEXTOS.md, "Configurar saldo".
 *
 * - Formulario: "Saldo inicial en pesos" y "Fecha de inicio". Los errores de
 *   campo (vacío, letra O, fecha futura) se revisan antes de enviar y van
 *   debajo de cada campo; lo que rechace la API, en un aviso bajo el botón.
 * - Fijo: si ya hay movimientos, la hoja es de solo lectura y un aviso lleva
 *   a "Ajustar el saldo" (/app/saldo). Cómo se sabe: `estadoConfiguracion`.
 *
 * El monto se pasa a centavos como texto (`leerSaldoInicial`), sin floats; el
 * envío lleva el token CSRF (`configurarSaldo`).
 */
import { CircleAlert, Scale, Wallet, WifiOff } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Link } from "wouter";
import { Aviso, Ayuda, Hoja, Nota, Vacio } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { Etiqueta, Input } from "@/compartido/ui/ui/input";
import { pesos } from "@/compartido/formatos/formato";
import { Monto } from "@/compartido/ui/cifras";
import { configurarSaldo, useDatosSaldo } from "@/funcionalidades/saldo/cargar";
import {
  estadoConfiguracion,
  fechaConAnio,
  leerSaldoInicial,
  revisarFechaInicio,
  textoSaldoFijo,
  textoSaldoInicialGuardado,
  type Configuracion,
  type EstadoConfiguracion,
} from "@/funcionalidades/saldo/datos";
import { useSesion } from "@/funcionalidades/sesion/sesion";
import { TEXTOS } from "@/compartido/textos/textos";
import { Encabezado, Pila } from "@/compartido/ui/pantalla";
import { Campo, Cargando, ErrorCampo, FilaCifra } from "@/funcionalidades/saldo/saldo";

const T = TEXTOS.saldo.configurar;

export function ConfigurarSaldo() {
  const { cliente } = useSesion();
  const { carga, recargar } = useDatosSaldo(cliente);
  // La API rechazó el guardado: si al volver a leer quedó fija, el foco va al aviso.
  const rechazado = useRef(false);

  return (
    <Pila>
      <Encabezado titulo={T.titulo} debajo={<Ayuda>{T.ayuda}</Ayuda>} />
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
      ) : (
        <Contenido
          estado={estadoConfiguracion(carga.datos)}
          hoy={carga.datos.hoy}
          alRechazar={async () => {
            rechazado.current = true;
            await recargar(true);
          }}
          rechazado={rechazado.current}
        />
      )}
    </Pila>
  );
}

function Contenido({
  estado,
  hoy,
  alRechazar,
  rechazado,
}: {
  estado: EstadoConfiguracion;
  hoy: string;
  alRechazar: () => Promise<void>;
  rechazado: boolean;
}) {
  if (estado.tipo === "fijo") return <Fijo configuracion={estado.configuracion} enfocar={rechazado} />;
  return <Formulario inicial={estado.inicial} hoy={hoy} alRechazar={alRechazar} />;
}

type Mensaje = { tipo: "exito" | "error"; texto: string } | null;

function Formulario({
  inicial,
  hoy,
  alRechazar,
}: {
  inicial: { monto: string; fecha: string };
  hoy: string;
  /** La API dijo que no: se vuelve a leer, por si ya hay movimientos (pasa a "fijo"). */
  alRechazar: () => Promise<void>;
}) {
  const { cliente } = useSesion();
  const id = useId();
  const idMonto = useId();
  const idAyudaMonto = useId();
  const idErrorMonto = useId();
  const idFecha = useId();
  const idAyudaFecha = useId();
  const idErrorFecha = useId();
  const campoMonto = useRef<HTMLInputElement>(null);
  const campoFecha = useRef<HTMLInputElement>(null);
  const [monto, setMonto] = useState(inicial.monto);
  const [fecha, setFecha] = useState(inicial.fecha);
  const [errorMonto, setErrorMonto] = useState<string | null>(null);
  const [errorFecha, setErrorFecha] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<Mensaje>(null);
  const [enviando, setEnviando] = useState(false);

  const enviar = async () => {
    setMensaje(null);
    const lectura = leerSaldoInicial(monto);
    const fallaFecha = revisarFechaInicio(fecha, hoy);
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
    setEnviando(true);
    const r = await configurarSaldo(cliente, { saldo_inicial_centavos: lectura.centavos, fecha_inicio: fecha });
    if (r.tipo === "sin-sesion") return;
    setEnviando(false);
    if (r.tipo === "ok") {
      setMensaje({ tipo: "exito", texto: textoSaldoInicialGuardado(r.datos) });
      return;
    }
    setMensaje({ tipo: "error", texto: r.texto });
    // Pudo entrar un movimiento con la pantalla abierta: con datos nuevos, la
    // pantalla pasa a "fijo" (si no, el aviso de error se queda bajo el botón).
    if (r.estado === 400 || r.estado === 409) await alRechazar();
  };

  return (
    <Hoja aria-labelledby={id}>
      <h2 id={id}>{T.puntoDePartida}</h2>
      <form
        noValidate
        className="flex flex-col gap-5 mt-(--espacio-grupo)"
        onSubmit={(e) => {
          e.preventDefault();
          void enviar();
        }}
      >
        <Campo>
          <Etiqueta htmlFor={idMonto}>{T.monto}</Etiqueta>
          <Input
            ref={campoMonto}
            id={idMonto}
            inputMode="decimal"
            autoComplete="off"
            placeholder={T.ejemploMonto}
            className="font-montos text-lg"
            value={monto}
            aria-invalid={errorMonto ? true : undefined}
            aria-describedby={errorMonto ? `${idAyudaMonto} ${idErrorMonto}` : idAyudaMonto}
            onChange={(e) => {
              setMonto(e.target.value);
              setErrorMonto(null);
            }}
          />
          <Ayuda id={idAyudaMonto}>{T.ayudaMonto}</Ayuda>
          {errorMonto ? <ErrorCampo id={idErrorMonto}>{errorMonto}</ErrorCampo> : null}
        </Campo>
        <Campo>
          <Etiqueta htmlFor={idFecha}>{T.fecha}</Etiqueta>
          <Input
            ref={campoFecha}
            id={idFecha}
            type="date"
            max={hoy}
            value={fecha}
            aria-invalid={errorFecha ? true : undefined}
            aria-describedby={errorFecha ? `${idAyudaFecha} ${idErrorFecha}` : idAyudaFecha}
            onChange={(e) => {
              setFecha(e.target.value);
              setErrorFecha(null);
            }}
          />
          <Ayuda id={idAyudaFecha}>{T.ayudaFecha}</Ayuda>
          {errorFecha ? <ErrorCampo id={idErrorFecha}>{errorFecha}</ErrorCampo> : null}
        </Campo>
        <div className="mt-1">
          <Button type="submit" disabled={enviando}>
            <Wallet aria-hidden="true" className="size-5" />
            {enviando ? T.enCurso : T.boton}
          </Button>
        </div>
        {mensaje ? <Aviso tipo={mensaje.tipo}>{mensaje.texto}</Aviso> : null}
      </form>
    </Hoja>
  );
}

/**
 * Ya hay movimientos: solo lectura y el camino para corregir (un ajuste).
 * `enfocar`: llegó aquí porque la API rechazó el guardado (el botón ya no
 * existe), así que el foco pasa al aviso.
 */
function Fijo({ configuracion, enfocar }: { configuracion: Configuracion | null; enfocar: boolean }) {
  const id = useId();
  const aviso = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (enfocar) aviso.current?.focus();
  }, [enfocar]);
  if (configuracion === null) {
    // Movimientos sin saldo configurado: no hay cifras ni a qué ajustar.
    return (
      <Nota>
        <p className="font-fuerte">{T.fijoTitulo}</p>
      </Nota>
    );
  }
  return (
    <>
      <Hoja aria-labelledby={id}>
        <h2 id={id}>{T.puntoDePartida}</h2>
        <div className="flex flex-col gap-3 mt-(--espacio-grupo)">
          <FilaCifra nombre={T.saldoInicial}>
            <Monto>{pesos(configuracion.saldo_inicial_centavos)}</Monto>
          </FilaCifra>
          <FilaCifra nombre={T.fecha}>
            <span>{fechaConAnio(configuracion.fecha_inicio)}</span>
          </FilaCifra>
        </div>
      </Hoja>
      <div ref={aviso} tabIndex={-1} className="focus:outline-none">
        <Nota
          acciones={
            <Button asChild>
              <Link href="/saldo">
                <Scale aria-hidden="true" className="size-5" />
                {T.ajustar}
              </Link>
            </Button>
          }
        >
          <p className="font-fuerte">{T.fijoTitulo}</p>
          <p>{textoSaldoFijo(configuracion.fecha_inicio)}</p>
        </Nota>
      </div>
    </>
  );
}
