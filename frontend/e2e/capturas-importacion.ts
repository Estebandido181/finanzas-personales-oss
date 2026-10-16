import { fileURLToPath } from "node:url";
import type { Page } from "@playwright/test";
import { TAMANOS, expect, revisarAccesibilidad } from "./ayudas";
const carpeta = fileURLToPath(new URL("../capturas/", import.meta.url));
/** Evidencia opcional del mismo flujo real; el CI sigue publicando capturas.
 * Nunca inyecta estilos: el tema usa el atributo de la app y sus tokens. */
export async function capturarImportacion(page: Page, nombre: string) {
  if (!process.env.CAPTURAS_30 && !process.env.CI) return;
  const anterior = page.viewportSize();
  const tema = await page.evaluate(() =>
    document.documentElement.getAttribute("data-tema"),
  );
  for (const [tamano, medidas] of Object.entries(TAMANOS))
    for (const modo of ["claro", "oscuro"]) {
      await page.setViewportSize(medidas);
      await page.evaluate(
        (m) => document.documentElement.setAttribute("data-tema", m),
        modo,
      );
      await page.evaluate(() => document.fonts.ready);
      await page.waitForLoadState("networkidle");
      await page.mouse.move(0, 0);
      const alto = await page.evaluate(
        () => document.documentElement.scrollHeight,
      );
      await page.setViewportSize({
        width: medidas.width,
        height: Math.max(alto, medidas.height),
      });
      await revisarAccesibilidad(page);
      const pequenas = await page
        .locator(
          'button, a[href], input:not([type="hidden"]), select, textarea, [role="button"]',
        )
        .evaluateAll((elementos) =>
          elementos.flatMap((elemento) => {
            const r = elemento.getBoundingClientRect();
            const estilo = getComputedStyle(elemento);
            // Los controles recortados se activan por teclado, no por toque.
            const recortado =
              estilo.clip === "rect(0px, 0px, 0px, 0px)" ||
              estilo.clipPath === "inset(50%)";
            if (
              !r.width ||
              !r.height ||
              estilo.visibility === "hidden" ||
              recortado
            ) return [];
            return r.width < 43.9 || r.height < 43.9
              ? [{
                  texto: elemento.getAttribute("aria-label") || elemento.textContent?.trim(),
                  ancho: r.width,
                  alto: r.height,
                }]
              : [];
          }),
        );
      expect(
        pequenas,
        `áreas táctiles menores de 44 px: ${nombre}/${tamano}/${modo}`,
      ).toEqual([]);
      await page.screenshot({
        path: `${carpeta}v3-30-${nombre}-${tamano}-${modo}.png`,
        animations: "disabled",
      });
    }
  if (anterior) await page.setViewportSize(anterior);
  await page.evaluate((m) => {
    if (m === null) document.documentElement.removeAttribute("data-tema");
    else document.documentElement.setAttribute("data-tema", m);
  }, tema);
}
