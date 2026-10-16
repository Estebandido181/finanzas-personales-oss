/**
 * Cliente de la API (/api, ítem 10). Único punto por donde el frontend habla
 * con el servidor.
 *
 * - Las formas de los datos salen de `esquema.d.ts`, generado desde
 *   openapi/openapi.json con `npm run tipos`. Nunca se escriben a mano.
 * - La sesión va en la cookie `sesion` (HttpOnly, mismo dominio): el
 *   frontend no la ve ni la guarda.
 * - El token CSRF vive solo en memoria (esta variable). No se guarda en
 *   localStorage ni en ningún otro sitio: al recargar se vuelve a pedir con
 *   GET /api/sesion. Todo lo que cambia datos lo envía en `X-CSRF-Token`
 *   (la descripción OpenAPI lo declara obligatorio, así que TypeScript no
 *   deja olvidarlo).
 * - Un 401 en cualquier llamada (salvo el propio login) avisa de que la
 *   sesión se cerró, y la app vuelve a la pantalla de entrar.
 */
import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "@/api/esquema";

export type Esquemas = components["schemas"];
export type Sesion = Esquemas["Sesion"];

export const ENCABEZADO_CSRF = "X-CSRF-Token";
const RUTA_SESION = "/api/sesion";

let tokenCsrf: string | null = null;
let alPerderSesion: (() => void) | null = null;

export function guardarTokenCsrf(token: string | null): void {
  tokenCsrf = token;
}

export function hayTokenCsrf(): boolean {
  return tokenCsrf !== null;
}

/** El encabezado para lo que cambia datos. Sin token no se envía nada. */
export function cabeceraCsrf(): { [ENCABEZADO_CSRF]: string } {
  if (tokenCsrf === null) throw new ErrorSinToken();
  return { [ENCABEZADO_CSRF]: tokenCsrf };
}

export class ErrorSinToken extends Error {
  constructor() {
    super("No hay token CSRF en memoria: falta iniciar sesión.");
    this.name = "ErrorSinToken";
  }
}

/** Registra qué hacer cuando la API responde 401 (sesión vencida o cerrada). */
export function alCerrarseLaSesion(accion: (() => void) | null): void {
  alPerderSesion = accion;
}

export function esLogin(request: Request): boolean {
  return request.method === "POST" && new URL(request.url).pathname === RUTA_SESION;
}

/**
 * La sesión se perdió: olvida el token y avisa a la app (vuelve a "Entrar"
 * con "Tu sesión se cerró…"). Lo usan el 401 de la API y quien descubre que
 * no hay token CSRF en memoria (`ErrorSinToken`).
 */
export function sesionPerdida(): void {
  tokenCsrf = null;
  alPerderSesion?.();
}

const vigilarSesion: Middleware = {
  onResponse({ request, response }) {
    if (response.status === 401 && !esLogin(request)) sesionPerdida();
    return undefined;
  },
};

/**
 * Crea un cliente. `fetch` se puede cambiar en las pruebas. Mismo origen:
 * la base es el origen de la página (la API está en el mismo dominio, D17).
 */
export function crearCliente(fetchPropio?: typeof fetch) {
  const cliente = createClient<paths>({
    baseUrl: globalThis.location?.origin ?? "",
    credentials: "same-origin",
    ...(fetchPropio ? { fetch: fetchPropio } : {}),
  });
  cliente.use(vigilarSesion);
  return cliente;
}

export type ClienteApi = ReturnType<typeof crearCliente>;

export const api: ClienteApi = crearCliente();
