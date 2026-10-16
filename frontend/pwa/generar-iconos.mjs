// Genera los íconos de la app instalable (ítem 18) a partir de
// diseno/favicon.svg (la hoja de libreta, en su versión clara) sobre el papel
// envejecido de tokens.css (`--background` claro). Usa el Chromium de
// Playwright, que ya es dependencia de desarrollo: no hace falta otra
// herramienta de imágenes.
//
//   node pwa/generar-iconos.mjs        (PLAYWRIGHT_CHROMIUM=/ruta/a/chrome si hace falta)
//
// Escribe en public/iconos/ (se versionan; no se generan en cada build):
// - icono-192.png, icono-512.png: "any", esquinas algo redondeadas y fondo transparente fuera.
// - icono-maskable-512.png: fondo a sangre; la hoja cabe en la zona segura
//   (círculo del 80 % central), así Android puede recortarlo en círculo o gota.
// - apple-touch-icon.png (180 px): fondo a sangre y sin transparencia (iOS
//   pone negro donde es transparente y redondea las esquinas él mismo).
import { readFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const aqui = dirname(fileURLToPath(import.meta.url));
const favicon = readFileSync(resolve(aqui, "../diseno/favicon.svg"), "utf8");
const tokens = readFileSync(resolve(aqui, "../diseno/tokens.css"), "utf8");
const papel = tokens.match(/--background:\s*(#[0-9a-fA-F]{6})/)?.[1];
if (!papel) throw new Error("No encontré --background en tokens.css");
const salida = resolve(aqui, "../public/iconos");
mkdirSync(salida, { recursive: true });

// `hoja`: qué parte del lado ocupa el favicon (su viewBox de 32).
const ICONOS = [
  { archivo: "icono-192.png", lado: 192, hoja: 0.68, radio: 0.18 },
  { archivo: "icono-512.png", lado: 512, hoja: 0.68, radio: 0.18 },
  { archivo: "icono-maskable-512.png", lado: 512, hoja: 0.56, radio: 0 },
  { archivo: "apple-touch-icon.png", lado: 180, hoja: 0.68, radio: 0 },
];

const datos = "data:image/svg+xml;base64," + Buffer.from(favicon).toString("base64");
const navegador = await chromium.launch(
  process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {},
);
const pagina = await navegador.newPage({ deviceScaleFactor: 1 });
await pagina.emulateMedia({ colorScheme: "light" });
for (const { archivo, lado, hoja, radio } of ICONOS) {
  const tam = Math.round(lado * hoja);
  await pagina.setViewportSize({ width: lado, height: lado });
  await pagina.setContent(`<!doctype html>
    <body style="margin:0;background:transparent">
      <div id="i" style="width:${lado}px;height:${lado}px;display:grid;place-items:center;
        background:${papel};border-radius:${Math.round(lado * radio)}px">
        <img src="${datos}" width="${tam}" height="${tam}" alt="">
      </div>
    </body>`);
  await pagina.locator("img").evaluate((img) => img.decode());
  await pagina.locator("#i").screenshot({ path: resolve(salida, archivo), omitBackground: true });
  console.log(`${archivo} (${lado}×${lado})`);
}
await navegador.close();
