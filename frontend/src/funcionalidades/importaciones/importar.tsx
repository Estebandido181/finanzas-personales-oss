import { Check, Plus, Pencil, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "wouter";
import { Aviso, Ayuda, Hoja, Nota } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { cabeceraCsrf, type Esquemas } from "@/compartido/http/cliente";
import { pesos, fechaEnFrase, hoyColombia } from "@/compartido/formatos/formato";
import { Monto, SubrayadoDoble } from "@/compartido/ui/cifras";
import { useSesion } from "@/funcionalidades/sesion/sesion";
import { Pila } from "@/compartido/ui/pantalla";
import {
  ArchivoElegido,
  CabeceraImportacion,
  ConteoImportacion,
} from "@/funcionalidades/importaciones/piezas";
import { ElegirExcel } from "@/funcionalidades/importaciones/elegir-excel";
import { dato, FallaPeticion as FallaImportacion, textoFalla } from "@/compartido/http/dato";
import { MIME_EXCEL, tomarArchivoCompartido } from "@/pwa/compartir";
import { ComprobarSaldo } from "@/funcionalidades/saldo/comprobar";

type Vista = Esquemas["VistaPreviaImportacion"];
type Fase = "elegir" | "analizando" | "previa" | "importando" | "revisar";
export function ImportarBanco({
  compartido = false,
}: {
  compartido?: boolean;
}) {
  const { cliente } = useSesion();
  const [, navegar] = useLocation();
  const [archivo, setArchivo] = useState<File | null>(null);
  const [vista, setVista] = useState<Vista | null>(null);
  const [fase, setFase] = useState<Fase>("elegir");
  const [error, setError] = useState<string | null>(null);
  const [vencido, setVencido] = useState(false);
  const [descartando, setDescartando] = useState(false);
  const peticion = useRef<AbortController | null>(null);
  const montado = useRef(true);
  const compartidoPedido = useRef(false);
  const invalidarComprobacion = () => {
    setVencido(true);
    setError("La revisión cambió o venció. Vuelve a analizar el archivo antes de importar.");
  };
  useEffect(() => {
    montado.current = true;
    return () => {
      montado.current = false;
      peticion.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (!vista) return;
    setVencido(false);
    const reloj = setTimeout(() => setVencido(true), vista.segundos * 1000);
    return () => clearTimeout(reloj);
  }, [vista]);
  const analizar = async (elegido = archivo, aviso: string | null = null) => {
    if (!elegido) return;
    setError(aviso);
    setVista(null);
    setFase("analizando");
    const controlador = new AbortController();
    peticion.current?.abort();
    peticion.current = controlador;
    try {
      const analisis = await dato(
        cliente.POST("/api/importaciones/analizar", {
          params: {
            header: {
              ...cabeceraCsrf(),
              "X-Nombre-Archivo": encodeURIComponent(elegido.name),
            },
          },
          headers: { "Content-Type": MIME_EXCEL },
          body: "",
          bodySerializer: () => elegido,
          signal: controlador.signal,
        }),
      );
      if (montado.current) {
        setVista(analisis);
        setFase("previa");
      }
    } catch (falla) {
      if (montado.current && !controlador.signal.aborted) {
        setError(textoFalla(falla));
        setFase("elegir");
      }
    }
  };
  useEffect(() => {
    if (!compartido || compartidoPedido.current) return;
    compartidoPedido.current = true;
    void tomarArchivoCompartido().then((elegido) => {
      if (!montado.current) return;
      if (elegido) {
        setArchivo(elegido);
        void analizar(elegido);
      } else
        setError(
          "El archivo compartido ya no está disponible. Vuelve a compartirlo o elígelo aquí.",
        );
    });
    // La petición se hace una vez y solo al montar la pantalla autenticada.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compartido]);
  const confirmar = async () => {
    if (!vista || vencido) return;
    setFase("importando");
    setError(null);
    try {
      const importacion = await dato(
        cliente.POST("/api/importaciones", {
          params: { header: cabeceraCsrf() },
          body: { token: vista.token },
        }),
      );
      if (montado.current) {
        setArchivo(null);
        setVista(null);
        navegar(
          importacion.siguiente === "categorizar"
            ? `/importaciones/${importacion.id}/categorizar`
            : `/importaciones/${importacion.id}`,
        );
      }
    } catch (falla) {
      if (!montado.current) return;
      if (falla instanceof FallaImportacion && falla.estado === 409) {
        await analizar(
          archivo,
          "Algo cambió desde el análisis. Revisa la nueva vista previa antes de importar.",
        );
      } else {
        setFase("previa");
        setError(textoFalla(falla));
        if (falla instanceof FallaImportacion && falla.estado === 410)
          setVencido(true);
      }
    }
  };
  const revisar = async () => {
    if (!vista || descartando) return;
    setDescartando(true);
    try {
      await dato(
        cliente.DELETE("/api/importaciones/analisis", {
          params: { header: cabeceraCsrf() },
          body: { token: vista.token },
        }),
      );
      setFase("revisar");
      setArchivo(null);
      setError(null);
    } catch (falla) {
      setError(textoFalla(falla));
    } finally {
      setDescartando(false);
    }
  };
  if (fase === "analizando" || fase === "importando")
    return (
      <Pila>
        <CabeceraImportacion
          titulo={
            fase === "analizando"
              ? "Analizando el archivo"
              : "Importando movimientos"
          }
          ayuda={
            fase === "analizando"
              ? "La app compara el reporte con lo que ya llevas registrado. Todavía no se guarda nada."
              : "Se guarda lo que revisaste en la vista previa."
          }
        />
        <Hoja>
          {archivo ? <ArchivoElegido nombre={archivo.name} /> : null}
          <p role="status" className="mt-4 text-muted-foreground">
            {fase === "analizando" ? "Analizando…" : "Importando…"}
          </p>
        </Hoja>
      </Pila>
    );
  if (fase === "revisar" && vista)
    return (
      <Pila>
        <CabeceraImportacion
          titulo="Revisemos antes de importar"
          ayuda="No se importó nada: todo sigue como estaba. Si el saldo no cuadra, el problema está en el archivo o en el saldo actual de la app."
        />
        <Nota>
          <p>
            Compara el saldo que ves en la Sucursal Virtual con el de la app, y
            las fechas del reporte con el rango que descargaste.
          </p>
        </Nota>
        <Hoja>
          <h2>Qué puede estar pasando, de lo más a lo menos probable</h2>
          <ul className="mt-4">
            {vista.causas_probables.map((causa) => (
              <li
                key={causa.codigo}
                className="py-(--espacio-fila) not-first:border-t not-first:border-renglon"
              >
                <p className="font-medio">{causa.titulo}</p>
                <Ayuda>{causa.texto}</Ayuda>
                <div className="mt-3">
                  {causa.accion === "elegir_otro_archivo" ? (
                    <Button
                      variant="outline"
                      onClick={() => {
                        setVista(null);
                        setFase("elegir");
                      }}
                    >
                      Elegir otro archivo
                    </Button>
                  ) : causa.accion === "ajustar_saldo" ? (
                    <Button asChild variant="outline">
                      <Link href="/saldo">Ajustar el saldo</Link>
                    </Button>
                  ) : vista.puede_extender_historial ? (
                    <Button asChild variant="outline">
                      <Link href="/extender-historial">Extender historial</Link>
                    </Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </Hoja>
      </Pila>
    );
  if (fase === "previa" && vista?.sin_cambios)
    return (
      <Pila>
        <CabeceraImportacion
          titulo="Revisa antes de importar"
          ayuda={`Esto es lo que pasará si importas ${archivo?.name ?? "el archivo"}.`}
        />
        <Hoja aria-labelledby="sin-cambios">
          <h2 id="sin-cambios">Qué va a pasar</h2>
          <ul className="mt-4">
            <ConteoImportacion
              icono={Plus}
              titulo="Se agregan"
              ayuda="No hay movimientos nuevos en este archivo."
              cantidad={vista.resumen.agregados}
            />
            <ConteoImportacion
              icono={Check}
              titulo="Ya están"
              ayuda="Coinciden con lo que llegó por correo o con una importación anterior."
              cantidad={vista.resumen.ya_estaban}
            />
          </ul>
          <Aviso tipo="info" className="mt-4">
            <span className="font-fuerte">
              Importar este archivo no cambiaría nada.
            </span>{" "}
            Tu saldo seguiría en{" "}
            <Monto>{pesos(vista.saldo_despues_centavos)}</Monto>. Si esperabas
            movimientos nuevos, descarga un rango de fechas más reciente.
            <Button
              className="mt-3"
              onClick={() => {
                setArchivo(null);
                setVista(null);
                setFase("elegir");
              }}
            >
              Elegir otro archivo
            </Button>
          </Aviso>
          {vista.resumen.anteriores > 0 ? <Ayuda className="mt-4">
            {vista.resumen.anteriores} movimientos son anteriores a tu fecha de inicio y no se importan.
          </Ayuda> : null}
          {vista.puede_extender_historial ? <Button asChild variant="outline" className="mt-3"><Link href="/extender-historial">Extender historial</Link></Button> : null}
        </Hoja>
        {error ? <Aviso tipo="error">{error}</Aviso> : null}
        {vencido ? <Button onClick={() => void analizar()}>Analizar otra vez</Button> : null}
        <ComprobarSaldo contexto={vista} token={vista.token} tipo="importacion" deshabilitado={vencido} alInvalidar={invalidarComprobacion} />
      </Pila>
    );
  if (fase === "previa" && vista)
    return (
      <Pila>
        <CabeceraImportacion
          titulo="Revisa antes de importar"
          ayuda={`Todavía no cambió nada. Esto es lo que pasará si importas ${archivo?.name ?? "el archivo"}.`}
        />
        <Button
          variant="ghost"
          onClick={() => {
            setVista(null);
            setFase("elegir");
          }}
        >
          Elegir otro archivo
        </Button>
        {error ? <Aviso tipo="error">{error}</Aviso> : null}
        <Hoja aria-labelledby="que-pasara">
          <h2 id="que-pasara">Qué va a pasar</h2>
          <ul className="mt-4">
            <ConteoImportacion
              icono={Plus}
              titulo="Se agregan"
              ayuda={`Movimientos del banco que no habían llegado por correo. ${vista.entran_categorizados} entran categorizados por tus reglas y ${vista.sin_categoria} quedan sin categoría.`}
              cantidad={vista.resumen.agregados}
            />
            <ConteoImportacion
              icono={Check}
              titulo="Ya están"
              ayuda="Ya se habían confirmado con el banco. No se repiten."
              cantidad={vista.resumen.ya_estaban}
            />
            <ConteoImportacion
              icono={Check}
              titulo="Se confirman"
              ayuda="Ya llegaron por correo o los registraste tú. El banco los confirma sin repetirlos."
              cantidad={vista.resumen.confirmados}
            />
            <ConteoImportacion
              icono={Pencil}
              titulo="Se corrigen"
              ayuda="Estaban registrados con otro monto. Quedan con el monto del banco."
              cantidad={vista.resumen.corregidos}
            />
          </ul>
          <Ayuda className="mt-4">
            {vista.resumen.anteriores}{" "}
            {vista.resumen.anteriores === 1
              ? "movimiento es anterior"
              : "movimientos son anteriores"}{" "}
            a tu fecha de inicio (
            {fechaEnFrase(vista.fecha_inicio, hoyColombia())}) y no se importan.
            Después te preguntamos por {vista.preguntas_pendientes}{" "}
            {vista.preguntas_pendientes === 1
              ? "movimiento parecido"
              : "movimientos parecidos"}{" "}
            y revisas {vista.resumen.no_en_banco} que el banco no trae.
          </Ayuda>
          {vista.puede_extender_historial ? <Button asChild variant="outline" className="mt-3"><Link href="/extender-historial">Extender historial</Link></Button> : null}
        </Hoja>
        <Hoja aria-labelledby="saldo-previsto">
          <h2 id="saldo-previsto">Tu saldo después de importar</h2>
          <div className="mt-4 space-y-3">
            <div className="flex justify-between gap-3">
              <span>Saldo actual en la app</span>
              <Monto>{pesos(vista.saldo_antes_centavos)}</Monto>
            </div>
            <div className="flex justify-between gap-3">
              <span>Cambio por esta importación</span>
              <Monto
                className={
                  vista.diferencia_centavos < 0
                    ? "text-monto-negativo"
                    : vista.diferencia_centavos > 0
                      ? "text-monto-positivo"
                      : undefined
                }
              >
                {pesos(vista.diferencia_centavos, { conSigno: true })}
              </Monto>
            </div>
            <div className="flex justify-between gap-3 font-fuerte">
              <span>Tu saldo quedará en</span>
              <SubrayadoDoble>
                <Monto>{pesos(vista.saldo_despues_centavos)}</Monto>
              </SubrayadoDoble>
            </div>
          </div>
          {vista.sin_cambios ? (
            <Nota className="mt-4">
              <p>Este archivo ya está al día. No cambia nada.</p>
            </Nota>
          ) : (
            <>
              <p className="font-fuerte mt-4">Comprueba con tu saldo real abajo</p>
              <Ayuda>
                Compáralo con el que ves ahora en la Sucursal Virtual de
                Bancolombia.
              </Ayuda>
            </>
          )}
          {vencido ? (
            <Aviso tipo="info" className="mt-4">
              El análisis venció. Vuelve a analizar el archivo antes de
              importar.
            </Aviso>
          ) : null}
          <div className="flex flex-col gap-3 mt-4 computador:flex-row">
            {vencido ? (
              <Button onClick={() => void analizar()}>
                <RefreshCw aria-hidden="true" className="size-5" />
                Analizar otra vez
              </Button>
            ) : vista.sin_cambios ? (
              <Button asChild>
                <Link href="/">Volver al inicio</Link>
              </Button>
            ) : (
              <Button disabled={descartando} onClick={() => void confirmar()}>
                <Check aria-hidden="true" className="size-5" />
                Sí, importar
              </Button>
            )}
            <Button
              variant="outline"
              disabled={descartando}
              onClick={() => void revisar()}
            >
              {descartando ? "Descartando…" : "No, revisar"}
            </Button>
          </div>
        </Hoja>
        <ComprobarSaldo contexto={vista} token={vista.token} tipo="importacion" deshabilitado={vencido || descartando} alInvalidar={invalidarComprobacion} />
      </Pila>
    );
  return (
    <Pila>
      <CabeceraImportacion
        titulo="Importar movimientos del banco"
        ayuda="Sube el Excel que descargas de la Sucursal Virtual. Primero ves qué va a pasar; no se guarda nada hasta que lo confirmes."
      />
      <ElegirExcel
        archivo={archivo}
        ocupado={false}
        error={error}
        alElegir={(elegido) => {
          setArchivo(elegido);
          setError(null);
          setVista(null);
        }}
        alAnalizar={() => void analizar()}
        alQuitar={() => {
          setArchivo(null);
          setVista(null);
          setError(null);
        }}
      />
    </Pila>
  );
}
