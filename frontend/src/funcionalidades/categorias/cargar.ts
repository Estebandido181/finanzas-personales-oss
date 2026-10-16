/**
 * Cómo "Categorías y reglas" habla con la API (ítem 15): leer categorías y
 * reglas; crear, editar y borrar categorías; borrar reglas. Todo lo que
 * cambia datos lleva el token CSRF (`cabeceraCsrf`).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { cabeceraCsrf, ErrorSinToken, sesionPerdida, type ClienteApi, type Esquemas } from "@/compartido/http/cliente";
import { detalleDe, mensajeDeError } from "@/compartido/http/errores";
import { FalloApi, exigir, esSinRed } from "@/compartido/http/respuesta";
import { TEXTOS } from "@/compartido/textos/textos";
import type { CategoriaBorrada, CategoriaConUso, Regla } from "@/funcionalidades/categorias/datos";

export interface DatosCategorias {
  categorias: CategoriaConUso[];
  reglas: Regla[];
}

export type Carga =
  | { tipo: "cargando" }
  | { tipo: "error"; sinRed: boolean; mensaje: string }
  | { tipo: "listo"; datos: DatosCategorias; actualizando: boolean };


/** Las categorías (con su uso en el mes actual) y las reglas, a la vez. */
export async function leerCategorias(cliente: ClienteApi): Promise<DatosCategorias> {
  const [categorias, reglas] = await Promise.all([
    exigir(cliente.GET("/api/categorias")),
    exigir(cliente.GET("/api/reglas")),
  ]);
  return { categorias: categorias.categorias, reglas: reglas.reglas };
}

function cargaConError(error: unknown): Carga {
  if (error instanceof FalloApi) {
    return { tipo: "error", sinRed: false, mensaje: mensajeDeError(error.estado, error.detalle) };
  }
  if (esSinRed(error)) return { tipo: "error", sinRed: true, mensaje: mensajeDeError(null) };
  return { tipo: "error", sinRed: false, mensaje: TEXTOS.errores.fallaDelServidor };
}

/**
 * Los datos de la pantalla. Tras un cambio se recargan sin pasar por
 * "Cargando…" (`silencioso`): la pantalla sigue mostrando lo anterior.
 */
export function useDatosCategorias(cliente: ClienteApi) {
  const [carga, setCarga] = useState<Carga>({ tipo: "cargando" });
  const pedido = useRef(0);

  const recargar = useCallback(
    async (silencioso = false) => {
      const este = ++pedido.current;
      setCarga((antes) =>
        silencioso && antes.tipo === "listo" ? { ...antes, actualizando: true } : { tipo: "cargando" },
      );
      let nueva: Carga;
      try {
        nueva = { tipo: "listo", datos: await leerCategorias(cliente), actualizando: false };
      } catch (error) {
        nueva = cargaConError(error);
      }
      if (este === pedido.current) setCarga(nueva);
    },
    [cliente],
  );

  useEffect(() => {
    void recargar();
    return () => {
      pedido.current++;
    };
  }, [recargar]);

  return { carga, recargar };
}

/** Resultado de algo que cambia datos. */
export type Resultado<T> =
  | { tipo: "ok"; datos: T }
  | { tipo: "error"; texto: string }
  /** La sesión se perdió: la app ya vuelve a "Entrar". */
  | { tipo: "sin-sesion" };

/** Hace la llamada y traduce el resultado (401, 404, `detalle` de la API, sin red). */
async function enviar<T>(
  llamada: () => Promise<{ data?: T; error?: unknown; response: Response }>,
  textoNoExiste: string,
): Promise<Resultado<T>> {
  try {
    const { data, error, response } = await llamada();
    if (response.ok) return { tipo: "ok", datos: data as T };
    if (response.status === 401) return { tipo: "sin-sesion" };
    if (response.status === 404) return { tipo: "error", texto: textoNoExiste };
    return { tipo: "error", texto: mensajeDeError(response.status, detalleDe(error)) };
  } catch (e) {
    if (e instanceof ErrorSinToken) {
      sesionPerdida();
      return { tipo: "sin-sesion" };
    }
    return { tipo: "error", texto: esSinRed(e) ? mensajeDeError(null) : TEXTOS.errores.fallaDelServidor };
  }
}

const T = TEXTOS.categorias;

export function crearCategoria(
  cliente: ClienteApi,
  entrada: Esquemas["CategoriaEntrada"],
): Promise<Resultado<Esquemas["Categoria"]>> {
  return enviar(
    () => cliente.POST("/api/categorias", { params: { header: cabeceraCsrf() }, body: entrada }),
    TEXTOS.errores.fallaDelServidor,
  );
}

export function editarCategoria(
  cliente: ClienteApi,
  id: number,
  cambios: Esquemas["EditarCategoriaEntrada"],
): Promise<Resultado<Esquemas["Categoria"]>> {
  return enviar(
    () =>
      cliente.PATCH("/api/categorias/{categoria_id}", {
        params: { path: { categoria_id: id }, header: cabeceraCsrf() },
        body: cambios,
      }),
    T.yaNoExiste,
  );
}

/** Borra la categoría; `moverA` es a cuál pasan sus movimientos y reglas (`null` si no tiene). */
export function borrarCategoria(
  cliente: ClienteApi,
  id: number,
  moverA: number | null,
): Promise<Resultado<CategoriaBorrada>> {
  return enviar(
    () =>
      cliente.DELETE("/api/categorias/{categoria_id}", {
        params: {
          path: { categoria_id: id },
          header: cabeceraCsrf(),
          ...(moverA === null ? {} : { query: { mover_a: moverA } }),
        },
      }),
    T.yaNoExiste,
  );
}

/** Borra la regla; la API responde con cómo deshacerlo (`deshacer`, ítem 38). */
export function borrarRegla(cliente: ClienteApi, id: number): Promise<Resultado<Esquemas["ReglaBorrada"]>> {
  return enviar(
    () =>
      cliente.DELETE("/api/reglas/{regla_id}", {
        params: { path: { regla_id: id }, header: cabeceraCsrf() },
      }),
    T.reglaYaNoExiste,
  );
}
