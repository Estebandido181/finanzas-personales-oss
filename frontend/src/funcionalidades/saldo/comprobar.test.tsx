import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { useLayoutEffect, useRef } from "react";
import { ProveedorSesion, useSesion } from "@/funcionalidades/sesion/sesion";
import { simularApi, SESION_INVENTADA, TOKEN_INVENTADO } from "@/pruebas/api-simulada";
import { comprobacionInventada } from "@/pruebas/comprobacion-inventada";
import { ComprobarSaldo } from "@/funcionalidades/saldo/comprobar";

const ok = (cuerpo: unknown) => ({ estado: 200, cuerpo });

it("conserva el envío válido iniciado al montar antes del primer efecto pasivo", async () => {
  let signal: AbortSignal | undefined;
  const api = simularApi({
    "GET /api/sesion": ok(SESION_INVENTADA),
    "POST /api/saldo/comprobar": (peticion) => {
      signal = peticion.signal;
      return new Promise<ReturnType<typeof ok>>(() => {});
    },
  });
  function EnviarAlMontar() {
    const contenedor = useRef<HTMLDivElement>(null);
    useLayoutEffect(() => {
      contenedor.current!.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    }, []);
    return <div ref={contenedor}><ComprobarSaldo contexto="estable" valorInicial="0" /></div>;
  }
  function ConSesion() {
    const { estado } = useSesion();
    return estado.tipo === "dentro" ? <EnviarAlMontar /> : null;
  }
  const vista = render(<ProveedorSesion cliente={api.cliente}><ConSesion /></ProveedorSesion>);
  await waitFor(() => expect(signal).toBeDefined());
  expect(signal!.aborted).toBe(false);
  expect(screen.getByRole("button", { name: "Comprobando…" })).toBeDisabled();
  expect(api.peticiones.filter((p) => p.method === "POST")).toHaveLength(1);
  vista.unmount();
  expect(signal!.aborted).toBe(true);
});

for (const [nombre, cambio] of [
  ["contexto", { contexto: "nuevo-contexto" }],
  ["token", { token: "nuevo-token-inventado" }],
  ["bloqueo", { deshabilitado: true }],
] as const) it(`conserva la petición al cambiar solo el callback y la cancela al cambiar ${nombre}`, async () => {
  let signal: AbortSignal | undefined;
  let resolver!: (respuesta: ReturnType<typeof ok>) => void;
  const props = { contexto: "preview", token: "token-inventado", tipo: "importacion" as const, alInvalidar: vi.fn() };
  const api = montar({
    "POST /api/saldo/comprobar": (peticion) => {
      signal = peticion.signal;
      return new Promise<ReturnType<typeof ok>>((resolve) => { resolver = resolve; });
    },
  }, props);
  await comprobar("0");
  api.cambiar({ ...props, alInvalidar: vi.fn() });
  expect(signal!.aborted).toBe(false);
  expect(screen.getByRole("button", { name: "Comprobando…" })).toBeDisabled();
  api.cambiar({ ...props, ...cambio });
  expect(signal!.aborted).toBe(true);
  resolver(ok(comprobacionInventada()));
  await waitFor(() => expect(screen.getByRole("button", { name: "Comprobar saldo" })).toBeInTheDocument());
  expect(screen.queryByText("+$0,06")).toBeNull();
  expect(api.peticiones.filter((p) => p.method === "POST")).toHaveLength(1);
});

it("conserva el nuevo envío iniciado al habilitar antes de los efectos pasivos", async () => {
  let signal: AbortSignal | undefined;
  const api = simularApi({
    "GET /api/sesion": ok(SESION_INVENTADA),
    "POST /api/saldo/comprobar": (peticion) => {
      signal = peticion.signal;
      return new Promise<ReturnType<typeof ok>>(() => {});
    },
  });
  function EnviarAlHabilitar({ deshabilitado }: { deshabilitado: boolean }) {
    const contenedor = useRef<HTMLDivElement>(null);
    useLayoutEffect(() => {
      if (!deshabilitado) contenedor.current!.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    }, [deshabilitado]);
    return <div ref={contenedor}><ComprobarSaldo contexto="preview" valorInicial="0" tipo="importacion"
      token={deshabilitado ? "anterior-inventado" : "nuevo-inventado"} deshabilitado={deshabilitado} /></div>;
  }
  function ConSesion({ deshabilitado }: { deshabilitado: boolean }) {
    const { estado } = useSesion();
    return estado.tipo === "dentro" ? <EnviarAlHabilitar deshabilitado={deshabilitado} /> : null;
  }
  const contenido = (deshabilitado: boolean) => <ProveedorSesion cliente={api.cliente}><ConSesion deshabilitado={deshabilitado} /></ProveedorSesion>;
  const vista = render(contenido(true));
  expect(await screen.findByRole("button", { name: "Comprobar saldo" })).toBeDisabled();
  expect(signal).toBeUndefined();
  vista.rerender(contenido(false));
  await waitFor(() => expect(signal).toBeDefined());
  expect(signal!.aborted).toBe(false);
  expect(screen.getByRole("button", { name: "Comprobando…" })).toBeDisabled();
  expect(api.peticiones.filter((p) => p.method === "POST")).toHaveLength(1);
  vista.unmount();
  expect(signal!.aborted).toBe(true);
});

function montar(rutas: Parameters<typeof simularApi>[0] = {}, props: Parameters<typeof ComprobarSaldo>[0] = { contexto: "actual" }) {
  const api = simularApi({ "GET /api/sesion": ok(SESION_INVENTADA), "POST /api/saldo/comprobar": ok(comprobacionInventada()), ...rutas });
  const contenido = (p: typeof props) => <ProveedorSesion cliente={api.cliente}><ComprobarSaldo {...p} /></ProveedorSesion>;
  const vista = render(contenido(props));
  return { ...api, cambiar: (p: typeof props) => vista.rerender(contenido(p)) };
}
async function comprobar(valor = "1.234,56") {
  const usuario = userEvent.setup();
  await usuario.type(screen.getByLabelText("Escribe el saldo que ves ahora en Bancolombia"), valor);
  await usuario.click(screen.getByRole("button", { name: "Comprobar saldo" }));
  return usuario;
}
it("envía centavos y CSRF sin fecha ni ajuste; presenta diferencia exacta y hora de recepción", async () => {
  const api = montar(); await comprobar();
  expect(await screen.findByText("+$0,06")).toBeVisible();
  expect(screen.getByText(/Es la hora de recepción/)).toBeVisible();
  expect(screen.getByText(/2 preguntas pendientes; 1 movimientos/)).toBeVisible();
  const peticion = api.peticiones.find((p) => p.method === "POST")!;
  expect(await peticion.json()).toEqual({ saldo_real_centavos: 123456 });
  expect(peticion.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
  expect(api.peticiones.filter((p) => p.method === "POST")).toHaveLength(1);
  expect(screen.queryByLabelText(/fecha/i)).toBeNull();
});
it("usa el token del preview; muestra impacto y resto firmados del servidor sin recalcular", async () => {
  const api = montar({ "POST /api/saldo/comprobar": ok(comprobacionInventada({ origen: "importacion", diferencia_centavos: -1, efecto_conciliacion_centavos: -234, resto_no_explicado_centavos: -1 })) }, { contexto: "preview", token: "analisis-inventado", tipo: "importacion" });
  await comprobar();
  expect(await screen.findAllByText("−$0,01")).toHaveLength(2);
  expect(screen.getByText("−$2,34")).toBeVisible();
  expect(await api.peticiones.find((p) => p.method === "POST")!.json()).toEqual({ saldo_real_centavos: 123456, token_analisis: "analisis-inventado", tipo_analisis: "importacion" });
});
it("coincidir no promete cobertura y editar el monto descarta el diagnóstico", async () => {
  montar({ "POST /api/saldo/comprobar": ok(comprobacionInventada({ coincide: true, diferencia_centavos: 0 })) });
  const usuario = await comprobar("0");
  expect(await screen.findByText(/Los saldos coinciden/)).toHaveTextContent(/no garantiza/);
  await usuario.type(screen.getByLabelText("Escribe el saldo que ves ahora en Bancolombia"), ",01");
  expect(screen.queryByText(/Los saldos coinciden/)).toBeNull();
});
it("el estado sin configuración y la coincidencia inicial salen del servidor", async () => {
  const api = montar({ "POST /api/saldo/comprobar": ok(comprobacionInventada({ estado: "sin_configuracion", saldo_app_centavos: null, diferencia_centavos: null, coincide: null })) });
  await comprobar(); expect(await screen.findByText(/Configura primero tu saldo/)).toBeVisible();
  api.rutas["POST /api/saldo/comprobar"] = ok(comprobacionInventada({ origen: "arranque", coincide: true, diferencia_centavos: 0, verificacion_independiente: false, diferencia_forzada_por_inicial: true }));
  await userEvent.click(screen.getByRole("button", { name: "Comprobar saldo" }));
  expect(await screen.findByText(/Esta coincidencia no es una comprobación independiente/)).toBeVisible();
  expect(screen.queryByText(/Los saldos coinciden/)).toBeNull();
});
for (const estado of [409, 410]) it(`${estado} descarta el resultado y bloquea volver a usar el token`, async () => {
  const alInvalidar = vi.fn();
  const api = montar({}, { contexto: "preview", token: "analisis-inventado", tipo: "arranque", alInvalidar });
  await comprobar(); await screen.findByText("+$0,06");
  api.rutas["POST /api/saldo/comprobar"] = { estado, cuerpo: { detalle: "Revisión obsoleta." } };
  await userEvent.click(screen.getByRole("button", { name: "Comprobar saldo" }));
  expect(await screen.findByText(/Vuelve a analizar los archivos/)).toBeVisible();
  expect(screen.queryByText("+$0,06")).toBeNull();
  expect(screen.getByRole("button", { name: "Comprobar saldo" })).toBeDisabled();
  expect(alInvalidar).toHaveBeenCalledWith(estado);
});
it("una respuesta retrasada no restaura el diagnóstico después de cambiar el contexto", async () => {
  let resolver!: (respuesta: ReturnType<typeof ok>) => void;
  const api = montar({ "POST /api/saldo/comprobar": () => new Promise((r) => { resolver = r; }) });
  await comprobar(); expect(screen.getByRole("button", { name: "Comprobando…" })).toBeDisabled();
  api.cambiar({ contexto: "despues-de-responder" });
  resolver(ok(comprobacionInventada()));
  await waitFor(() => expect(screen.getByRole("button", { name: "Comprobar saldo" })).toBeEnabled());
  expect(screen.queryByText("+$0,06")).toBeNull();
});
it("un error de red permite reintentar y un monto inválido no se envía", async () => {
  const api = montar({ "POST /api/saldo/comprobar": "sin-red" });
  const usuario = await comprobar("1,234");
  expect(api.peticiones.filter((p) => p.method === "POST")).toHaveLength(0);
  await usuario.clear(screen.getByLabelText("Escribe el saldo que ves ahora en Bancolombia"));
  await usuario.type(screen.getByLabelText("Escribe el saldo que ves ahora en Bancolombia"), "0");
  await usuario.click(screen.getByRole("button", { name: "Comprobar saldo" }));
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: "Comprobar saldo" })).toBeEnabled();
});
