import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { memoryLocation } from "wouter/memory-location";
import { App } from "@/app/app";
import type { Esquemas } from "@/compartido/http/cliente";
import {
  simularApi,
  SESION_INVENTADA,
  TOKEN_INVENTADO,
} from "@/pruebas/api-simulada";
import { detalleInventado } from "@/pruebas/importacion-inventada";
const ok = (cuerpo: unknown) => ({ estado: 200, cuerpo });
const movimiento: Esquemas["DatoConciliacion"] = {
  descartado: false,
  nota_descartado: null,
  origen: "extracto",
  id: null,
  descripcion: "COMPRA EJEMPLO",
  destino_ultimos4: "*1234",
  fecha_hora: "2026-09-04T12:30:00",
  monto_centavos: 150000,
  tipo: "compra",
};
const pregunta: Esquemas["PreguntaConciliacion"] = {
  id: 7,
  tipo: "monto_parecido",
  fuente: "banco",
  movimiento,
  candidatos: [],
  ajuste: null,
  diferencia_centavos: null,
  opciones: [
    {
      id: "clave-servidor",
      texto: "Sí, es el mismo",
      consecuencia: "Se conserva el monto del banco.",
    },
  ],
  sugerencia: {
    opcion: "clave-servidor",
    motivo: "Coincide la fecha.",
    analisis: "El servidor analizó las fechas.",
  },
};
const lista: Esquemas["ListaPreguntasConciliacion"] = {
  preguntas: [pregunta],
  total: 1,
  con_sugerencia: 1,
};
function abrir(ruta: string, rutas: Parameters<typeof simularApi>[0]) {
  const api = simularApi({ "GET /api/sesion": ok(SESION_INVENTADA), ...rutas });
  render(
    <App cliente={api.cliente} hook={memoryLocation({ path: ruta }).hook} />,
  );
  return api;
}
it("el candidato descartado muestra la nota del servidor y responder no envía restaurar", async () => {
  const api = abrir("/conciliacion/preguntas", {
    "GET /api/conciliacion/preguntas": ok({ ...lista, preguntas: [{ ...pregunta,
      candidatos: [{ ...movimiento, id: 51, descripcion: "DESCARTADO INVENTADO", descartado: true,
        nota_descartado: "Seguirá fuera del saldo hasta que elijas Restaurar." }] }] }),
    "POST /api/conciliacion/preguntas/7/respuesta": { estado: 409, cuerpo: { detalle: "Revisa esta respuesta inventada." } },
  });
  expect(await screen.findByText("Descartado", { exact: true })).toBeVisible();
  expect(screen.getByText("Seguirá fuera del saldo hasta que elijas Restaurar.")).toBeVisible();
  await userEvent.setup().click(screen.getByRole("button", { name: "Sí, es el mismo" }));
  await screen.findByRole("alert");
  const envios = api.peticiones.filter((p) => p.method === "POST");
  expect(envios).toHaveLength(1);
  expect(new URL(envios[0]!.url).pathname).toBe("/api/conciliacion/preguntas/7/respuesta");
});
it("la respuesta envía la clave opaca del servidor y conserva la pregunta cuando falla", async () => {
  const api = abrir("/conciliacion/preguntas", {
    "GET /api/conciliacion/preguntas": ok(lista),
    "POST /api/conciliacion/preguntas/7/respuesta": {
      estado: 409,
      cuerpo: { detalle: "Otra sesión cambió esta pregunta." },
    },
  });
  await userEvent
    .setup()
    .click(await screen.findByRole("button", { name: "Sí, es el mismo" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Otra sesión");
  expect(screen.getByText("Se conserva el monto del banco.")).toBeVisible();
  const enviada = api.peticiones.find((p) => p.method === "POST")!;
  expect(await enviada.json()).toEqual({ opcion: "clave-servidor" });
  expect(enviada.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
});
it("aceptar sugerencias aplica el lote del servidor y ofrece su resumen reversible", async () => {
  let resuelto = false;
  const resultado: Esquemas["ResultadoDecisionConciliacion"] = {
    aplicadas: [7],
    resumen: "El servidor aplicó una sugerencia.",
    efecto_saldo_centavos: 0,
    saldo_centavos: 123456,
    deshacer: { token: "deshacer-inventado", segundos: 30 },
  };
  const api = abrir("/conciliacion/preguntas", {
    "GET /api/conciliacion/preguntas": () =>
      ok(
        resuelto
          ? ({
              preguntas: [],
              total: 0,
              con_sugerencia: 0,
            } satisfies Esquemas["ListaPreguntasConciliacion"])
          : lista,
      ),
    "POST /api/conciliacion/preguntas/aceptar-sugerencias": () => {
      resuelto = true;
      return ok(resultado);
    },
  });
  await userEvent
    .setup()
    .click(
      await screen.findByRole("button", { name: "Aceptar la sugerencia" }),
    );
  expect(
    await screen.findByRole("heading", { name: "No hay preguntas pendientes" }),
  ).toBeVisible();
  expect(screen.getByText(resultado.resumen)).toBeVisible();
  expect(screen.getByRole("button", { name: "Deshacer" })).toBeEnabled();
  expect(
    api.peticiones
      .find((p) => p.method === "POST")!
      .headers.get("Content-Type"),
  ).toBe("application/json");
});
it("una respuesta fallida sigue visible si el servidor ya retiró la pregunta", async () => {
  let consultadas = 0;
  abrir("/conciliacion/preguntas", {
    "GET /api/conciliacion/preguntas": () =>
      ok(
        ++consultadas === 1
          ? lista
          : ({
              preguntas: [],
              total: 0,
              con_sugerencia: 0,
            } satisfies Esquemas["ListaPreguntasConciliacion"]),
      ),
    "POST /api/conciliacion/preguntas/7/respuesta": {
      estado: 409,
      cuerpo: { detalle: "La pregunta ya fue resuelta." },
    },
  });
  await userEvent
    .setup()
    .click(await screen.findByRole("button", { name: "Sí, es el mismo" }));
  await screen.findByRole("heading", { name: "No hay preguntas pendientes" });
  expect(screen.getByRole("alert")).toHaveTextContent(
    "La pregunta ya fue resuelta",
  );
});
it("no-en-banco usa el id explícito del servidor y la decisión dejar", async () => {
  const api = abrir("/conciliacion/no-esta-en-el-banco", {
    "GET /api/conciliacion/no-esta-en-el-banco": ok({
      movimientos: [
        {
          id: 23,
          movimiento,
          sugerencia: {
            opcion: null,
            motivo: "",
            analisis: "No aparece en el reporte.",
          },
        },
      ],
      reporte: null,
    } satisfies Esquemas["ListaNoEnBanco"]),
    "POST /api/conciliacion/no-esta-en-el-banco/23/respuesta": {
      estado: 409,
      cuerpo: { detalle: "El reporte cambió." },
    },
  });
  await userEvent
    .setup()
    .click(
      await screen.findByRole("button", {
        name: "Dejarlo: sigue contando en tu saldo",
      }),
    );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "El reporte cambió",
  );
  expect(await api.peticiones.find((p) => p.method === "POST")!.json()).toEqual(
    { opcion: "dejar" },
  );
});
it("la nota del día incompleto nombra el primer día del reporte que manda el servidor", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-09-15T12:00:00-05:00"));
  try {
    abrir("/conciliacion/no-esta-en-el-banco", {
      "GET /api/conciliacion/no-esta-en-el-banco": ok({
        movimientos: [],
        reporte: { desde: "2026-08-10", hasta: "2026-09-08", dia_incompleto: true },
      } satisfies Esquemas["ListaNoEnBanco"]),
    });
    expect(
      await screen.findByText(
        "El 10 de agosto, primer día del reporte, puede venir incompleto. Por precaución, ese día no se marca como «No está en el banco».",
      ),
    ).toBeVisible();
  } finally {
    vi.useRealTimers();
  }
});
it("sin día incompleto del servidor no aparece la nota", async () => {
  abrir("/conciliacion/no-esta-en-el-banco", {
    "GET /api/conciliacion/no-esta-en-el-banco": ok({
      movimientos: [],
      reporte: { desde: "2026-08-10", hasta: "2026-09-08", dia_incompleto: false },
    } satisfies Esquemas["ListaNoEnBanco"]),
  });
  await screen.findByRole("heading", { name: "No hay movimientos por revisar" });
  expect(screen.queryByText(/primer día del reporte/)).toBeNull();
});
it("una carga sin red ofrece reintentar y permite llegar al estado vacío", async () => {
  let intento = 0;
  abrir("/conciliacion/no-esta-en-el-banco", {
    "GET /api/conciliacion/no-esta-en-el-banco": () =>
      ++intento === 1
        ? "sin-red"
        : ok({
            movimientos: [],
            reporte: null,
          } satisfies Esquemas["ListaNoEnBanco"]),
  });
  await userEvent
    .setup()
    .click(await screen.findByRole("button", { name: "Volver a intentar" }));
  expect(
    await screen.findByRole("heading", {
      name: "No hay movimientos por revisar",
    }),
  ).toBeVisible();
});
it("todo resuelto depende del campo servidor y no de sumar los conteos", async () => {
  abrir("/importacion", {
    "GET /api/importaciones/ultima": ok({
      importacion: detalleInventado({
        todo_resuelto: true,
        sin_categoria: 3,
        preguntas_pendientes: 2,
      }),
    }),
  });
  expect(
    await screen.findByRole("heading", { name: "Preguntas resueltas" }),
  ).toBeVisible();
  expect(screen.queryByRole("heading", { name: "Por resolver" })).toBeNull();
});
it("la pantalla no muestra todo resuelto porque los conteos sean cero", async () => {
  abrir("/importacion", {
    "GET /api/importaciones/ultima": ok({
      importacion: detalleInventado({
        todo_resuelto: false,
        sin_categoria: 0,
        preguntas_pendientes: 0,
        no_en_banco_pendientes: 0,
      }),
    }),
  });
  await screen.findByRole("heading", { name: "Por resolver" });
  expect(screen.queryByRole("heading", { name: "Preguntas resueltas" })).toBeNull();
});
it("la lista de preguntas sin sugerencias no ofrece aceptación en lote", async () => {
  abrir("/conciliacion/preguntas", {
    "GET /api/conciliacion/preguntas": ok({
      ...lista,
      con_sugerencia: 0,
      preguntas: [
        {
          ...pregunta,
          sugerencia: {
            opcion: null,
            motivo: "Sin pista.",
            analisis: "El servidor requiere tu decisión.",
          },
        },
      ],
    } satisfies Esquemas["ListaPreguntasConciliacion"]),
  });
  await screen.findByText("No hay una pista clara: elige tú.");
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: /Aceptar/ })).toBeNull(),
  );
});


it("las diferencias distinguen un ingreso y un ajuste negativo por signo y tinta", async () => {
  const ingreso = { ...movimiento, tipo: "ingreso", monto_centavos: 120000, descripcion: "INGRESO INVENTADO" } satisfies Esquemas["DatoConciliacion"];
  const ajuste = { ...movimiento, origen: "manual", tipo: "ajuste", monto_centavos: -80000, descripcion: "AJUSTE INVENTADO" } satisfies Esquemas["DatoConciliacion"];
  abrir("/conciliacion/preguntas", {
    "GET /api/conciliacion/preguntas": ok({
      ...lista,
      preguntas: [{ ...pregunta, tipo: "mismo_dia_ajuste", movimiento: ingreso, ajuste }],
    } satisfies Esquemas["ListaPreguntasConciliacion"]),
  });
  await screen.findByRole("heading", { name: /Ya estaba en el saldo/ });
  expect(screen.getByText(/\+.*1\.200/)).toHaveClass("text-monto-positivo");
  expect(screen.getByText(/−.*800/)).toHaveClass("text-monto-negativo");
});


it("los candidatos indistinguibles muestran las mismas etiquetas que sus opciones", async () => {
  const candidatos = [1, 2].map((numero) => ({
    ...movimiento,
    id: numero + 100,
    etiqueta: `Candidato ${numero}`,
  }));
  abrir("/conciliacion/preguntas", {
    "GET /api/conciliacion/preguntas": ok({
      ...lista,
      preguntas: [{
        ...pregunta,
        tipo: "varios_candidatos",
        candidatos,
        opciones: [
          { id: "opaca-1", texto: "Es Candidato 1", consecuencia: "Se conserva el primero." },
          { id: "opaca-2", texto: "Es Candidato 2", consecuencia: "Se conserva el segundo." },
        ],
      }],
    } satisfies Esquemas["ListaPreguntasConciliacion"]),
  });
  expect(await screen.findByText("Candidato 1 ·")).toBeVisible();
  expect(screen.getByRole("button", { name: "Es Candidato 1" })).toBeVisible();
  expect(screen.getByText("Candidato 2 ·")).toBeVisible();
  expect(screen.queryByText(/movimiento 10[12]/)).toBeNull();
});

it("cada candidato muestra su origen explícito aunque la pregunta provenga del banco", async () => {
  abrir("/conciliacion/preguntas", {
    "GET /api/conciliacion/preguntas": ok({
      ...lista,
      preguntas: [{
        ...pregunta,
        candidatos: [
          { ...movimiento, id: 101, origen: "manual", descripcion: "INGRESO A MANO INVENTADO" },
          { ...movimiento, id: 102, origen: "gmail", descripcion: "AVISO INVENTADO" },
        ],
      }],
    } satisfies Esquemas["ListaPreguntasConciliacion"]),
  });
  await screen.findByRole("heading", { name: /1 de 1/ });
  expect(screen.getByText(/^Del banco ·/)).toBeVisible();
  expect(screen.getByText(/^A mano ·/)).toBeVisible();
  expect(screen.getByText(/^Del correo ·/)).toBeVisible();
});
