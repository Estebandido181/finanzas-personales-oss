/**
 * Plugin de Vite (ítem 18): al terminar `vite build`, compila
 * `src/pwa/sw.ts` a `dist/sw.js` como script clásico (IIFE, sin imports) con
 * la lista cerrada del cascarón y su versión.
 *
 * - La lista son **todos los archivos de `dist/`** (los `assets/` con hash, los
 *   íconos, el manifest y `tema-inicial.js`) más el índice, que se guarda
 *   como `/app/` (el servidor no sirve `/app/index.html`). Nada de `/api`.
 * - La versión es un hash del contenido de esos archivos: si cambia un solo
 *   byte, cambia `sw.js`, el navegador instala la versión nueva y borra la
 *   caché anterior.
 */
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve, sep } from "node:path";
import { build, type Plugin, type ResolvedConfig } from "vite";

const ARCHIVO_SW = "sw.js";
const ENTRADA_SW = resolve(import.meta.dirname, "../src/pwa/sw.ts");

function archivos(carpeta: string): string[] {
  return readdirSync(carpeta).flatMap((nombre) => {
    const ruta = join(carpeta, nombre);
    return statSync(ruta).isDirectory() ? archivos(ruta) : [ruta];
  });
}

/** Rutas del cascarón y versión, a partir de la carpeta compilada. */
export function cascaron(dist: string, base: string): { precache: string[]; version: string } {
  const hash = createHash("sha256");
  const precache: string[] = [];
  const lista = archivos(dist)
    .map((ruta) => relative(dist, ruta).split(sep).join("/"))
    .filter((rel) => rel !== ARCHIVO_SW)
    .sort();
  for (const rel of lista) {
    hash.update(rel).update("\0").update(readFileSync(join(dist, rel))).update("\0");
    precache.push(rel === "index.html" ? base : base + rel);
  }
  return { precache, version: hash.digest("hex").slice(0, 16) };
}

export function serviceWorker(): Plugin {
  let config: ResolvedConfig;
  return {
    name: "finanzas-service-worker",
    apply: "build",
    configResolved(resuelta) {
      config = resuelta;
    },
    async closeBundle() {
      const dist = resolve(config.root, config.build.outDir);
      const { precache, version } = cascaron(dist, config.base);
      await build({
        configFile: false,
        logLevel: "warn",
        publicDir: false,
        define: {
          __PRECACHE__: JSON.stringify(precache),
          __VERSION__: JSON.stringify(version),
        },
        build: {
          outDir: dist,
          emptyOutDir: false,
          copyPublicDir: false,
          sourcemap: false,
          minify: true,
          lib: {
            entry: ENTRADA_SW,
            formats: ["iife"],
            name: "trabajadorFinanzas",
            fileName: () => ARCHIVO_SW,
          },
        },
      });
    },
  };
}
