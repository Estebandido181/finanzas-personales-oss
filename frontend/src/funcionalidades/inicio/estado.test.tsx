import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import type { Esquemas } from "@/compartido/http/cliente";
import { ProveedorSesion } from "@/funcionalidades/sesion/sesion";
import { simularApi, SESION_INVENTADA } from "@/pruebas/api-simulada";
import { EstadoRevisionesInicio } from "@/funcionalidades/inicio/estado";

const alDia: Esquemas["EstadoInicio"] = { todo_al_dia: true, total_acciones: 0, texto: "Todo al día", areas: [] };
const pendiente: Esquemas["EstadoInicio"] = { todo_al_dia: false, total_acciones: 1, texto: "1 cosa por revisar", areas: [{ codigo: "preguntas", cantidad: 1, titulo: "Preguntas de conciliación", href: "/conciliacion/preguntas" }] };
const ok = (cuerpo: Esquemas["EstadoInicio"]) => ({ estado: 200, cuerpo });
function montar(respuesta = ok(alDia), manejador?: Parameters<typeof simularApi>[0][string]) {
  const api = simularApi({ "GET /api/sesion": { estado: 200, cuerpo: SESION_INVENTADA }, "GET /api/inicio/estado": manejador ?? respuesta });
  const contenido = (revision: string, ocupado: boolean) => <ProveedorSesion cliente={api.cliente}><EstadoRevisionesInicio revision={revision} ocupado={ocupado} /></ProveedorSesion>;
  const vista = render(contenido("inicial", false));
  return { ...api, cambiar: (revision: string, ocupado: boolean) => vista.rerender(contenido(revision, ocupado)) };
}
it("muestra Todo al día solo por el estado y texto del servidor, sin enlaces extra", async () => {
  const api = montar();
  expect(await screen.findByText("Todo al día")).toBeVisible();
  expect(screen.queryByRole("link")).toBeNull();
  expect(api.peticiones.filter((p) => p.url.endsWith("/api/inicio/estado"))).toHaveLength(1);
});
it("respeta el singular y usa exclusivamente los destinos y el total recibidos", async () => {
  const api = montar(ok(pendiente));
  await userEvent.click(await screen.findByText("1 cosa por revisar"));
  const lista = screen.getByRole("list", { name: "Revisiones pendientes" });
  expect(within(lista).getByRole("link", { name: "Preguntas de conciliación: 1" })).toHaveAttribute("href", "/conciliacion/preguntas");
  api.rutas["GET /api/inicio/estado"] = ok({ ...pendiente, total_acciones: 47, texto: "47 cosas por revisar" });
  api.cambiar("nueva-lectura", false);
  expect(await screen.findByText("47 cosas por revisar")).toBeVisible();
  expect(screen.queryByText("1 cosa por revisar")).toBeNull();
});
it("carga y error no prometen Todo al día; reintentar vuelve a consultar", async () => {
  let resolver!: (respuesta: { estado: number; cuerpo: unknown }) => void;
  const api = montar(ok(alDia), () => new Promise((r) => { resolver = r; }));
  expect(screen.getByRole("status")).toHaveTextContent("Consultando las revisiones…");
  expect(screen.queryByText("Todo al día")).toBeNull();
  resolver({ estado: 503, cuerpo: { detalle: "Falla inventada." } });
  expect(await screen.findByRole("alert")).toHaveTextContent("No se pudieron consultar las revisiones");
  expect(screen.queryByText("Todo al día")).toBeNull();
  api.rutas["GET /api/inicio/estado"] = ok(pendiente);
  await userEvent.click(screen.getByRole("button", { name: "Volver a consultar las revisiones" }));
  expect(await screen.findByText("1 cosa por revisar")).toBeVisible();
});
it("sincronizar invalida una consulta retrasada y consulta el estado actualizado al terminar", async () => {
  let resolver!: (respuesta: ReturnType<typeof ok>) => void;
  const api = montar(ok(alDia), () => new Promise((r) => { resolver = r; }));
  api.cambiar("inicial", true);
  resolver(ok(alDia));
  await waitFor(() => expect(screen.queryByText("Todo al día")).toBeNull());
  api.rutas["GET /api/inicio/estado"] = ok(pendiente);
  api.cambiar("tras-sincronizar", false);
  expect(await screen.findByText("1 cosa por revisar")).toBeVisible();
  expect(api.peticiones.filter((p) => p.url.endsWith("/api/inicio/estado"))).toHaveLength(2);
});
