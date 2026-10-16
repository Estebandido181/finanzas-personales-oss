import type { Esquemas } from "@/compartido/http/cliente";
export const CONTEOS_INVENTADOS: Esquemas["ConteosImportacion"] = {
  filas: 48,
  ya_estaban: 30,
  ya_preguntadas: 0,
  confirmados: 30,
  corregidos: 2,
  agregados: 14,
  preguntas_es_el_mismo: 3,
  preguntas_ajuste: 0,
  no_en_banco: 2,
  anteriores: 2,
  sin_formato: 0,
  ajuste_reducido: false,
};
export function vistaInventada(
  cambios: Partial<Esquemas["VistaPreviaImportacion"]> = {},
): Esquemas["VistaPreviaImportacion"] {
  return {
    causas_probables: [
      {
        codigo: "saldo",
        titulo: "Revisa tu saldo",
        texto: "Compara con el saldo del banco.",
        accion: "ajustar_saldo",
      },
    ],
    diferencia_centavos: -6300000,
    entran_categorizados: 11,
    fecha_inicio: "2026-09-01",
    puede_extender_historial: false,
    token: "analisis-inventado",
    segundos: 900,
    resumen: CONTEOS_INVENTADOS,
    reporte: {
      desde: "2026-09-02",
      hasta: "2026-10-01",
      dia_incompleto: false,
    },
    saldo_antes_centavos: 480215000,
    saldo_despues_centavos: 473915000,
    sin_categoria: 3,
    preguntas_pendientes: 3,
    sin_cambios: false,
    ...cambios,
  };
}
export function detalleInventado(
  cambios: Partial<Esquemas["DetalleImportacion"]> = {},
): Esquemas["DetalleImportacion"] {
  return {
    todo_resuelto: false,
    puede_extender_historial: false,
    id: 1,
    hecha_en: "2026-10-02T16:00:00",
    deshecha_en: null,
    resumen: CONTEOS_INVENTADOS,
    reporte: {
      desde: "2026-09-02",
      hasta: "2026-10-01",
      dia_incompleto: false,
    },
    saldo_centavos: 473915000,
    se_puede_deshacer: true,
    motivo_no_deshacer: null,
    sin_categoria: 3,
    grupos: [],
    preguntas_pendientes: 3,
    no_en_banco_pendientes: 2,
    siguiente: "categorizar",
    ...cambios,
  };
}
