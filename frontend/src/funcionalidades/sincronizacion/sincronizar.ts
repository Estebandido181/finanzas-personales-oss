import { useCallback, useEffect, useRef, useState } from "react";
import { cabeceraCsrf, ErrorSinToken, sesionPerdida, type ClienteApi } from "@/compartido/http/cliente";
import { detalleDe, mensajeDeError } from "@/compartido/http/errores";
import { esSinRed } from "@/compartido/http/respuesta";
import { TEXTOS } from "@/compartido/textos/textos";
import { textoResultado } from "@/funcionalidades/sincronizacion/estado";

export type ResultadoBoton = { tipo: "exito" | "error"; texto: string } | null;

/**
 * «Sincronizar ahora». Si la sincronización falló (la API responde 200 con
 * `estado: "fallida"`), el aviso grande de arriba lo explica al recargar: aquí
 * no se repite. `alTerminar(fallida)` recarga la pantalla. El aviso del
 * resultado se borra al cambiar de mes (`mes`).
 */
export function useSincronizar(
  cliente: ClienteApi,
  alTerminar: (fallida: boolean) => Promise<void>,
  mes: string | null,
) {
  const [enCurso, setEnCurso] = useState(false);
  const [resultado, setResultado] = useState<ResultadoBoton>(null);
  useEffect(() => {
    setResultado(null);
  }, [mes]);
  const montado = useRef(true);
  useEffect(() => {
    montado.current = true;
    return () => {
      montado.current = false;
    };
  }, []);

  const sincronizar = useCallback(async () => {
    setEnCurso(true);
    setResultado(null);
    let nuevo: ResultadoBoton = null;
    let fallida = false;
    let recargar = false;
    try {
      const { data, error, response } = await cliente.POST("/api/sincronizacion", {
        params: { header: cabeceraCsrf() },
        // Sin cuerpo, pero la API exige JSON en todo lo que cambia datos (415 si no).
        headers: { "Content-Type": "application/json" },
      });
      if (data) {
        recargar = true;
        fallida = data.estado === "fallida";
        if (!fallida && data.contadores) nuevo = { tipo: "exito", texto: textoResultado(data.contadores) };
      } else if (response.status === 409) {
        nuevo = { tipo: "error", texto: TEXTOS.inicio.sincronizacionEnCurso };
      } else if (response.status !== 401) {
        nuevo = { tipo: "error", texto: mensajeDeError(response.status, detalleDe(error)) };
      }
    } catch (e) {
      if (e instanceof ErrorSinToken) {
        // Sin token no hay sesión en este navegador: igual que un 401, la app
        // vuelve a "Entrar" con "Tu sesión se cerró…".
        sesionPerdida();
        return;
      }
      nuevo = {
        tipo: "error",
        texto: esSinRed(e) ? mensajeDeError(null) : TEXTOS.errores.fallaDelServidor,
      };
    }
    if (recargar) await alTerminar(fallida);
    if (!montado.current) return;
    setResultado(nuevo);
    setEnCurso(false);
  }, [cliente, alTerminar]);

  return { enCurso, resultado, sincronizar };
}

// Ítem 38: sincronizar sola al abrir la app. La hora no se calcula aquí: la
// decide el servidor (`debe_sincronizar_al_abrir`). Pero la pantalla sí cuida
// que no lo repita:
// - StrictMode monta dos veces los efectos en desarrollo;
// - volver a Inicio (otro mes, otra sección y de vuelta) no es "abrir la app";
// - tras un fallo (sin red, 5xx) no se reintenta sola: el servidor puede seguir
//   diciendo "sí" y la pantalla entraría en un ciclo. Queda el botón a mano.
// Por eso la marca vive en el módulo (una por carga de la página), no en el
// componente: sobrevive a los remontajes.
let sincronizoAlAbrir = false;

/** Para las pruebas: como una página recién abierta. */
export function reiniciarSincronizacionAlAbrir(): void {
  sincronizoAlAbrir = false;
}

/**
 * Lanza `sincronizar` una sola vez por carga de la página, la primera vez que
 * el servidor dice que toca (`debe`). `debe` es `false` mientras se carga.
 */
export function useSincronizarAlAbrir(debe: boolean, sincronizar: () => Promise<void>): void {
  const ultima = useRef(sincronizar);
  ultima.current = sincronizar;
  useEffect(() => {
    if (!debe || sincronizoAlAbrir) return;
    sincronizoAlAbrir = true;
    void ultima.current();
  }, [debe]);
}
