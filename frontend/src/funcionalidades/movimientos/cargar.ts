/**
 * Cómo Movimientos habla con la API: leer el mes (con y sin filtros) y
 * categorizar o corregir un movimiento, con o sin crear la regla.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { cabeceraCsrf, ErrorSinToken, sesionPerdida, type ClienteApi, type Esquemas } from "@/compartido/http/cliente";
import { detalleDe, mensajeDeError } from "@/compartido/http/errores";
import { FalloApi, exigir, esSinRed } from "@/compartido/http/respuesta";
import { TEXTOS } from "@/compartido/textos/textos";
import {
  consultaApi,
  esBandeja,
  hayFiltro,
  type Categoria,
  type Filtros,
  type GrupoPendientes,
  type Movimiento,
  type Reporte,
} from "@/funcionalidades/movimientos/datos";

/** Un mes, con o sin filtros. */
export interface DatosDelMes {
  tipo: "mes";
  /** Selector de mes y número de pendientes (de todos los meses, como Inicio). */
  reporte: Reporte;
  categorias: Categoria[];
  /** Todos los movimientos del mes, sin filtros (días y "Gastado"). */
  delMes: Movimiento[];
  /** Los que pasan el filtro según la API; `null` sin filtro. */
  filtradas: Movimiento[] | null;
  filtros: Filtros;
}

/** La bandeja "Sin categorizar": los pendientes de todos los meses. */
export interface DatosBandeja {
  tipo: "bandeja";
  categorias: Categoria[];
  pendientes: Movimiento[];
  /** Ítem 38: los pendientes iguales (2 o más), que se categorizan juntos. Los arma el servidor. */
  grupos: GrupoPendientes[];
  /** El mismo número que el de Inicio (`reporte.pendientes`). */
  total: number;
  filtros: Filtros;
}

export interface DatosDescartados {
  tipo: "descartados";
  reporte: Reporte;
  categorias: Categoria[];
  movimientos: Esquemas["MovimientoDescartado"][];
  filtros: Filtros;
}
export type DatosMovimientos = DatosDelMes | DatosBandeja | DatosDescartados;

/** El número de "Sin categorizar (N)": de todos los meses, igual que en Inicio. */
export function totalPendientes(datos: DatosMovimientos): number {
  return datos.tipo === "bandeja" ? datos.total : datos.reporte.pendientes;
}

export type Carga =
  | { tipo: "cargando" }
  | { tipo: "error"; sinRed: boolean; mensaje: string }
  | { tipo: "listo"; datos: DatosMovimientos; actualizando: boolean };


/**
 * Lee todo lo de Movimientos. `mes` es "aaaa-mm", o `null` para el mes
 * actual; la bandeja no usa el mes.
 */
export async function leerMovimientos(
  cliente: ClienteApi,
  mes: string | null,
  filtros: Filtros,
): Promise<DatosMovimientos> {
  if (filtros.vista === "descartados") {
    const [reporte, categorias, descartados] = await Promise.all([
      exigir(cliente.GET("/api/reporte")),
      exigir(cliente.GET("/api/categorias")),
      exigir(cliente.GET("/api/movimientos/descartados")),
    ]);
    return { tipo: "descartados", reporte, categorias: categorias.categorias, movimientos: descartados.movimientos, filtros };
  }
  if (esBandeja(filtros)) {
    const [categorias, bandeja] = await Promise.all([
      exigir(cliente.GET("/api/categorias")),
      exigir(cliente.GET("/api/movimientos/sin-categorizar")),
    ]);
    return {
      tipo: "bandeja",
      categorias: categorias.categorias,
      pendientes: bandeja.movimientos,
      grupos: bandeja.grupos,
      total: bandeja.total,
      filtros,
    };
  }
  const delMesConsulta = mes ? { params: { query: { mes } } } : {};
  const [reporte, categorias, delMes, filtradas] = await Promise.all([
    exigir(cliente.GET("/api/reporte", delMesConsulta)),
    exigir(cliente.GET("/api/categorias")),
    exigir(cliente.GET("/api/movimientos", delMesConsulta)),
    hayFiltro(filtros)
      ? exigir(cliente.GET("/api/movimientos", { params: { query: consultaApi(mes, filtros) } }))
      : Promise.resolve(null),
  ]);
  return {
    tipo: "mes",
    reporte,
    categorias: categorias.categorias,
    delMes: delMes.movimientos,
    filtradas: filtradas?.movimientos ?? null,
    filtros,
  };
}

function cargaConError(error: unknown): Carga {
  if (error instanceof FalloApi) {
    return { tipo: "error", sinRed: false, mensaje: mensajeDeError(error.estado, error.detalle) };
  }
  if (esSinRed(error)) return { tipo: "error", sinRed: true, mensaje: mensajeDeError(null) };
  return { tipo: "error", sinRed: false, mensaje: TEXTOS.errores.fallaDelServidor };
}

/**
 * Los datos del mes con sus filtros. Cambiar de mes pasa por "Cargando…";
 * cambiar de filtro o recargar tras categorizar, no: la pantalla sigue
 * mostrando lo anterior (`actualizando`) hasta que llega lo nuevo.
 */
export function useDatosMovimientos(cliente: ClienteApi, mes: string | null, filtros: Filtros) {
  const [carga, setCarga] = useState<Carga>({ tipo: "cargando" });
  const pedido = useRef(0);
  // Qué se cargó por última vez ("bandeja" o el mes): lo demás se cambia sin "Cargando…".
  const cargado = useRef<string | null | undefined>(undefined);
  const { vista, categoria } = filtros;
  const clave = filtros.vista === "descartados" ? "descartados" : esBandeja(filtros) ? "bandeja" : mes;

  const recargar = useCallback(
    async (silencioso = false) => {
      const este = ++pedido.current;
      // Entrar o salir de la bandeja es cambiar de filtro, no de mes: sin "Cargando…".
      const mismoMes =
        cargado.current === clave || (cargado.current !== undefined && (clave === "bandeja" || cargado.current === "bandeja"));
      if (silencioso || mismoMes) {
        setCarga((antes) => (antes.tipo === "listo" ? { ...antes, actualizando: true } : antes));
      } else {
        setCarga({ tipo: "cargando" });
      }
      let nueva: Carga;
      try {
        const datos = await leerMovimientos(cliente, mes, { vista, categoria });
        nueva = { tipo: "listo", datos, actualizando: false };
      } catch (error) {
        nueva = cargaConError(error);
      }
      // Si mientras tanto se pidió otro mes u otro filtro, esta respuesta ya no sirve.
      if (este !== pedido.current) return;
      cargado.current = nueva.tipo === "listo" ? clave : undefined;
      setCarga(nueva);
    },
    [cliente, mes, vista, categoria, clave],
  );

  useEffect(() => {
    void recargar();
    return () => {
      pedido.current++;
    };
  }, [recargar]);

  return { carga, recargar };
}

export type ResultadoCategorizar =
  | { tipo: "ok"; datos: import("@/compartido/http/cliente").Esquemas["Categorizado"] }
  | { tipo: "error"; texto: string }
  /** La sesión se perdió: la app ya vuelve a "Entrar". */
  | { tipo: "sin-sesion" };

/**
 * PUT /api/movimientos/{id}/categoria. Con `recordar`, en la misma llamada
 * se guarda la regla (y se aplica a los pendientes iguales). Ítem 17:
 * `condiciones` dice qué regla crear (una de `reglas_posibles`); solo va con
 * `recordar` (la API responde 400 si no).
 */
export async function categorizar(
  cliente: ClienteApi,
  movimientoId: number,
  categoriaId: number,
  recordar: boolean,
  condiciones?: Esquemas["OpcionRegla"]["condiciones"],
): Promise<ResultadoCategorizar> {
  try {
    const { data, error, response } = await cliente.PUT("/api/movimientos/{movimiento_id}/categoria", {
      params: { path: { movimiento_id: movimientoId }, header: cabeceraCsrf() },
      body: {
        categoria_id: categoriaId,
        recordar,
        ...(recordar && condiciones ? { condiciones } : {}),
      },
    });
    if (data) return { tipo: "ok", datos: data };
    if (response.status === 401) return { tipo: "sin-sesion" };
    if (response.status === 404) return { tipo: "error", texto: TEXTOS.movimientos.yaNoExiste };
    return { tipo: "error", texto: mensajeDeError(response.status, detalleDe(error)) };
  } catch (e) {
    if (e instanceof ErrorSinToken) {
      sesionPerdida();
      return { tipo: "sin-sesion" };
    }
    return { tipo: "error", texto: esSinRed(e) ? mensajeDeError(null) : TEXTOS.errores.fallaDelServidor };
  }
}

export type ResultadoCategorizarGrupo =
  | { tipo: "ok"; datos: Esquemas["Categorizado"] }
  | { tipo: "error"; texto: string }
  /** La sesión se perdió: la app ya vuelve a "Entrar". */
  | { tipo: "sin-sesion" };

/**
 * POST /api/movimientos/categorizar-grupo (ítem 38): categoriza juntos los
 * `ids` del grupo y guarda su regla, todo o nada. El servidor toca solo los
 * que siguen pendientes; `categorizados` los cuenta.
 */
export async function categorizarGrupo(
  cliente: ClienteApi,
  grupo: Pick<GrupoPendientes, "clave" | "ids">,
  categoriaId: number,
  modoRegla: Esquemas["CategorizarGrupoEntrada"]["modo_regla"] = "exacta",
): Promise<ResultadoCategorizarGrupo> {
  try {
    const { data, error, response } = await cliente.POST("/api/movimientos/categorizar-grupo", {
      params: { header: cabeceraCsrf() },
      body: { clave: grupo.clave, ids: grupo.ids, categoria_id: categoriaId, modo_regla: modoRegla },
    });
    if (data) return { tipo: "ok", datos: data };
    if (response.status === 401) return { tipo: "sin-sesion" };
    return { tipo: "error", texto: mensajeDeError(response.status, detalleDe(error)) };
  } catch (e) {
    if (e instanceof ErrorSinToken) {
      sesionPerdida();
      return { tipo: "sin-sesion" };
    }
    return { tipo: "error", texto: esSinRed(e) ? mensajeDeError(null) : TEXTOS.errores.fallaDelServidor };
  }
}
