/// <reference types="vitest/config" />
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { serviceWorker } from "./pwa/plugin-sw.ts";

// La app se publica en /app (D17): FastAPI sirve dist/ (ver finanzas/web/frontend.py).
export default defineConfig({
  base: "/app/",
  // serviceWorker(): dist/sw.js con el cascarón de esta versión (ítem 18).
  plugins: [react(), tailwindcss(), serviceWorker()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // CSP estricta (img-src y font-src sin data: para nuestros archivos): nada
    // se incrusta como data: URI, todo sale como archivo con hash en assets/.
    assetsInlineLimit: 0,
    // Todos los navegadores actuales soportan modulepreload: sin polyfill.
    modulePreload: { polyfill: false },
    sourcemap: false,
  },
  server: {
    // En desarrollo (`npm run dev`) la API es el uvicorn local. El Host se
    // conserva, así la comprobación de Origin de la app acepta los envíos.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    // Bound parallel test environments on shared/local CI machines.
    maxWorkers: 2,
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/pruebas/preparar.ts"],
    environmentOptions: { jsdom: { url: "http://localhost/app/" } },
  },
});
