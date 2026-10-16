import type { Esquemas } from "@/compartido/http/cliente";

export function comprobacionInventada(cambios: Partial<Esquemas["ComprobacionSaldo"]> = {}): Esquemas["ComprobacionSaldo"] {
  return {
    estado: "disponible", origen: "actual", saldo_real_centavos: 123456,
    saldo_app_centavos: 123450, diferencia_centavos: 6, coincide: false,
    recibido_en: "2026-10-06T14:32:00", huella: "huella-inventada",
    verificacion_independiente: true, diferencia_forzada_por_inicial: false,
    saldo_antes_centavos: 123450, saldo_despues_centavos: 123450,
    efecto_conciliacion_centavos: 0, resto_no_explicado_centavos: 6,
    desglose_antes: null, desglose_despues: null, contribuciones: null,
    pendientes: { preguntas: 2, no_en_banco: 1, sin_categoria: 3 },
    cobertura: { desde: null, hasta: null, archivos_de_120_filas: null,
      proteccion_ausencias_conservadora: false, cobertura_verificada: false,
      cobertura_hasta_consulta_verificada: false, huecos: [],
      advertencia: "No se puede asegurar que estén todos los movimientos." },
    ...cambios,
  };
}
