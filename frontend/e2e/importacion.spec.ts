import {
  entrar,
  expect,
  revisarAccesibilidad,
  TAMANOS,
  prepararModo,
  test,
} from "./ayudas";
import { capturarImportacion } from "./capturas-importacion";
import type { components } from "../src/api/esquema";

for (const origen of ["gmail", "manual"] as const) {
  test(`confirmación exacta ${origen} informa un confirmado y cero nuevos en preview, detalle e Inicio`, async ({ page, request }) => {
    expect((await request.get(`/e2e/datos/importacion-confirmacion/${origen}`)).ok()).toBe(true);
    await entrar(page, "/app/importar");
    await page.waitForLoadState("networkidle");
    await page.getByLabel("Archivo Excel del banco").setInputFiles({
      name: "ingreso-INVENTADO.xlsx", mimeType: MIME_XLSX, buffer: excelIngresoInventado(),
    });
    await page.getByRole("button", { name: "Analizar archivo" }).click();
    const confirmacion = page.getByRole("listitem").filter({ has: page.getByText("Se confirman", { exact: true }) });
    await expect(confirmacion.getByText("1", { exact: true })).toBeVisible();
    await expect(page.getByRole("listitem").filter({ has: page.getByText("Se agregan", { exact: true }) }).getByText("0", { exact: true })).toBeVisible();
    await capturarImportacion(page, `confirmacion-${origen}-preview`);
    await page.getByRole("button", { name: "Sí, importar" }).click();
    await expect(page.getByRole("heading", { name: "Categoriza lo nuevo" })).toBeVisible();
    await page.getByRole("link", { name: "Ver el resultado de la importación" }).click();
    await expect(page.getByRole("listitem").filter({ has: page.getByText("Confirmados", { exact: true }) }).getByText("1", { exact: true })).toBeVisible();
    const ultima: components["schemas"]["UltimaImportacion"] = await (await page.request.get("/api/importaciones/ultima")).json();
    expect(ultima.importacion?.resumen.agregados).toBe(0);
    expect(ultima.importacion?.resumen.confirmados).toBe(1);
    expect(ultima.importacion?.saldo_centavos).toBe(100500);
    await capturarImportacion(page, `confirmacion-${origen}-detalle`);
    await page.goto("/app/");
    await expect(page.getByText("0 agregados, 0 ya estaban, 1 confirmados, 0 corregidos.")).toBeVisible();
    await capturarImportacion(page, `confirmacion-${origen}-inicio`);
  });
}
import { elegirReporte, excelInventado, excelIngresoInventado, MIME_XLSX } from "./excel-inventado";
test.beforeEach(async ({ request }) => {
  expect((await request.get("/e2e/datos/importacion")).ok()).toBe(true);
});

// Devuelve el escenario original para los archivos que siguen en la suite.
test.afterEach(async ({ page, request }) => {
  await page.waitForLoadState("networkidle");
  expect((await request.get("/e2e/datos/reiniciar")).ok()).toBe(true);
});

test("preview no guarda, descartar diagnóstico tampoco y confirmar lleva a categorizar", async ({
  page,
}) => {
  await entrar(page, "/app/importar");
  await capturarImportacion(page, "importar");
  await elegirReporte(page);
  await expect(
    page.getByRole("heading", { name: "Revisa antes de importar" }),
  ).toBeVisible();
  expect(
    (await (await page.request.get("/api/importaciones/ultima")).json())
      .importacion,
  ).toBeNull();
  await revisarAccesibilidad(page);
  await capturarImportacion(page, "vista-previa");
  await page.getByRole("button", { name: "No, revisar" }).click();
  await expect(
    page.getByRole("heading", { name: "Revisemos antes de importar" }),
  ).toBeVisible();
  expect(
    (await (await page.request.get("/api/importaciones/ultima")).json())
      .importacion,
  ).toBeNull();
  await capturarImportacion(page, "revisar");
  await page.getByRole("button", { name: "Elegir otro archivo" }).click();
  await elegirReporte(page);
  await page.getByRole("button", { name: "Sí, importar" }).click();
  await expect(
    page.getByRole("heading", { name: "Categoriza lo nuevo" }),
  ).toBeVisible();
  await revisarAccesibilidad(page);
  await capturarImportacion(page, "categorizar");
});

test("el candidato manual de un ingreso parecido se rotula A mano según el servidor", async ({ page, request }) => {
  expect((await request.get("/e2e/datos/importacion-confirmacion/manual?parecido=true")).ok()).toBe(true);
  await entrar(page, "/app/importar");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Archivo Excel del banco").setInputFiles({
    name: "ingreso-INVENTADO.xlsx", mimeType: MIME_XLSX, buffer: excelIngresoInventado(),
  });
  await page.getByRole("button", { name: "Analizar archivo" }).click();
  await page.getByRole("button", { name: "Sí, importar" }).click();
  await expect(page.getByRole("heading", { name: "Qué pasó" })).toBeVisible();
  await page.goto("/app/conciliacion/preguntas");
  await expect(page.getByText(/^A mano ·/)).toBeVisible();
  await expect(page.getByText(/^Del banco ·/)).toBeVisible();
  await expect(page.getByText(/^Del correo ·/)).toHaveCount(0);
  const preguntas: components["schemas"]["ListaPreguntasConciliacion"] = await (await page.request.get("/api/conciliacion/preguntas")).json();
  expect(preguntas.preguntas[0]?.candidatos[0]?.origen).toBe("manual");
  await capturarImportacion(page, "preguntas-ingreso-manual");
});

test("categorizar grupo crea empieza-por, siguiente reporte la aplica y undo importación restaura", async ({
  page,
}) => {
  await entrar(page, "/app/importar");
  await elegirReporte(page);
  await page.getByRole("button", { name: "Sí, importar" }).click();
  await expect(
    page.getByRole("heading", { name: "Categoriza lo nuevo" }),
  ).toBeVisible();
  await page
    .getByRole("listitem")
    .filter({
      has: page.getByText("TRANSPORTE VIAJES EJEMPLO", { exact: true }),
    })
    .getByRole("button", { name: "Transporte", exact: true })
    .click();
  await expect(
    page.getByText("2 movimientos categorizados en Transporte.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("listitem").filter({ has: page.getByText("ABONO EJEMPLO", { exact: true }) }).getByRole("button", { name: "Categorizar de ABONO EJEMPLO", exact: true }).click();
  await page
    .getByRole("button", { name: "Otros ingresos", exact: true })
    .click();
  await page
    .getByRole("link", { name: "Ver el resultado de la importación" })
    .click();
  await expect(page.getByRole("heading", { name: "Qué pasó" })).toBeVisible();
  await page.goto("/app/importar");
  await elegirReporte(page, true);
  await page.getByRole("button", { name: "Sí, importar" }).click();
  await expect(page.getByRole("heading", { name: "Qué pasó" })).toBeVisible();
  const ultima = (
    await (await page.request.get("/api/importaciones/ultima")).json()
  ).importacion;
  expect(ultima.sin_categoria).toBe(0);
  await capturarImportacion(page, "detalle");
  await page
    .getByRole("button", { name: "Deshacer importación", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await revisarAccesibilidad(page);
  await capturarImportacion(page, "deshacer-dialogo");
  await page.getByRole("button", { name: "Sí, deshacer importación" }).click();
  await expect(page.getByRole("status")).toContainText("Importación deshecha");
});

test("preguntas con sugerencias y no-en-banco se resuelven explícitamente y se deshacen", async ({
  page,
}) => {
  await entrar(page, "/app/importar");
  await elegirReporte(page);
  await page.getByRole("button", { name: "Sí, importar" }).click();
  await expect(
    page.getByRole("heading", { name: "Categoriza lo nuevo" }),
  ).toBeVisible();
  await page.goto("/app/conciliacion/preguntas");
  await expect(
    page.getByRole("heading", { name: "¿Es el mismo movimiento?" }),
  ).toBeVisible();
  await revisarAccesibilidad(page);
  await capturarImportacion(page, "preguntas");
  const pregunta = (
    await (await page.request.get("/api/conciliacion/preguntas")).json()
  ).preguntas[0];
  expect(pregunta).toBeTruthy();
  await page
    .getByRole("button", { name: pregunta.opciones[0].texto, exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Deshacer", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Deshacer", exact: true }).click();
  await expect(page.getByRole("heading", { name: /1 de 1/ })).toBeVisible();
  await page.goto("/app/conciliacion/no-esta-en-el-banco");
  await expect(
    page.getByRole("button", { name: "Borrar movimiento" }),
  ).toBeVisible();
  await revisarAccesibilidad(page);
  await capturarImportacion(page, "no-en-banco");
  await page.getByRole("button", { name: "Borrar movimiento" }).click();
  await page.getByRole("button", { name: "Deshacer", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Borrar movimiento" }),
  ).toBeVisible();
});

test("rechazo de formato y 409 requieren reanalizar sin confirmación automática", async ({
  page,
}) => {
  await entrar(page, "/app/importar");
  await page.getByLabel("Archivo Excel del banco").setInputFiles({
    name: "falso-EJEMPLO.xlsx",
    mimeType: MIME_XLSX,
    buffer: Buffer.from("archivo inventado inválido"),
  });
  await page.getByRole("button", { name: "Analizar archivo" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await elegirReporte(page);
  await expect(
    page.getByRole("heading", { name: "Revisa antes de importar" }),
  ).toBeVisible();
  await page.waitForLoadState("networkidle");
  const sesion = await (await page.request.get("/api/sesion")).json();
  const saldo = await (await page.request.get("/api/saldo")).json();
  const ingreso = await page.request.post("/api/ingresos", {
    headers: {
      "X-CSRF-Token": sesion.csrf_token,
      Origin: new URL(page.url()).origin,
    },
    data: {
      token: saldo.token_ingreso,
      monto_centavos: 100,
      fecha_hora: "2026-08-20T12:00:00",
      descripcion: "INGRESO CONCURRENTE EJEMPLO",
    },
  });
  expect(ingreso.ok()).toBe(true);
  await page.getByRole("button", { name: "Sí, importar" }).click();
  await expect(page.getByRole("alert")).toContainText("Algo cambió");
  await expect(
    page.getByRole("heading", { name: "Revisa antes de importar" }),
  ).toBeVisible();
  expect(
    (await (await page.request.get("/api/importaciones/ultima")).json())
      .importacion,
  ).toBeNull();
});

test("share target mantiene archivo soloRAM y entrega a la sesión tras login", async ({
  page,
}) => {
  await page.setViewportSize(TAMANOS.celular);
  await prepararModo(page, "oscuro");
  await page.goto("/app/");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
  const cuerpo = excelInventado().toString("base64");
  // Navegación POST equivalente al share target Android, sin scripts ni estilos en línea.
  await page.evaluate(
    ({ cuerpo, mime }) => {
      const bytes = Uint8Array.from(atob(cuerpo), (c) => c.charCodeAt(0));
      const formulario = document.createElement("form");
      formulario.method = "POST";
      formulario.action = "/app/compartir";
      formulario.enctype = "multipart/form-data";
      const entrada = document.createElement("input");
      entrada.type = "file";
      entrada.name = "archivo";
      const datos = new DataTransfer();
      datos.items.add(
        new File([bytes], "compartido-EJEMPLO.xlsx", { type: mime }),
      );
      entrada.files = datos.files;
      formulario.append(entrada);
      document.body.append(formulario);
      formulario.submit();
    },
    { cuerpo, mime: MIME_XLSX },
  );
  await expect(page.getByLabel("Contraseña")).toBeVisible();
  await page.waitForLoadState("networkidle");
  const otra = await page.context().newPage();
  await otra.goto("/app/importar");
  await otra.evaluate(() => navigator.serviceWorker.ready);
  await otra.waitForFunction(() => navigator.serviceWorker.controller !== null);
  const ajeno = await otra.evaluate(
    () =>
      new Promise<boolean>((resolve) => {
        const canal = new MessageChannel();
        canal.port1.onmessage = (evento) => {
          canal.port1.close();
          resolve(evento.data === null);
        };
        navigator.serviceWorker.controller!.postMessage(
          { tipo: "recibir-archivo-compartido" },
          [canal.port2],
        );
      }),
  );
  expect(ajeno).toBe(true);
  await otra.close();
  await page.getByLabel("Contraseña").fill("clave-e2e-inventada");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Revisa antes de importar" }),
  ).toBeVisible();
  expect(
    (await (await page.request.get("/api/importaciones/ultima")).json())
      .importacion,
  ).toBeNull();
  const rutas = await page.evaluate(async () => {
    const lista: string[] = [];
    for (const nombre of await caches.keys())
      for (const peticion of await (await caches.open(nombre)).keys())
        lista.push(new URL(peticion.url).pathname);
    return lista;
  });
  expect(
    rutas.filter(
      (r) =>
        r.includes("compartir") || r.includes(".xlsx") || r.startsWith("/api"),
    ),
  ).toEqual([]);
  await revisarAccesibilidad(page);
});

test("cerrar sesión elimina el archivo compartido pendiente de otra ventana", async ({
  page,
}) => {
  await page.goto("/app/");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
  const cuerpo = excelInventado().toString("base64");
  await page.evaluate(
    ({ cuerpo, mime }) => {
      const bytes = Uint8Array.from(atob(cuerpo), (c) => c.charCodeAt(0));
      const formulario = document.createElement("form");
      formulario.method = "POST";
      formulario.action = "/app/compartir";
      formulario.enctype = "multipart/form-data";
      const entrada = document.createElement("input");
      entrada.type = "file";
      entrada.name = "archivo";
      const datos = new DataTransfer();
      datos.items.add(
        new File([bytes], "pendiente-EJEMPLO.xlsx", { type: mime }),
      );
      entrada.files = datos.files;
      formulario.append(entrada);
      document.body.append(formulario);
      formulario.submit();
    },
    { cuerpo, mime: MIME_XLSX },
  );
  await expect(page.getByLabel("Contraseña")).toBeVisible();
  await page.waitForLoadState("networkidle");
  const otra = await page.context().newPage();
  await entrar(otra, "/app/mas");
  await otra.waitForLoadState("networkidle");
  await otra
    .getByRole("main")
    .getByRole("button", { name: "Cerrar sesión" })
    .click();
  await expect(otra.getByLabel("Contraseña")).toBeVisible();
  await otra.waitForLoadState("networkidle");
  await otra.close();
  await page.getByLabel("Contraseña").fill("clave-e2e-inventada");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "El archivo compartido ya no está disponible",
  );
  expect(
    (await (await page.request.get("/api/importaciones/ultima")).json())
      .importacion,
  ).toBeNull();
});


test("ingreso y ajuste del mismo día muestran signos y colores del servidor", async ({ page, request }) => {
  expect((await request.get("/e2e/datos/importacion-formatos")).ok()).toBe(true);
  await entrar(page, "/app/importar");
  await page.getByLabel("Archivo Excel del banco").setInputFiles({
    name: "ingreso-EJEMPLO.xlsx", mimeType: MIME_XLSX, buffer: excelIngresoInventado(),
  });
  await page.getByRole("button", { name: "Analizar archivo" }).click();
  await page.getByRole("button", { name: "Sí, importar" }).click();
  await expect(page.getByRole("heading", { name: "Qué pasó" })).toBeVisible();
  await page.goto("/app/conciliacion/preguntas");
  await expect(page.getByRole("heading", { name: /Ya estaba en el saldo/ })).toBeVisible();
  await expect(page.getByText(/\+.*5/, { exact: false })).toHaveClass(/text-monto-positivo/);
  await expect(page.getByText(/−.*5/, { exact: false })).toHaveClass(/text-monto-negativo/);
  await revisarAccesibilidad(page);
  await capturarImportacion(page, "preguntas-ajuste-ingreso");
});


test("deshacer un no-en-banco tras otra importación muestra conflicto y conserva saldo", async ({ page, context }) => {
  await entrar(page, "/app/importar");
  await elegirReporte(page);
  await page.getByRole("button", { name: "Sí, importar" }).click();
  await expect(page.getByRole("heading", { name: "Categoriza lo nuevo" })).toBeVisible();
  await page.goto("/app/conciliacion/no-esta-en-el-banco");
  await page.getByRole("button", { name: "Borrar movimiento" }).click();
  await expect(page.getByRole("button", { name: "Deshacer", exact: true })).toBeVisible();
  const otra = await context.newPage();
  try {
    await otra.goto("/app/importar");
    await otra.getByLabel("Archivo Excel del banco").setInputFiles({
      name: "reporte-posterior-EJEMPLO.xlsx",
      mimeType: MIME_XLSX,
      buffer: excelInventado(true, true),
    });
    await otra.getByRole("button", { name: "Analizar archivo" }).click();
    await otra.getByRole("button", { name: "Sí, importar" }).click();
    await expect(otra.getByRole("heading", { name: "Categoriza lo nuevo" })).toBeVisible();
    await otra.waitForLoadState("networkidle");
    const saldoAntes = (await (await otra.request.get("/api/saldo")).json()).saldo_centavos;
    expect(typeof saldoAntes).toBe("number");
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: "Deshacer", exact: true }).click();
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByRole("button", { name: "Borrar movimiento" })).toHaveCount(0);
    expect((await (await page.request.get("/api/saldo")).json()).saldo_centavos).toBe(saldoAntes);
  } finally {
    await otra.waitForLoadState("networkidle");
    await otra.close();
  }
});


test("candidatos indistinguibles comparten etiquetas humanas en filas y opciones", async ({ page, request }) => {
  expect((await request.get("/e2e/datos/importacion-candidatos")).ok()).toBe(true);
  await entrar(page, "/app/importar");
  await elegirReporte(page);
  await page.getByRole("button", { name: "Sí, importar" }).click();
  await expect(page.getByRole("heading", { name: "Categoriza lo nuevo" })).toBeVisible();
  await page.goto("/app/conciliacion/preguntas");
  await expect(page.getByRole("heading", { name: /Cuál es el mismo/ })).toBeVisible();
  await expect(page.getByText("Candidato 1 ·", { exact: true })).toBeVisible();
  await expect(page.getByText("Candidato 2 ·", { exact: true })).toBeVisible();
  const pregunta = (await (await page.request.get("/api/conciliacion/preguntas")).json()).preguntas[0];
  expect(pregunta.candidatos.map((c: components["schemas"]["DatoConciliacion"]) => c.etiqueta)).toEqual(["Candidato 1", "Candidato 2"]);
  for (const opcion of pregunta.opciones) {
    await expect(page.getByRole("button", { name: opcion.texto, exact: true })).toBeVisible();
    expect(opcion.texto).not.toMatch(/movimiento \d/);
  }
  await capturarImportacion(page, "preguntas-candidatos");
});
