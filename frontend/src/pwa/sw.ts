/**
 * Service worker de la app (ítem 18). Se compila aparte, como script clásico,
 * a `dist/sw.js` (ver `pwa/plugin-sw.ts`), y se sirve en /app/sw.js con
 * alcance /app/. La lógica y las reglas de seguridad están en `trabajador.ts`.
 *
 * `__PRECACHE__` y `__VERSION__` los reemplaza el plugin al compilar.
 */
import {
  esMensajeLimpiar,
  instalar,
  limpiar,
  nombreCache,
  responder,
  type ConfigTrabajador,
} from "./trabajador";

import {
  ArchivosCompartidos,
  esCompartir,
  recibirCompartido,
  MENSAJE_ARCHIVO,
} from "./compartir";

declare const __PRECACHE__: readonly string[];
declare const __VERSION__: string;

// Lo mínimo del ámbito de un service worker. Se declara aquí para no mezclar
// la librería "WebWorker" de TypeScript con la "DOM" del resto de la app.
interface EventoExtensible extends Event {
  waitUntil(promesa: Promise<unknown>): void;
}
interface EventoFetch extends EventoExtensible {
  readonly request: Request;
  readonly resultingClientId: string;
  respondWith(respuesta: Promise<Response>): void;
}
interface EventoMensaje extends EventoExtensible {
  readonly data: unknown;
  readonly origin: string;
  readonly source: { id?: string } | null;
  readonly ports: readonly MessagePort[];
}
interface AmbitoSw {
  readonly caches: CacheStorage;
  readonly location: Location;
  readonly clients: { claim(): Promise<void> };
  skipWaiting(): Promise<void>;
  addEventListener(
    tipo: "install" | "activate",
    oyente: (e: EventoExtensible) => void,
  ): void;
  addEventListener(tipo: "fetch", oyente: (e: EventoFetch) => void): void;
  addEventListener(tipo: "message", oyente: (e: EventoMensaje) => void): void;
}

const sw = self as unknown as AmbitoSw;
const config: ConfigTrabajador = {
  cache: nombreCache(__VERSION__),
  precache: __PRECACHE__,
};
const lista = new Set(config.precache);
const compartidos = new ArchivosCompartidos();

sw.addEventListener("install", (evento) => {
  // La versión nueva reemplaza a la anterior en cuanto termina de instalarse.
  evento.waitUntil(
    instalar(config, sw.caches, fetch, sw.location.origin).then(() =>
      sw.skipWaiting(),
    ),
  );
});

sw.addEventListener("activate", (evento) => {
  // Borra las cachés de versiones anteriores.
  evento.waitUntil(limpiar(config, sw.caches).then(() => sw.clients.claim()));
});

sw.addEventListener("fetch", (evento) => {
  if (esCompartir(evento.request, sw.location.origin)) {
    evento.respondWith(
      (async () => {
        await recibirCompartido(
          evento.request,
          evento.resultingClientId,
          compartidos,
        );
        // Conserva el documento destinatario y su clientId: un 303 abriría otro
        // documento. El cuerpo bancario nunca sale a la red en esta navegación.
        const indice = await (
          await sw.caches.open(config.cache)
        ).match("/app/");
        if (!indice) {
          compartidos.limpiar();
          return new Response("Abre Finanzas y elige el archivo Excel.", {
            status: 503,
            headers: {
              "Content-Type": "text/plain; charset=utf-8",
              "Cache-Control": "no-store",
            },
          });
        }
        return indice;
      })(),
    );
    return;
  }
  // /api, otros métodos, otros orígenes y la v1 no se tocan: van a la red.
  const respuesta = responder(
    evento.request,
    config,
    sw.caches,
    fetch,
    sw.location.origin,
    lista,
  );
  if (respuesta) evento.respondWith(respuesta);
});

sw.addEventListener("message", (evento) => {
  // Solo de páginas de este mismo origen (ni vacío ni ajeno).
  if (esMensajeLimpiar(evento, sw.location.origin)) {
    compartidos.limpiar();
    evento.waitUntil(limpiar(config, sw.caches));
  }
  if (
    evento.origin === sw.location.origin &&
    evento.data &&
    typeof evento.data === "object" &&
    "tipo" in evento.data &&
    evento.data.tipo === MENSAJE_ARCHIVO
  ) {
    const cliente = evento.source?.id;
    if (cliente && evento.ports[0])
      evento.ports[0].postMessage(compartidos.consumir(cliente));
  }
});
