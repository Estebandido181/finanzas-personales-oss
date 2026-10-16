import { renderHook } from "@testing-library/react";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { reiniciarSincronizacionAlAbrir, useSincronizarAlAbrir } from "@/funcionalidades/sincronizacion/sincronizar";

beforeEach(() => reiniciarSincronizacionAlAbrir());

describe("useSincronizarAlAbrir", () => {
  it("no sincroniza si el servidor no lo pide", () => {
    const sincronizar = vi.fn(async () => {});
    renderHook(() => useSincronizarAlAbrir(false, sincronizar));
    expect(sincronizar).not.toHaveBeenCalled();
  });

  it("sincroniza una sola vez cuando el servidor lo pide", () => {
    const sincronizar = vi.fn(async () => {});
    const { rerender } = renderHook(() => useSincronizarAlAbrir(true, sincronizar));
    rerender();
    rerender();
    expect(sincronizar).toHaveBeenCalledTimes(1);
  });

  it("espera a que el servidor lo diga (mientras carga, false) y luego sincroniza una vez", () => {
    const sincronizar = vi.fn(async () => {});
    const { rerender } = renderHook(({ debe }) => useSincronizarAlAbrir(debe, sincronizar), {
      initialProps: { debe: false },
    });
    expect(sincronizar).not.toHaveBeenCalled();
    rerender({ debe: true });
    expect(sincronizar).toHaveBeenCalledTimes(1);
  });

  it("StrictMode monta dos veces los efectos y aun así sincroniza una sola vez", () => {
    const sincronizar = vi.fn(async () => {});
    renderHook(() => useSincronizarAlAbrir(true, sincronizar), { wrapper: StrictMode });
    expect(sincronizar).toHaveBeenCalledTimes(1);
  });

  it("volver a Inicio (se desmonta y se monta) no repite la sincronización", () => {
    const sincronizar = vi.fn(async () => {});
    renderHook(() => useSincronizarAlAbrir(true, sincronizar)).unmount();
    renderHook(() => useSincronizarAlAbrir(true, sincronizar));
    expect(sincronizar).toHaveBeenCalledTimes(1);
  });

  it("si la sincronización falla, no se reintenta sola aunque el servidor siga diciendo que toca", async () => {
    const sincronizar = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const { rerender } = renderHook(
      ({ debe }) => useSincronizarAlAbrir(debe, () => sincronizar().catch(() => {})),
      { initialProps: { debe: true } },
    );
    await Promise.resolve();
    // Recargas con el mismo "sí" (o un "no" y otra vez "sí", p. ej. al cambiar de mes).
    rerender({ debe: false });
    rerender({ debe: true });
    rerender({ debe: true });
    expect(sincronizar).toHaveBeenCalledTimes(1);
  });
});
