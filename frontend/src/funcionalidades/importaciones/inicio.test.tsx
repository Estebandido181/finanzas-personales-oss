import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { memoryLocation } from "wouter/memory-location";
import { App } from "@/app/app";
import type { Esquemas } from "@/compartido/http/cliente";
import { simularApi, SESION_INVENTADA } from "@/pruebas/api-simulada";
import {
  reporteInventado,
  movimientosInventados,
  sincronizacionCorrecta,
} from "@/pruebas/inicio-inventado";
import { detalleInventado, CONTEOS_INVENTADOS } from "@/pruebas/importacion-inventada";
const ok = (cuerpo: unknown) => ({ estado: 200, cuerpo });
function abrir(mostrar: boolean, resumen = CONTEOS_INVENTADOS) {
  const estado: Esquemas["EstadoImportaciones"] = {
    ultima_id: 1,
    mostrar_recordatorio: mostrar,
    movimientos_desde_ultima: mostrar ? 0 : 120,
    semanas_desde_ultima: mostrar ? 0 : 5,
    preguntas_pendientes: 0,
    no_en_banco_pendientes: 0,
    sin_categoria: 0,
    importacion_pendiente: false,
  };
  const api = simularApi({
    "GET /api/sesion": ok(SESION_INVENTADA),
    "GET /api/reporte": ok(reporteInventado()),
    "GET /api/movimientos": ok({
      mes: "2026-09",
      movimientos: movimientosInventados(),
    }),
    "GET /api/sincronizacion": ok(sincronizacionCorrecta()),
    "GET /api/importaciones/ultima": ok({
      importacion: detalleInventado({ todo_resuelto: true, resumen }),
    }),
    "GET /api/importaciones/estado": ok(estado),
  });
  render(
    <App cliente={api.cliente} hook={memoryLocation({ path: "/" }).hook} />,
  );
}
it("muestra el recordatorio por orden del servidor, aun con conteos bajos, y deja consultar los pasos", async () => {
  abrir(true);
  expect(
    await screen.findByText("Conviene importar los movimientos del banco"),
  ).toBeVisible();
  await userEvent.setup().click(screen.getByText("Cómo descargar el reporte"));
  expect(
    screen.getByRole("heading", { name: "Cómo conseguir el archivo" }),
  ).toBeVisible();
});

it("Inicio informa la confirmación sin movimientos nuevos", async () => {
  abrir(false, { ...CONTEOS_INVENTADOS, agregados: 0, ya_estaban: 0, confirmados: 1, corregidos: 0 });
  expect(await screen.findByText("0 agregados, 0 ya estaban, 1 confirmados, 0 corregidos.")).toBeVisible();
});
it("oculta el recordatorio si el servidor lo indica, aun con 120 movimientos y cinco semanas", async () => {
  abrir(false);
  await screen.findByRole("heading", { name: "Última importación del banco" });
  await waitFor(() =>
    expect(
      screen.queryByText("Conviene importar los movimientos del banco"),
    ).toBeNull(),
  );
});
