import { detalleDe } from "./errores";

/** Una respuesta de openapi-fetch que no trajo datos: su texto de error. */
export class FalloApi extends Error {
  constructor(
    readonly estado: number,
    readonly detalle: string | undefined,
  ) {
    super(`HTTP ${estado}`);
  }
}

export async function exigir<T>(promesa: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promesa;
  if (data === undefined) throw new FalloApi(response.status, detalleDe(error));
  return data;
}

/**
 * `fetch` sin respuesta (sin red, servidor caído) lanza `TypeError`: eso es
 * "sin conexión". Cualquier otra excepción es una falla genérica.
 */
export function esSinRed(error: unknown): boolean {
  return error instanceof TypeError;
}
