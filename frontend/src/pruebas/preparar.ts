import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { reiniciarSincronizacionAlAbrir } from "@/funcionalidades/sincronizacion/sincronizar";

afterEach(() => {
  cleanup();
  reiniciarSincronizacionAlAbrir();
  localStorage.clear();
  document.documentElement.removeAttribute("data-tema");
});
