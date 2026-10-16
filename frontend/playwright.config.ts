/**
 * Pruebas en navegador (ítem 12). Corren contra la app real: FastAPI con la
 * CSP, la sesión, el CSRF y /app de producción, sirviendo `dist/` (hay que
 * compilar antes: `npm run build`), con una base temporal y datos inventados
 * (scripts/servidor_e2e.py).
 *
 * Proyectos:
 * - `pruebas` (npm run e2e): flujos, accesibilidad con axe y CSP. En el CI.
 * - `capturas` (npm run capturas): capturas 390/1280 px, claro/oscuro, en
 *   frontend/capturas/ para revisión local. No se versionan ni se suben
 *   automáticamente como artefactos (ver .gitignore).
 */
import { defineConfig, devices } from "@playwright/test";

// Otro puerto con PUERTO_E2E: así dos copias del repositorio pueden correr
// sus pruebas a la vez sin que una reutilice el servidor (y los datos) de la otra.
const PUERTO = Number(process.env.PUERTO_E2E || 8123);
const PYTHON = process.env.PYTHON ?? "python3";
// Opcional: usar un Chromium ya instalado (p. ej. cuando no se puede
// descargar el de Playwright). En el CI no hace falta.
const ejecutable = process.env.PLAYWRIGHT_CHROMIUM;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? [["list"], ["github"]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PUERTO}`,
    ...devices["Desktop Chrome"],
    locale: "es-CO",
    timezoneId: "America/Bogota",
    ...(ejecutable ? { launchOptions: { executablePath: ejecutable } } : {}),
  },
  projects: [
    { name: "pruebas", testIgnore: /capturas\.spec\.ts/ },
    { name: "capturas", testMatch: /capturas\.spec\.ts/ },
  ],
  webServer: {
    command: `${PYTHON} ../scripts/servidor_e2e.py --puerto ${PUERTO}`,
    url: `http://127.0.0.1:${PUERTO}/app/`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    stdout: "ignore",
    stderr: "pipe",
  },
});
