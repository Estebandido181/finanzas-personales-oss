import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { entrar, expect, revisarAccesibilidad, TAMANOS, test } from "./ayudas";
import { excelInventado, MIME_XLSX } from "./excel-inventado";
import type { Page } from "@playwright/test";
import type { components } from "../src/api/esquema";
async function capturar(page: Page, nombre: string) {
  if (!process.env.CAPTURAS_31) return;
  const anterior = page.viewportSize();
  for (const [tamano, medidas] of Object.entries(TAMANOS)) for (const modo of ["claro", "oscuro"]) {
    await page.waitForLoadState("networkidle");
    await page.setViewportSize(medidas);
    await page.evaluate((tema) => document.documentElement.setAttribute("data-tema", tema), modo);
    await page.evaluate(() => document.fonts.ready);
    // En capturas largas, la barra fija queda al pie de la imagen y no tapa
    // controles en el centro; la app conserva su tamaño real en la prueba.
    const alto = await page.evaluate(() => document.documentElement.scrollHeight);
    await page.setViewportSize({ width: medidas.width, height: Math.max(alto, medidas.height) });
    await revisarAccesibilidad(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: fileURLToPath(new URL(`../capturas/v3-31-${nombre}-${tamano}-${modo}.png`, import.meta.url)), fullPage: true, animations: "disabled" });
  }
  if (anterior) await page.setViewportSize(anterior);
}
async function subir(page: Page, nombre: string, buffer = excelInventado()) {
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Archivo Excel del banco").setInputFiles({ name: nombre, mimeType: MIME_XLSX, buffer });
  await expect(page.getByText(nombre, { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Agregar otro archivo" })).toBeEnabled();
}
test.afterEach(async ({ page, request }) => {
  await page.waitForLoadState("networkidle");
  expect((await request.get("/e2e/datos/reiniciar")).ok()).toBe(true);
});
test("primer arranque junta archivos, confirma el cálculo, categoriza y deshace restaurando ausencia de saldo", async ({ page, request }) => {
  expect((await request.get("/e2e/datos/sin-saldo")).ok()).toBe(true);
  await entrar(page);
  await expect(page.getByRole("heading", { name: "Empieza con tu historial del banco" })).toBeVisible();
  await capturar(page, "arranque");
  await subir(page, "mes-A-INVENTADO.xlsx");
  await subir(page, "mes-B-INVENTADO.xlsx");
  await page.getByRole("button", { name: "Quitar mes-A-INVENTADO.xlsx" }).click();
  await expect(page.getByText("mes-A-INVENTADO.xlsx")).toHaveCount(0);
  await subir(page, "mes-C-INVENTADO.xlsx");
  await page.getByLabel("Escribe el saldo que ves ahora en Bancolombia").fill("100.000");
  await page.getByRole("button", { name: "Calcular saldo inicial" }).click();
  await expect(page.getByRole("heading", { name: "Revisa tu saldo inicial" })).toBeVisible();
  await expect(page.getByText(/Esta coincidencia no es una comprobación independiente/)).toBeVisible();
  await expect(page.getByText(/4 filas solapadas/)).toBeVisible();
  const saldoSinConfirmar: components["schemas"]["Saldo"] = await (await page.request.get("/api/saldo")).json();
  expect(saldoSinConfirmar.configuracion).toBeNull();
  await capturar(page, "saldo-inicial");
  await page.getByRole("button", { name: "Empezar con este saldo inicial" }).click();
  await expect(page.getByRole("heading", { name: "Tu historial del banco" })).toBeVisible();
  const resultado: components["schemas"]["ResultadoArranque"] = await (await page.request.get(new URL(page.url()).pathname.replace("/app/", "/api/"))).json();
  expect(resultado.importacion.saldo_centavos).toBe(10000000);
  expect(resultado.calculo.filas_solapadas).toBe(4);
  await capturar(page, "resultado");
  await page.getByRole("link", { name: "Categorizar lo nuevo" }).click();
  await expect(page.getByRole("heading", { name: "Categoriza lo nuevo" })).toBeVisible();
  await revisarAccesibilidad(page);
  await page.getByRole("link", { name: "Ver el resultado de la importación" }).click();
  await expect(page.getByRole("heading", { name: "Tu historial del banco" })).toBeVisible();
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Deshacer importación" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Deshacer importación" }).click();
  await expect(page.getByRole("heading", { name: "Historial restaurado" })).toBeVisible();
  await revisarAccesibilidad(page);
  expect((await (await page.request.get("/api/saldo")).json()).configuracion).toBeNull();
});
test("extender hacia atrás mantiene saldo actual y no repite los archivos solapados", async ({ page, request }) => {
  expect((await request.get("/e2e/datos/importacion-formatos")).ok()).toBe(true);
  await entrar(page, "/app/extender-historial");
  const saldoAntes: components["schemas"]["Saldo"] = await (await page.request.get("/api/saldo")).json();
  const codigo = "import io,sys\nfrom datetime import date\nfrom openpyxl import Workbook\nw=Workbook();s=w.active;s.title='Hoja 1';s.append(['Fecha','Descripción','Referencia','Valor']);s.append([date(2026,7,10),'COMPRA INVENTADA','',-100])\nf=io.BytesIO();w.save(f);sys.stdout.buffer.write(f.getvalue())";
  const excel = execFileSync(process.env.PYTHON ?? "python3", ["-X", "utf8", "-c", codigo]);
  await subir(page, "julio-A-INVENTADO.xlsx", excel);
  await subir(page, "julio-B-INVENTADO.xlsx", excel);
  await expect(page.getByLabel("Escribe el saldo que ves ahora en Bancolombia (opcional)")).toHaveValue("");
  await page.getByLabel("Escribe el saldo que ves ahora en Bancolombia (opcional)").fill("1.234,56");
  await page.getByRole("button", { name: "Calcular saldo inicial" }).click();
  await expect(page.getByRole("button", { name: "Extender con este saldo inicial" })).toBeVisible();
  await expect(page.getByText("Diferencia: banco menos app", { exact: true })).toBeVisible();
  await revisarAccesibilidad(page);
  await page.getByRole("button", { name: "Extender con este saldo inicial" }).click();
  await expect(page.getByRole("heading", { name: "Tu historial del banco" })).toBeVisible();
  const saldoDespues: components["schemas"]["Saldo"] = await (await page.request.get("/api/saldo")).json();
  expect(saldoDespues.saldo_centavos).toBe(saldoAntes.saldo_centavos);
  expect(saldoDespues.configuracion?.fecha_inicio).toBe("2026-07-10");
  const resultado: components["schemas"]["ResultadoArranque"] = await (await page.request.get(new URL(page.url()).pathname.replace("/app/", "/api/"))).json();
  expect(resultado.importacion.resumen.agregados).toBe(1);
  expect(resultado.calculo.filas_solapadas).toBe(1);
  await revisarAccesibilidad(page);
});
