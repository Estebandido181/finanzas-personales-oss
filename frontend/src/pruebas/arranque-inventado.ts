import type { Esquemas } from "@/compartido/http/cliente";
import { CONTEOS_INVENTADOS, detalleInventado } from "@/pruebas/importacion-inventada";
export const ESTADO_ARRANQUE_INVENTADO: Esquemas["EstadoArranque"] = { mostrar_arranque_inicial: true, puede_iniciar_arranque: true, puede_extender_historial: false };
export function archivosInventados(cantidad = 1): Esquemas["ArchivosHistorial"] {
  return { token: `archivos-inventados-${cantidad}`, segundos: 900, limite_archivos: 12, limite_filas: 1440, puede_calcular: cantidad > 0,
    archivos: Array.from({ length: cantidad }, (_, i) => ({ id: i + 1, estado: "leido", filas: 4, desde: "2026-08-10", hasta: "2026-08-13", truncado: false })) };
}
export function previaArranqueInventada(cambios: Partial<Esquemas["VistaPreviaArranque"]> = {}): Esquemas["VistaPreviaArranque"] {
  return { token: "calculo-inventado", segundos: 900, modo: "arranque", archivos: 2, archivos_truncados: 0, filas: 8, filas_solapadas: 4,
    desde: "2026-08-10", hasta: "2026-08-13", fecha_inicio_propuesta: "2026-08-10", fecha_inicio_anterior: null,
    saldo_actual_centavos: 10000000, ingresos_centavos: 1000000, gastos_centavos: 4840000, otros_movimientos_netos_centavos: 0,
    explicacion_otros_movimientos: "No hay otros movimientos en el periodo.", saldo_inicial_centavos: 13840000, saldo_inicial_anterior_centavos: null, saldo_despues_centavos: 10000000,
    correos_leidos: 0, contadores_gmail: { nuevos: 0, duplicados: 0, errores: 0, rechazados_autenticacion: 0, no_reconocidos: 0 },
    cobertura_verificada: false, advertencia_cobertura: "No se puede comprobar que los archivos incluyan todo el periodo.", huecos: [], resumen: CONTEOS_INVENTADOS, preguntas_pendientes: 0, no_reconocidos: 0, sin_categoria: 3, ...cambios };
}
export function resultadoArranqueInventado(cambios: Partial<Esquemas["ResultadoArranque"]> = {}): Esquemas["ResultadoArranque"] {
  const { token: _token, segundos: _segundos, ...calculo } = previaArranqueInventada();
  return { calculo, fase: "categorizar", fecha_inicio: "2026-08-10", saldo_inicial_centavos: calculo.saldo_inicial_centavos, sincronizacion: null,
    importacion: detalleInventado({ preguntas_pendientes: 0, no_en_banco_pendientes: 0, saldo_centavos: 10000000 }), ...cambios };
}
