import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ElegirExcel } from "@/funcionalidades/importaciones/elegir-excel";
it("seleccionar nunca analiza ni confirma automáticamente; permite volver a elegir el mismo", async () => {
  const usuario = userEvent.setup();
  const elegir = vi.fn();
  const analizar = vi.fn();
  render(
    <ElegirExcel
      archivo={null}
      ocupado={false}
      error={null}
      alElegir={elegir}
      alAnalizar={analizar}
      alQuitar={vi.fn()}
    />,
  );
  const entrada = screen.getByLabelText("Archivo Excel del banco");
  const archivo = new File(["inventado"], "reporte-EJEMPLO.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  await usuario.upload(entrada, archivo);
  await usuario.upload(entrada, archivo);
  expect(elegir).toHaveBeenCalledTimes(2);
  expect(analizar).not.toHaveBeenCalled();
});
it("al analizar bloquea acciones repetidas y conserva el nombre elegido", () => {
  render(
    <ElegirExcel
      archivo={new File(["x"], "reporte-EJEMPLO.xlsx")}
      ocupado
      error={null}
      alElegir={vi.fn()}
      alAnalizar={vi.fn()}
      alQuitar={vi.fn()}
    />,
  );
  expect(screen.getByText("reporte-EJEMPLO.xlsx")).toBeVisible();
  expect(screen.getByRole("button", { name: "Analizando…" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Quitar archivo" })).toBeDisabled();
});
it("mantiene el archivo para reintentar un fallo sin guardar", () => {
  render(
    <ElegirExcel
      archivo={new File(["x"], "reporte-EJEMPLO.xlsx")}
      ocupado={false}
      error="No hay conexión con la app."
      alElegir={vi.fn()}
      alAnalizar={vi.fn()}
      alQuitar={vi.fn()}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("No hay conexión");
  expect(
    screen.getByRole("button", { name: "Analizar archivo" }),
  ).toBeEnabled();
});
