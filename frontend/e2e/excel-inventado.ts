/** Excel exclusivamente inventado, generado en RAM: ningún .xlsx en Git. */
import { execFileSync } from "node:child_process";
import type { Page } from "@playwright/test";
export const MIME_XLSX =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
export function excelInventado(nuevo = false, conAusente = false): Buffer {
  const codigo = `import io,sys\nfrom datetime import date\nfrom openpyxl import Workbook\nw=Workbook();s=w.active;s.title='Hoja 1';s.append(['Fecha','Descripción','Referencia','Valor'])\nfilas=[(10,'COMPRA PUNTO EJEMPLO',-36000),(11,'TRANSPORTE VIAJES EJEMPLO',-6200),(12,'TRANSPORTE VIAJES EJEMPLO',-6200),(13,'ABONO EJEMPLO',10000)]\n${nuevo ? "filas.append((14,'TRANSPORTE VIAJES EJEMPLO',-6200))" : ""}\n${conAusente ? "filas.append((11,'TIENDA AUSENTE EJEMPLO',-89900))" : ""}\nfor dia,texto,valor in filas:s.append([date(2026,8,dia),texto,'',valor])\nf=io.BytesIO();w.save(f);sys.stdout.buffer.write(f.getvalue())`;
  return execFileSync(process.env.PYTHON ?? "python3", [
    "-X",
    "utf8",
    "-c",
    codigo,
  ]);
}
export async function elegirReporte(page: Page, nuevo = false): Promise<void> {
  await page.waitForLoadState("networkidle");
  await page
    .getByLabel("Archivo Excel del banco")
    .setInputFiles({
      name: "reporte-EJEMPLO.xlsx",
      mimeType: MIME_XLSX,
      buffer: excelInventado(nuevo),
    });
  await page.getByRole("button", { name: "Analizar archivo" }).click();
}


export function excelIngresoInventado(): Buffer {
  const codigo = "import io,sys\nfrom datetime import date\nfrom openpyxl import Workbook\nw=Workbook();s=w.active;s.title='Hoja 1';s.append(['Fecha','Descripción','Referencia','Valor']);s.append([date(2026,8,10),'ABONO INVENTADO','',5])\nf=io.BytesIO();w.save(f);sys.stdout.buffer.write(f.getvalue())";
  return execFileSync(process.env.PYTHON ?? "python3", ["-X", "utf8", "-c", codigo]);
}
