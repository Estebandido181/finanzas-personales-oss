import { ErrorSinToken, sesionPerdida } from "./cliente";
import { detalleDe, mensajeDeError } from "./errores";
import { TEXTOS } from "@/compartido/textos/textos";

export class FallaPeticion extends Error {
  constructor(
    public readonly estado: number | null,
    detalle?: string,
  ) {
    super(mensajeDeError(estado, detalle));
  }
}
/** Solo normaliza el resultado de openapi-fetch; no define ninguna forma de
 * datos financieros. Los T provienen de los tipos OpenAPI generados. */
export async function dato<T>(
  peticion: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  try {
    const { data, error, response } = await peticion;
    if (response.ok && data !== undefined) return data;
    throw new FallaPeticion(response.status, detalleDe(error));
  } catch (error) {
    if (error instanceof ErrorSinToken) {
      sesionPerdida();
      throw new FallaPeticion(401);
    }
    if (error instanceof FallaPeticion) throw error;
    throw new FallaPeticion(null);
  }
}
export function textoFalla(error: unknown): string {
  if (error instanceof ErrorSinToken) {
    sesionPerdida();
    return mensajeDeError(401);
  }
  return error instanceof FallaPeticion
    ? error.message
    : TEXTOS.errores.fallaDelServidor;
}
