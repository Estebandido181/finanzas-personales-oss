import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "@/app/app";
import { registrarServiceWorker } from "@/pwa/registrar";
import "@/app/estilos.css";

const raiz = document.getElementById("raiz");
if (!raiz) throw new Error("Falta el elemento #raiz en index.html");

createRoot(raiz).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// Instalable en el celular (ítem 18). Después de cargar, para no competir con
// la primera pantalla. Solo guarda el cascarón estático, nunca datos.
window.addEventListener("load", () => void registrarServiceWorker());
