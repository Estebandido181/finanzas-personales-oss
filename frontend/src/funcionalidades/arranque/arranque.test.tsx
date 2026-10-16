import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { memoryLocation } from "wouter/memory-location";
import { App } from "@/app/app";
import { simularApi, SESION_INVENTADA, TOKEN_INVENTADO } from "@/pruebas/api-simulada";
import { archivosInventados, previaArranqueInventada, resultadoArranqueInventado, ESTADO_ARRANQUE_INVENTADO } from "@/pruebas/arranque-inventado";
import { detalleInventado } from "@/pruebas/importacion-inventada";
import { reporteInventado, sincronizacionCorrecta } from "@/pruebas/inicio-inventado";
const ok = (cuerpo: unknown) => ({ estado: 200, cuerpo });
function montar(rutas: Parameters<typeof simularApi>[0] = {}, path = "/arranque") {
  const api = simularApi({ "GET /api/sesion": ok(SESION_INVENTADA), "GET /api/arranque/estado": ok(ESTADO_ARRANQUE_INVENTADO), ...rutas });
  render(<App cliente={api.cliente} hook={memoryLocation({ path }).hook} />);
  return api;
}
async function subir(usuario: ReturnType<typeof userEvent.setup>, nombre = "mes-A-INVENTADO.xlsx") {
  await usuario.upload(await screen.findByLabelText("Archivo Excel del banco"), new File(["inventado"], nombre, { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
}
it("renumera nombres al quitar el primer archivo y agregar otro; usa token renovado y CSRF", async () => {
  let cantidad = 0;
  const api = montar({ "POST /api/arranque/archivos": () => ok(archivosInventados(++cantidad)), "DELETE /api/arranque/archivos/1": () => { cantidad--; return ok(archivosInventados(cantidad)); } });
  const usuario = userEvent.setup();
  await subir(usuario); await screen.findByText("mes-A-INVENTADO.xlsx");
  await subir(usuario, "mes-B-INVENTADO.xlsx"); await screen.findByText("mes-B-INVENTADO.xlsx");
  await usuario.click(screen.getByRole("button", { name: "Quitar mes-A-INVENTADO.xlsx" }));
  await waitFor(() => expect(screen.queryByText("mes-A-INVENTADO.xlsx")).not.toBeInTheDocument());
  await subir(usuario, "mes-C-INVENTADO.xlsx");
  expect(await screen.findByText("mes-C-INVENTADO.xlsx")).toBeVisible();
  expect(screen.getByRole("button", { name: "Quitar mes-B-INVENTADO.xlsx" })).toBeVisible();
  const ultima = api.peticiones.filter((p) => p.method === "POST").at(-1)!;
  expect(ultima.headers.get("x-historial-token")).toBe("archivos-inventados-1");
  expect(ultima.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
});
it("la ayuda pide descargas que se solapen un día", async () => {
  montar();
  expect(await screen.findByText(/Haz que cada descarga empiece el último día de la anterior: el primer día de cada archivo puede venir incompleto\./)).toBeVisible();
  expect(screen.queryByText(/Sube un mes y después agrega otro/)).toBeNull();
});
it("muestra el cálculo exacto del servidor, conserva centavos y no confirma al calcular", async () => {
  const api = montar({ "POST /api/arranque/archivos": ok(archivosInventados()), "POST /api/arranque/calcular": ok(previaArranqueInventada({ saldo_inicial_centavos: -123, huecos: [{ desde: "2026-08-15", hasta: "2026-08-17" }] })) });
  const usuario = userEvent.setup(); await subir(usuario);
  await usuario.type(screen.getByLabelText("Escribe el saldo que ves ahora en Bancolombia"), "1.234,56");
  await usuario.click(screen.getByRole("button", { name: "Calcular saldo inicial" }));
  expect(await screen.findByText("−$1,23")).toBeVisible();
  expect(screen.getByText(/Revisa el periodo del/)).toBeVisible();
  const calculo = api.peticiones.find((p) => p.url.endsWith("/calcular"))!;
  expect(await calculo.json()).toEqual({ token: "archivos-inventados-1", modo: "arranque", saldo_actual_centavos: 123456 });
  expect(api.peticiones.some((p) => p.url.endsWith("/confirmar"))).toBe(false);
});
it("bloquea mutaciones mientras calcula y 409 pide revisión nueva", async () => {
  let resolver!: (valor: ReturnType<typeof ok>) => void;
  const api = montar({ "POST /api/arranque/archivos": ok(archivosInventados()), "POST /api/arranque/calcular": () => new Promise((r) => { resolver = r; }), "POST /api/arranque/confirmar": { estado: 409, cuerpo: { detalle: "Cambió el historial; revisa el cálculo." } } });
  const usuario = userEvent.setup(); await subir(usuario); await usuario.type(screen.getByLabelText("Escribe el saldo que ves ahora en Bancolombia"), "0");
  await usuario.click(screen.getByRole("button", { name: "Calcular saldo inicial" }));
  expect(screen.getByRole("button", { name: "Quitar mes-A-INVENTADO.xlsx" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Agregar otro archivo" })).toBeDisabled();
  resolver(ok(previaArranqueInventada()));
  await usuario.click(await screen.findByRole("button", { name: "Empezar con este saldo inicial" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "Empezar con este saldo inicial" })).not.toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Calcular saldo inicial" })).toBeEnabled();
  expect(api.peticiones.filter((p) => p.url.endsWith("/confirmar"))).toHaveLength(1);
});
it("410 conserva el error y exige elegir archivos otra vez", async () => {
  montar({ "POST /api/arranque/archivos": ok(archivosInventados()), "POST /api/arranque/calcular": { estado: 410, cuerpo: { detalle: "La revisión venció." } } });
  const usuario = userEvent.setup(); await subir(usuario); await usuario.type(screen.getByLabelText("Escribe el saldo que ves ahora en Bancolombia"), "0"); await usuario.click(screen.getByRole("button", { name: "Calcular saldo inicial" }));
  expect(await screen.findByText(/La revisión venció. Elige/)).toBeVisible();
  expect(screen.getByRole("button", { name: "Calcular saldo inicial" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Elegir archivo" })).toBeEnabled();
});
it("410 al confirmar olvida tokens y nombres; mantiene aviso hasta validar nuevos archivos", async () => {
  let subidas = 0;
  const api = montar({
    "POST /api/arranque/archivos": () => ++subidas === 2 ? { estado: 415, cuerpo: { detalle: "Elige un Excel válido." } } : ok(archivosInventados()),
    "POST /api/arranque/calcular": ok(previaArranqueInventada()),
    "POST /api/arranque/confirmar": { estado: 410, cuerpo: { detalle: "La revisión venció." } },
  });
  const usuario = userEvent.setup(); await subir(usuario);
  await usuario.type(screen.getByLabelText("Escribe el saldo que ves ahora en Bancolombia"), "0");
  await usuario.click(screen.getByRole("button", { name: "Calcular saldo inicial" }));
  await usuario.click(await screen.findByRole("button", { name: "Empezar con este saldo inicial" }));
  expect(await screen.findByText(/La revisión venció. Elige/)).toBeVisible();
  expect(screen.getByRole("button", { name: "Calcular saldo inicial" })).toBeDisabled();
  expect(screen.queryByText("mes-A-INVENTADO.xlsx")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Descartar archivos" })).not.toBeInTheDocument();
  await subir(usuario, "invalido-INVENTADO.xlsx");
  expect(await screen.findByText("Elige un Excel válido.")).toBeVisible();
  expect(screen.getByText(/La revisión venció. Elige/)).toBeVisible();
  await subir(usuario, "nuevo-INVENTADO.xlsx");
  expect(await screen.findByText("nuevo-INVENTADO.xlsx")).toBeVisible();
  expect(screen.queryByText(/La revisión venció. Elige/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Calcular saldo inicial" })).toBeEnabled();
  const subidasEnviadas = api.peticiones.filter((p) => p.method === "POST" && p.url.endsWith("/archivos"));
  expect(subidasEnviadas).toHaveLength(3);
  for (const p of subidasEnviadas.slice(1)) expect(p.headers.has("x-historial-token")).toBe(false);
});
it("extensión admite comprobación opcional sin deducir saldo actual", async () => {
  const api = montar({ "GET /api/arranque/estado": ok({ ...ESTADO_ARRANQUE_INVENTADO, mostrar_arranque_inicial: false, puede_extender_historial: true }), "POST /api/arranque/archivos": ok(archivosInventados()), "POST /api/arranque/calcular": ok(previaArranqueInventada({ modo: "extension" })) }, "/extender-historial");
  const usuario = userEvent.setup(); await subir(usuario);
  expect(screen.getByLabelText("Escribe el saldo que ves ahora en Bancolombia (opcional)")).toHaveValue("");
  await usuario.click(screen.getByRole("button", { name: "Calcular saldo inicial" }));
  expect(await screen.findByRole("button", { name: "Extender con este saldo inicial" })).toBeVisible();
  expect((await api.peticiones.find((p) => p.url.endsWith("/calcular"))!.json()).modo).toBe("extension");
});
it("extensión envía el saldo observado solo como referencia opcional de comprobación", async () => {
  const api = montar({ "GET /api/arranque/estado": ok({ ...ESTADO_ARRANQUE_INVENTADO, mostrar_arranque_inicial: false, puede_extender_historial: true }), "POST /api/arranque/archivos": ok(archivosInventados()), "POST /api/arranque/calcular": ok(previaArranqueInventada({ modo: "extension" })) }, "/extender-historial");
  const usuario = userEvent.setup(); await subir(usuario);
  await usuario.type(screen.getByLabelText("Escribe el saldo que ves ahora en Bancolombia (opcional)"), "1.234,56");
  await usuario.click(screen.getByRole("button", { name: "Calcular saldo inicial" }));
  await screen.findByRole("button", { name: "Extender con este saldo inicial" });
  expect(await api.peticiones.find((p) => p.url.endsWith("/calcular"))!.json()).toEqual({ token: "archivos-inventados-1", modo: "extension", saldo_actual_centavos: 0, saldo_real_centavos: 123456 });
});
it("deshacer usa la guarda del servidor y retorna configuración nula sin inventar saldo", async () => {
  const get = vi.fn().mockReturnValueOnce(ok(resultadoArranqueInventado())).mockReturnValue(ok(resultadoArranqueInventado({ fase: "deshecho", fecha_inicio: null, saldo_inicial_centavos: null, importacion: detalleInventado({ se_puede_deshacer: false, saldo_centavos: null, motivo_no_deshacer: "La importación ya está deshecha." }) })));
  const api = montar({ "GET /api/arranque/1": get, "POST /api/arranque/1/deshacer": ok(resultadoArranqueInventado()) }, "/arranque/1");
  const usuario = userEvent.setup(); await usuario.click(await screen.findByRole("button", { name: "Deshacer importación" }));
  await usuario.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Deshacer importación" }));
  expect(await screen.findByRole("heading", { name: "Historial restaurado" })).toBeVisible();
  expect(screen.queryByText("$0")).not.toBeInTheDocument();
  expect(api.peticiones.find((p) => p.method === "POST")!.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
});
it("Inicio abre arranque solo por la señal explícita del servidor", async () => {
  montar({ "GET /api/reporte": ok(reporteInventado()), "GET /api/movimientos": ok({ mes: "2026-09", movimientos: [] }), "GET /api/sincronizacion": ok(sincronizacionCorrecta()) }, "/");
  expect(await screen.findByRole("heading", { name: "Empieza con tu historial del banco" })).toBeVisible();
});
it("no ofrece extensión si el servidor niega el permiso", async () => {
  montar({}, "/extender-historial");
  expect(await screen.findByText("Configura primero tu saldo para extender el historial.")).toBeVisible();
  expect(screen.queryByLabelText("Archivo Excel del banco")).not.toBeInTheDocument();
});
