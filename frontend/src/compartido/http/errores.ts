import { TEXTOS } from "@/compartido/textos/textos";

/**
 * Respaldo general: traduce el resultado de una llamada fallida a un texto para el dueño
 * (TEXTOS.md, "Errores"). `estado` es el código HTTP, o `null` si ni siquiera
 * hubo respuesta (sin red, servidor caído). `detalle` es el texto que manda
 * la API en {"detalle": "..."}: ya está escrito para el dueño y sin datos
 * internos, así que se usa cuando no hay un texto propio para ese caso.
 */
export function mensajeDeError(estado: number | null, detalle?: unknown): string {
  if (estado === null) return TEXTOS.errores.sinConexion;
  if (estado === 401) return TEXTOS.errores.sesionCerrada;
  if (estado === 429) return TEXTOS.errores.demasiadosIntentos;
  if (typeof detalle === "string" && detalle.trim() !== "") return detalle;
  return TEXTOS.errores.fallaDelServidor;
}

/**
 * Para el login: un 401 es la contraseña, un 429 el bloqueo por intentos, sin
 * respuesta es la red y cualquier otra cosa, "No se pudo entrar…".
 */
export function mensajeDeErrorAlEntrar(estado: number | null): string {
  if (estado === null) return TEXTOS.errores.sinConexion;
  if (estado === 401) return TEXTOS.errores.contrasenaIncorrecta;
  if (estado === 429) return TEXTOS.errores.demasiadosIntentos;
  return TEXTOS.errores.entrarFallo;
}

/** Saca `detalle` de un cuerpo de error de la API, si lo trae. */
export function detalleDe(cuerpo: unknown): string | undefined {
  if (cuerpo && typeof cuerpo === "object" && "detalle" in cuerpo) {
    const detalle = (cuerpo as { detalle: unknown }).detalle;
    return typeof detalle === "string" ? detalle : undefined;
  }
  return undefined;
}
