/**
 * API simulada para las pruebas de unidad: un `fetch` falso que responde
 * según método y ruta, y guarda las peticiones para revisarlas.
 * Todos los datos son inventados.
 */
import { crearCliente, type Esquemas } from "@/compartido/http/cliente";

export type Respuesta = { estado: number; cuerpo?: unknown } | "sin-red";
export type Manejador = (peticion: Request) => Respuesta | Promise<Respuesta>;

export const TOKEN_INVENTADO = "token-csrf-inventado";
export const SESION_INVENTADA = {
  usuario: { id: "dueno", nombre: "Dueño" },
  csrf_token: TOKEN_INVENTADO,
};

export function simularApi(rutas: Record<string, Manejador | Respuesta>) {
  const peticiones: Request[] = [];
  const fetchFalso: typeof fetch = async (entrada, opciones) => {
    const peticion = entrada instanceof Request ? entrada : new Request(entrada, opciones);
    peticiones.push(peticion.clone());
    const clave = `${peticion.method} ${new URL(peticion.url).pathname}`;
    const estadoImportacion: Esquemas["EstadoImportaciones"] = { ultima_id: null, mostrar_recordatorio: false, movimientos_desde_ultima: 0, semanas_desde_ultima: 0, preguntas_pendientes: 0, no_en_banco_pendientes: 0, sin_categoria: 0, importacion_pendiente: false };
    const respaldos: Record<string, Respuesta> = {
      "GET /api/inicio/estado": { estado: 200, cuerpo: { todo_al_dia: true, total_acciones: 0, texto: "Todo al día", areas: [] } satisfies Esquemas["EstadoInicio"] },
      "GET /api/arranque/estado": { estado: 200, cuerpo: { mostrar_arranque_inicial: false, puede_iniciar_arranque: false, puede_extender_historial: false } satisfies Esquemas["EstadoArranque"] },
      "GET /api/importaciones/estado": { estado: 200, cuerpo: estadoImportacion },
      "GET /api/importaciones/ultima": { estado: 200, cuerpo: { importacion: null } satisfies Esquemas["UltimaImportacion"] },
    };
    const definida = rutas[clave] ?? respaldos[clave];
    const respuesta =
      definida === undefined
        ? { estado: 404, cuerpo: { detalle: "No encontrado." } }
        : typeof definida === "function"
          ? await definida(peticion)
          : definida;
    if (respuesta === "sin-red") throw new TypeError("Failed to fetch");
    const sinCuerpo = respuesta.estado === 204 || respuesta.cuerpo === undefined;
    return new Response(sinCuerpo ? null : JSON.stringify(respuesta.cuerpo), {
      status: respuesta.estado,
      headers: sinCuerpo ? {} : { "Content-Type": "application/json" },
    });
  };
  return { cliente: crearCliente(fetchFalso), peticiones, rutas };
}
