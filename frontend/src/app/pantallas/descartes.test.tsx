import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { it, expect } from "vitest";
import { memoryLocation } from "wouter/memory-location";
import { App } from "@/app/app";
import type { Esquemas } from "@/compartido/http/cliente";
import { simularApi, SESION_INVENTADA, TOKEN_INVENTADO, type Manejador, type Respuesta } from "@/pruebas/api-simulada";
import { movimientoInventado, reporteInventado, sincronizacionCorrecta } from "@/pruebas/inicio-inventado";

const ok = (cuerpo: unknown): Respuesta => ({ estado: 200, cuerpo });
const movimiento = movimientoInventado({ id: 51, descripcion: "COMPRA INVENTADA", pendiente: false, categorizable: false,
  puede_descartar: true, monto_centavos: 2000 });
const descartado: Esquemas["MovimientoDescartado"] = {
  id: 51, descarte_id: 1, descripcion: "COMPRA INVENTADA", tipo: "compra", origen: "gmail", monto_centavos: 5000,
  fecha_hora: "2026-09-30T12:00:00", descartado_en: "2026-09-30T13:00:00", referencia: null,
  descartado: true, puede_descartar: false, motivo_no_descartar: "Ya está descartado.", puede_restaurar: true, motivo_no_restaurar: null,
};
const resultado = (descartado: boolean): Esquemas["ResultadoDescarte"] => ({
  movimiento_id: 51, monto_centavos: descartado ? 2000 : 5000, saldo_antes_centavos: 25000, saldo_despues_centavos: 29000,
  descartado, puede_descartar: !descartado, motivo_no_descartar: null, puede_restaurar: descartado, motivo_no_restaurar: null,
});
function montar({ vista = false, lista = [movimiento], apartados = [descartado], rutas = {} }: {
  vista?: boolean; lista?: Esquemas["Movimiento"][]; apartados?: Esquemas["MovimientoDescartado"][];
  rutas?: Record<string, Manejador | Respuesta>;
} = {}) {
  const api = simularApi({
    "GET /api/sesion": ok(SESION_INVENTADA), "GET /api/no-reconocidos": ok({ correos: [] }),
    "GET /api/sincronizacion": ok(sincronizacionCorrecta()), "GET /api/categorias": ok({ categorias: [] }),
    "GET /api/reporte": ok(reporteInventado({ pendientes: 0 })),
    "GET /api/movimientos": () => ok({ mes: "2026-09", movimientos: lista }),
    "GET /api/movimientos/descartados": () => ok({ movimientos: apartados }),
    "POST /api/movimientos/51/descartar": () => { lista = []; return ok(resultado(true)); },
    "POST /api/movimientos/51/restaurar": () => { apartados = []; return ok(resultado(false)); },
    ...rutas,
  });
  const ubicacion = memoryLocation({ path: "/movimientos", searchPath: vista ? "ver=descartados" : "", record: true });
  render(<App cliente={api.cliente} hook={ubicacion.hook} searchHook={ubicacion.searchHook} />);
  return { ...api, ubicacion, usuario: userEvent.setup() };
}

it("descartar requiere confirmación, envía CSRF y muestra los saldos exactos del servidor", async () => {
  const api = montar();
  await api.usuario.click(await screen.findByRole("button", { name: "Descartar COMPRA INVENTADA" }));
  const dialogo = screen.getByRole("dialog");
  expect(within(dialogo).getByText(/Quedará fuera del saldo/)).toBeVisible();
  expect(api.peticiones.filter((p) => p.method === "POST")).toHaveLength(0);
  await api.usuario.click(within(dialogo).getByRole("button", { name: "Sí, descartar movimiento" }));
  expect(await screen.findByRole("heading", { name: "Movimiento descartado" })).toBeVisible();
  const aviso = screen.getByRole("status");
  expect(aviso).toHaveTextContent("Saldo antes: $250");
  expect(aviso).toHaveTextContent("Saldo después: $290");
  expect(api.peticiones.find((p) => p.method === "POST")!.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
  expect(api.peticiones.find((p) => p.method === "POST")!.headers.get("Content-Type")).toBe("application/json");
  await waitFor(() => expect(screen.queryByRole("button", { name: "Descartar COMPRA INVENTADA" })).toBeNull());
});

it("los permisos y motivos de bloqueo se muestran sin inferirlos", async () => {
  montar({ lista: [{ ...movimiento, puede_descartar: false, motivo_no_descartar: "Hay un ajuste posterior." }] });
  expect(await screen.findByRole("button", { name: "Descartar COMPRA INVENTADA" })).toBeDisabled();
  expect(screen.getByText("Hay un ajuste posterior.")).toBeVisible();
});

it("restaurar usa el monto actual mostrado y la vista de todos los meses se recarga", async () => {
  const api = montar({ vista: true });
  await api.usuario.click(await screen.findByRole("button", { name: "Restaurar COMPRA INVENTADA" }));
  const dialogo = screen.getByRole("dialog");
  expect(within(dialogo).getByText(/Se restaurará el monto actual/)).toBeVisible();
  expect(dialogo).toHaveTextContent("Monto actual: $50");
  await api.usuario.click(within(dialogo).getByRole("button", { name: "Sí, restaurar movimiento" }));
  expect(await screen.findByRole("heading", { name: "Movimiento restaurado" })).toBeVisible();
  expect(await screen.findByText("Sin movimientos descartados")).toBeVisible();
});

it("una respuesta tardía no muestra el resultado en otro filtro y bloquea el doble envío", async () => {
  let terminar!: (respuesta: Respuesta) => void;
  const api = montar({ rutas: { "POST /api/movimientos/51/descartar": () => new Promise<Respuesta>((resolve) => { terminar = resolve; }) } });
  await api.usuario.click(await screen.findByRole("button", { name: "Descartar COMPRA INVENTADA" }));
  await api.usuario.click(screen.getByRole("button", { name: "Sí, descartar movimiento" }));
  expect(screen.getByRole("button", { name: "Guardando…" })).toBeDisabled();
  await api.usuario.click(screen.getByRole("button", { name: "Guardando…" }));
  expect(api.peticiones.filter((p) => p.method === "POST")).toHaveLength(1);
  await act(async () => { api.ubicacion.navigate("/movimientos?ver=descartados"); });
  await act(async () => { terminar(ok(resultado(true))); });
  await screen.findByRole("list", { name: "Movimientos descartados" });
  expect(screen.queryByRole("heading", { name: "Movimiento descartado" })).toBeNull();
});

it("un conflicto recarga los permisos del servidor y conserva el mensaje", async () => {
  const bloqueado = { ...movimiento, puede_descartar: false, motivo_no_descartar: "Responde primero la pregunta pendiente." };
  let cambio = false;
  const api = montar({ rutas: {
    "GET /api/movimientos": () => ok({ mes: "2026-09", movimientos: [cambio ? bloqueado : movimiento] }),
    "POST /api/movimientos/51/descartar": () => { cambio = true; return { estado: 409, cuerpo: { detalle: bloqueado.motivo_no_descartar } }; },
  } });
  await api.usuario.click(await screen.findByRole("button", { name: "Descartar COMPRA INVENTADA" }));
  await api.usuario.click(screen.getByRole("button", { name: "Sí, descartar movimiento" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Responde primero la pregunta pendiente.");
  await waitFor(() => expect(screen.getByRole("button", { name: "Descartar COMPRA INVENTADA" })).toBeDisabled());
});
