import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { memoryLocation } from "wouter/memory-location";
import { App } from "@/app/app";
import {
  simularApi,
  SESION_INVENTADA,
  TOKEN_INVENTADO,
} from "@/pruebas/api-simulada";
import {
  vistaInventada,
  detalleInventado,
  CONTEOS_INVENTADOS,
} from "@/pruebas/importacion-inventada";
const ok = (cuerpo: unknown) => ({ estado: 200, cuerpo });
async function elegir(usuario: ReturnType<typeof userEvent.setup>) {
  await usuario.upload(
    await screen.findByLabelText("Archivo Excel del banco"),
    new File(["xlsx inventado"], "reporte-EJEMPLO.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }),
  );
  await usuario.click(screen.getByRole("button", { name: "Analizar archivo" }));
}
it.each([
  { nombre: "solo anteriores", sin_cambios: true, anteriores: 4, permitido: true },
  { nombre: "anteriores y nuevas", sin_cambios: false, anteriores: 2, permitido: true },
  { nombre: "permiso denegado", sin_cambios: true, anteriores: 4, permitido: false },
])("ofrece extensión según servidor con $nombre", async ({ sin_cambios, anteriores, permitido }) => {
  const api = simularApi({ "GET /api/sesion": ok(SESION_INVENTADA), "POST /api/importaciones/analizar": ok(vistaInventada({ sin_cambios, puede_extender_historial: permitido, resumen: { ...CONTEOS_INVENTADOS, anteriores } })) });
  render(<App cliente={api.cliente} hook={memoryLocation({ path: "/importar" }).hook} />);
  await elegir(userEvent.setup());
  await screen.findByRole("heading", { name: "Revisa antes de importar" });
  expect(screen.getByText(/movimientos son anteriores/)).toBeVisible();
  if (permitido) expect(screen.getByRole("link", { name: "Extender historial" })).toHaveAttribute("href", "/extender-historial");
  else expect(screen.queryByRole("link", { name: "Extender historial" })).not.toBeInTheDocument();
});
it("muestra saldos/conteos del servidor; no confirma al analizar y envía CSRF", async () => {
  const api = simularApi({
    "GET /api/sesion": ok(SESION_INVENTADA),
    "POST /api/importaciones/analizar": ok(vistaInventada()),
  });
  render(
    <App
      cliente={api.cliente}
      hook={memoryLocation({ path: "/importar" }).hook}
    />,
  );
  const usuario = userEvent.setup();
  await elegir(usuario);
  await screen.findByRole("heading", { name: "Revisa antes de importar" });
  expect(screen.getByText("$4.739.150")).toBeVisible();
  expect(screen.getByText("−$63.000")).toBeVisible();
  expect(
    api.peticiones.filter(
      (p) =>
        p.method === "POST" && new URL(p.url).pathname === "/api/importaciones",
    ),
  ).toHaveLength(0);
  const enviada = api.peticiones.find((p) =>
    new URL(p.url).pathname.endsWith("/analizar"),
  )!;
  expect(enviada.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
  expect(enviada.headers.get("Content-Type")).toContain("spreadsheetml.sheet");
});

it("preview cuenta una confirmación sin agregar ni volver a contar el movimiento", async () => {
  const api = simularApi({
    "GET /api/sesion": ok(SESION_INVENTADA),
    "POST /api/importaciones/analizar": ok(vistaInventada({
      resumen: { ...CONTEOS_INVENTADOS, agregados: 0, ya_estaban: 0, confirmados: 1, corregidos: 0 },
    })),
  });
  render(<App cliente={api.cliente} hook={memoryLocation({ path: "/importar" }).hook} />);
  await elegir(userEvent.setup());
  const fila = (await screen.findByText("Se confirman")).closest("li")!;
  expect(within(fila).getByText("1", { exact: true })).toBeVisible();
  expect(within(screen.getByText("Se agregan").closest("li")!).getByText("0", { exact: true })).toBeVisible();
  expect(within(screen.getByText("Ya están").closest("li")!).getByText("0", { exact: true })).toBeVisible();
});

it("detalle mantiene separadas las confirmaciones de los movimientos nuevos", async () => {
  const api = simularApi({
    "GET /api/sesion": ok(SESION_INVENTADA),
    "GET /api/importaciones/ultima": ok({ importacion: detalleInventado({
      resumen: { ...CONTEOS_INVENTADOS, agregados: 0, ya_estaban: 0, confirmados: 1, corregidos: 0 },
    }) }),
  });
  render(<App cliente={api.cliente} hook={memoryLocation({ path: "/importacion" }).hook} />);
  const fila = (await screen.findByText("Confirmados")).closest("li")!;
  expect(within(fila).getByText("1", { exact: true })).toBeVisible();
});
it("409 vuelve a analizar y exige otra confirmación del dueño", async () => {
  const analizar = vi.fn(() => ok(vistaInventada()));
  const api = simularApi({
    "GET /api/sesion": ok(SESION_INVENTADA),
    "POST /api/importaciones/analizar": analizar,
    "POST /api/importaciones": {
      estado: 409,
      cuerpo: { detalle: "Cambió el estado." },
    },
  });
  render(
    <App
      cliente={api.cliente}
      hook={memoryLocation({ path: "/importar" }).hook}
    />,
  );
  const usuario = userEvent.setup();
  await elegir(usuario);
  await usuario.click(
    await screen.findByRole("button", { name: "Sí, importar" }),
  );
  await screen.findByRole("heading", { name: "Revisa antes de importar" });
  await waitFor(() => expect(analizar).toHaveBeenCalledTimes(2));
  expect(screen.getByRole("alert")).toHaveTextContent("Algo cambió");
  expect(
    api.peticiones.filter(
      (p) =>
        p.method === "POST" && new URL(p.url).pathname === "/api/importaciones",
    ),
  ).toHaveLength(1);
});
it("410 impide repetir confirmación con token vencido y ofrece reanalizar", async () => {
  const api = simularApi({
    "GET /api/sesion": ok(SESION_INVENTADA),
    "POST /api/importaciones/analizar": ok(vistaInventada()),
    "POST /api/importaciones": {
      estado: 410,
      cuerpo: { detalle: "El análisis venció." },
    },
  });
  render(
    <App
      cliente={api.cliente}
      hook={memoryLocation({ path: "/importar" }).hook}
    />,
  );
  const usuario = userEvent.setup();
  await elegir(usuario);
  await usuario.click(
    await screen.findByRole("button", { name: "Sí, importar" }),
  );
  expect(
    await screen.findByRole("button", { name: "Analizar otra vez" }),
  ).toBeEnabled();
  expect(screen.queryByRole("button", { name: "Sí, importar" })).toBeNull();
});
it("deshacer solo se ofrece cuando lo permite el servidor y exige confirmar", async () => {
  const api = simularApi({
    "GET /api/sesion": ok(SESION_INVENTADA),
    "GET /api/importaciones/ultima": ok({ importacion: detalleInventado() }),
    "POST /api/importaciones/1/deshacer": ok(
      detalleInventado({
        deshecha_en: "2026-10-02T17:00:00",
        se_puede_deshacer: false,
      }),
    ),
  });
  render(
    <App
      cliente={api.cliente}
      hook={memoryLocation({ path: "/importacion" }).hook}
    />,
  );
  const usuario = userEvent.setup();
  await usuario.click(
    await screen.findByRole("button", { name: "Deshacer importación" }),
  );
  expect(api.peticiones.some((p) => p.method === "POST")).toBe(false);
  expect(screen.getByRole("dialog")).toBeVisible();
  await usuario.click(screen.getByRole("button", { name: "Cancelar" }));
  expect(screen.queryByRole("dialog")).toBeNull();
});
it("sin permisos no ofrece deshacer ni enlace a historial todavía inhabilitado", async () => {
  const api = simularApi({
    "GET /api/sesion": ok(SESION_INVENTADA),
    "GET /api/importaciones/ultima": ok({
      importacion: detalleInventado({
        se_puede_deshacer: false,
        motivo_no_deshacer: "Se registró un ajuste después.",
      }),
    }),
  });
  render(
    <App
      cliente={api.cliente}
      hook={memoryLocation({ path: "/importacion" }).hook}
    />,
  );
  await screen.findByText("Se registró un ajuste después.");
  expect(
    screen.queryByRole("button", { name: "Deshacer importación" }),
  ).toBeNull();
  expect(screen.queryByRole("link", { name: "Extender historial" })).toBeNull();
});

it("sin_cambios lo decide el servidor y no ofrece importar ni revisar el saldo", async () => {
  const api = simularApi({
    "GET /api/sesion": ok(SESION_INVENTADA),
    "POST /api/importaciones/analizar": ok(
      vistaInventada({ sin_cambios: true }),
    ),
  });
  render(
    <App
      cliente={api.cliente}
      hook={memoryLocation({ path: "/importar" }).hook}
    />,
  );
  await elegir(userEvent.setup());
  expect(
    await screen.findByText("Importar este archivo no cambiaría nada."),
  ).toBeVisible();
  expect(screen.queryByRole("button", { name: "Sí, importar" })).toBeNull();
  expect(screen.queryByRole("button", { name: "No, revisar" })).toBeNull();
  await userEvent
    .setup()
    .click(screen.getByRole("button", { name: "Elegir otro archivo" }));
  expect(
    await screen.findByLabelText("Archivo Excel del banco"),
  ).toBeInTheDocument();
});

it("mientras descarta bloquea confirmar y no repite el envío", async () => {
  let terminar!: () => void;
  const descarte = new Promise<void>((resolve) => {
    terminar = resolve;
  });
  const api = simularApi({
    "GET /api/sesion": ok(SESION_INVENTADA),
    "POST /api/importaciones/analizar": ok(vistaInventada()),
    "DELETE /api/importaciones/analisis": async () => {
      await descarte;
      return ok({ descartado: true });
    },
  });
  render(
    <App
      cliente={api.cliente}
      hook={memoryLocation({ path: "/importar" }).hook}
    />,
  );
  const usuario = userEvent.setup();
  await elegir(usuario);
  await usuario.click(
    await screen.findByRole("button", { name: "No, revisar" }),
  );
  expect(screen.getByRole("button", { name: "Descartando…" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Sí, importar" })).toBeDisabled();
  await usuario.click(screen.getByRole("button", { name: "Descartando…" }));
  expect(api.peticiones.filter((p) => p.method === "DELETE")).toHaveLength(1);
  terminar();
  expect(
    await screen.findByRole("heading", { name: "Revisemos antes de importar" }),
  ).toBeVisible();
});
