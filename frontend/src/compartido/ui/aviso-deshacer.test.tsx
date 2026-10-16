import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AvisoDeshacer } from "@/compartido/ui/aviso-deshacer";

const OFERTA = { fase: "oferta", texto: "Regla borrada." } as const;

function montar() {
  const alPausar = vi.fn();
  const alReanudar = vi.fn();
  render(<AvisoDeshacer estado={OFERTA} alDeshacer={() => {}} alPausar={alPausar} alReanudar={alReanudar} />);
  return { alPausar, alReanudar, usuario: userEvent.setup() };
}

describe("AvisoDeshacer: pausa de la cuenta", () => {
  it("el cursor encima pausa y al salir reanuda", async () => {
    const { alPausar, alReanudar, usuario } = montar();
    await usuario.hover(screen.getByRole("status"));
    expect(alPausar).toHaveBeenCalled();
    await usuario.unhover(screen.getByRole("status"));
    expect(alReanudar.mock.invocationCallOrder.at(-1)!).toBeGreaterThan(alPausar.mock.invocationCallOrder.at(-1)!);
  });

  it("el foco en el aviso al aparecer no pausa, pero el foco en «Deshacer» sí; al salir, reanuda", async () => {
    const { alPausar, alReanudar, usuario } = montar();
    expect(screen.getByRole("status")).toHaveFocus();
    expect(alPausar).not.toHaveBeenCalled();
    await usuario.tab();
    expect(screen.getByRole("button", { name: "Deshacer" })).toHaveFocus();
    expect(alPausar).toHaveBeenCalled();
    await usuario.tab();
    expect(alReanudar.mock.invocationCallOrder.at(-1)!).toBeGreaterThan(alPausar.mock.invocationCallOrder.at(-1)!);
  });
});
