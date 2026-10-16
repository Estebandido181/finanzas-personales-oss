import AxeBuilder from "@axe-core/playwright";
import { expect, test as base, type Page } from "@playwright/test";

/** La de scripts/servidor_e2e.py (inventada). */
export const CONTRASENA_E2E = "clave-e2e-inventada";

export const TAMANOS = {
  celular: { width: 390, height: 844 },
  computador: { width: 1280, height: 800 },
} as const;
export type Tamano = keyof typeof TAMANOS;
export type Modo = "claro" | "oscuro";

/**
 * `test` que además vigila la CSP: cualquier violación (un estilo o script en
 * línea, una imagen data: no permitida…) hace fallar la prueba. Se detecta de
 * dos formas: el evento `securitypolicyviolation` de la página y los mensajes
 * de consola del navegador.
 */
export const test = base.extend<{ violacionesCsp: string[] }>({
  violacionesCsp: [
    async ({ page }, usar) => {
      const violaciones: string[] = [];
      await page.exposeFunction("__avisarViolacionCsp", (texto: string) => violaciones.push(texto));
      await page.addInitScript(() => {
        document.addEventListener("securitypolicyviolation", (e) => {
          const avisar = (window as unknown as { __avisarViolacionCsp: (t: string) => void })
            .__avisarViolacionCsp;
          avisar(`${e.violatedDirective} ${e.blockedURI} ${e.sourceFile}:${e.lineNumber}`);
        });
      });
      page.on("console", (mensaje) => {
        if (/Content Security Policy|Refused to/i.test(mensaje.text())) {
          violaciones.push(mensaje.text());
        }
      });
      await usar(violaciones);
      expect(violaciones, "violaciones de la CSP").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

export async function prepararModo(page: Page, modo: Modo): Promise<void> {
  // El modo se fuerza como lo haría el dueño en «Apariencia» (localStorage),
  // y el esquema del sistema también, por si algo lo sigue.
  await page.emulateMedia({ colorScheme: modo === "oscuro" ? "dark" : "light" });
  await page.addInitScript((m) => {
    try {
      localStorage.setItem("finanzas-tema", m);
    } catch {
      /* sin almacenamiento */
    }
  }, modo);
}

export async function entrar(page: Page, ruta = "/app/"): Promise<void> {
  await page.goto(ruta);
  await page.getByLabel("Contraseña").fill(CONTRASENA_E2E);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText("Finanzas personales");
}

/** axe-core con las reglas WCAG 2.x A y AA y buenas prácticas: 0 violaciones. */
export async function revisarAccesibilidad(page: Page): Promise<void> {
  // Espera a que las fuentes carguen: el contraste depende del texto final.
  await page.evaluate(() => document.fonts.ready);
  const resultado = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .analyze();
  const resumen = resultado.violations.map(
    (v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`,
  );
  expect(resumen, "violaciones de accesibilidad (axe)").toEqual([]);
}
