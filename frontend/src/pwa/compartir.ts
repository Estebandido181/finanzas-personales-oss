/** Compartir → Finanzas: el original vive solo en memoria, ligado a la pestaña
 * que recibió la navegación. Se consume una vez tras iniciar sesión. Nunca se
 * escribe en Cache Storage, IndexedDB ni localStorage. */
export const RUTA_COMPARTIR = "/app/compartir";
export const MIME_EXCEL =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
export const MAX_ARCHIVO_COMPARTIDO = 2 * 1024 * 1024;
const MAX_FORMULARIO = MAX_ARCHIVO_COMPARTIDO + 64 * 1024;
const VIDA_ARCHIVO_MS = 15 * 60 * 1000;
export const MENSAJE_ARCHIVO = "recibir-archivo-compartido";

export class ArchivosCompartidos {
  private entrada: { cliente: string; archivo: File; vence: number } | null =
    null;
  private reloj: ReturnType<typeof setTimeout> | null = null;
  limpiar() {
    if (this.reloj !== null) clearTimeout(this.reloj);
    this.reloj = null;
    this.entrada = null;
  }
  guardar(cliente: string, archivo: File, ahora = Date.now()) {
    this.limpiar();
    if (
      !cliente ||
      !archivo.name.toLowerCase().endsWith(".xlsx") ||
      archivo.size > MAX_ARCHIVO_COMPARTIDO ||
      archivo.size === 0
    )
      return false;
    this.entrada = { cliente, archivo, vence: ahora + VIDA_ARCHIVO_MS };
    this.reloj = setTimeout(() => this.limpiar(), VIDA_ARCHIVO_MS);
    return true;
  }
  consumir(cliente: string, ahora = Date.now()): File | null {
    if (!this.entrada) return null;
    if (ahora >= this.entrada.vence) {
      this.limpiar();
      return null;
    }
    if (cliente !== this.entrada.cliente) return null;
    const archivo = this.entrada.archivo;
    this.limpiar();
    return archivo;
  }
}

export function esCompartir(
  peticion: Pick<Request, "url" | "method">,
  origen: string,
): boolean {
  const url = new URL(peticion.url);
  return (
    peticion.method === "POST" &&
    url.origin === origen &&
    url.pathname === RUTA_COMPARTIR
  );
}

export async function recibirCompartido(
  peticion: Request,
  cliente: string,
  almacen: ArchivosCompartidos,
): Promise<boolean> {
  almacen.limpiar();
  let valido = false;
  try {
    if (
      !cliente ||
      !peticion.headers
        .get("content-type")
        ?.startsWith("multipart/form-data;") ||
      !peticion.body
    )
      throw new Error("formato");
    const anunciada = peticion.headers.get("content-length");
    if (anunciada && Number(anunciada) > MAX_FORMULARIO)
      throw new Error("tamaño");
    const lector = peticion.body.getReader();
    const partes: Uint8Array<ArrayBuffer>[] = [];
    let longitud = 0;
    for (;;) {
      const { done, value } = await lector.read();
      if (done) break;
      longitud += value.byteLength;
      if (longitud > MAX_FORMULARIO) {
        await lector.cancel();
        throw new Error("tamaño");
      }
      partes.push(new Uint8Array(value));
    }
    const datos = await new Response(new Blob(partes), {
      headers: { "Content-Type": peticion.headers.get("content-type")! },
    }).formData();
    if ([...datos.keys()].some((clave) => clave !== "archivo"))
      throw new Error("archivo");
    const archivos = datos.getAll("archivo");
    if (archivos.length !== 1 || !(archivos[0] instanceof File))
      throw new Error("archivo");
    valido = almacen.guardar(cliente, archivos[0]);
  } catch {
    /* Solo un aviso genérico: nunca nombres, contenido ni datos en logs. */
  }
  return valido;
}

/** Solo se invoca dentro de la pantalla autenticada. La respuesta cruza un
 * MessageChannel privado; ninguna otra pestaña recibe el original. */
export async function tomarArchivoCompartido(): Promise<File | null> {
  const trabajador = navigator.serviceWorker?.controller;
  if (!trabajador) return null;
  return new Promise((resolve) => {
    const canal = new MessageChannel();
    const terminar = (archivo: File | null) => {
      clearTimeout(reloj);
      canal.port1.close();
      resolve(archivo);
    };
    const reloj = setTimeout(() => terminar(null), 3000);
    canal.port1.onmessage = (evento: MessageEvent<unknown>) =>
      terminar(evento.data instanceof File ? evento.data : null);
    trabajador.postMessage({ tipo: MENSAJE_ARCHIVO }, [canal.port2]);
  });
}
