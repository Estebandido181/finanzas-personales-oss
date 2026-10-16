/**
 * Respuestas inventadas de la API para las pruebas de Inicio (las cifras del
 * prototipo aprobado). Tipadas con el esquema generado: si la API cambia,
 * TypeScript lo avisa aquí.
 */
import type { Esquemas } from "@/compartido/http/cliente";

export function reporteInventado(cambios: Partial<Esquemas["Reporte"]> = {}): Esquemas["Reporte"] {
  return {
    mes: "2026-09",
    nombre_mes: "septiembre de 2026",
    es_mes_actual: true,
    mes_anterior: "2026-08",
    mes_siguiente: "2026-10",
    total_gasto_centavos: 184_245_000,
    total_ingresos_centavos: 535_000_000,
    pendientes: 3,
    pendientes_centavos: 2_770_000,
    // Ítem 15: los ingresos pendientes van aparte, nunca sumados a los gastos.
    pendientes_ingresos_centavos: 0,
    saldo_centavos: 473_915_000,
    por_categoria: [
      { nombre: "Mercado", centavos: 48_624_950, porcentaje: 26.4, categoria: { id: 1, nombre: "Mercado", clase: "gasto", color: "cat-mercado", icono: "shopping-basket" } },
      { nombre: "Vivienda y servicios", centavos: 41_280_000, porcentaje: 22.4, categoria: { id: 4, nombre: "Vivienda y servicios", clase: "gasto", color: "cat-vivienda", icono: "house" } },
      { nombre: "Restaurantes", centavos: 29_840_000, porcentaje: 16.2, categoria: { id: 2, nombre: "Restaurantes", clase: "gasto", color: "cat-restaurantes", icono: "utensils" } },
      { nombre: "Transporte", centavos: 18_660_000, porcentaje: 10.1, categoria: { id: 3, nombre: "Transporte", clase: "gasto", color: "cat-transporte", icono: "bus" } },
      { nombre: "Compras", centavos: 15_990_000, porcentaje: 8.7, categoria: { id: 7, nombre: "Compras", clase: "gasto", color: "cat-compras", icono: "shopping-bag" } },
      { nombre: "Antojos", centavos: 9_630_000, porcentaje: 5.2, categoria: { id: 9, nombre: "Antojos", clase: "gasto", color: "cat-antojos", icono: "ice-cream-cone" } },
      { nombre: "Salud", centavos: 8_400_050, porcentaje: 4.6, categoria: { id: 5, nombre: "Salud", clase: "gasto", color: "cat-salud", icono: "heart-pulse" } },
      { nombre: "Entretenimiento", centavos: 6_200_000, porcentaje: 3.4, categoria: { id: 6, nombre: "Entretenimiento", clase: "gasto", color: "cat-entretenimiento", icono: "ticket" } },
      { nombre: "Otros", centavos: 2_850_000, porcentaje: 1.5, categoria: { id: 8, nombre: "Otros", clase: "gasto", color: "cat-otros", icono: "shapes" } },
      { nombre: "Sin categorizar", centavos: 2_770_000, porcentaje: 1.5, categoria: null },
    ],
    ...cambios,
  };
}

let siguienteId = 1;

export function movimientoInventado(cambios: Partial<Esquemas["Movimiento"]> = {}): Esquemas["Movimiento"] {
  return {
    id: siguienteId++,
    fecha_hora: "2026-09-30T07:40:00",
    tipo: "compra",
    descripcion: "PANADERIA EL TRIGAL",
    monto_centavos: 850_000,
    es_gasto: true,
    descartado: false,
    puede_descartar: false,
    motivo_no_descartar: null,
    puede_restaurar: false,
    motivo_no_restaurar: null,
    categoria: null,
    origen: "gmail",
    origen_categoria: null,
    regla: null,
    pendiente: true,
    categorizable: true,
    clase_categoria: "gasto",
    regla_posible: { campo: "comercio", texto: "panaderia el trigal" },
    // Ítem 17: una compra ofrece solo la regla por texto.
    reglas_posibles: [
      {
        condiciones: "texto",
        tipo_movimiento: "compra",
        campo: "comercio",
        texto: "panaderia el trigal",
        monto_centavos: null,
        frase: "compra en «panaderia el trigal»",
      },
    ],
    ...cambios,
  };
}

export function movimientosInventados(): Esquemas["Movimiento"][] {
  return [
    movimientoInventado(),
    movimientoInventado({
      fecha_hora: "2026-09-30T07:12:00",
      tipo: "transferencia",
      descripcion: "*3000000001",
      monto_centavos: 320_000,
      categoria: { id: 3, nombre: "Transporte", clase: "gasto", color: "cat-transporte", icono: "bus" },
      pendiente: false,
      regla_posible: { campo: "cuenta_destino", texto: "*3000000001" },
    }),
    movimientoInventado({
      fecha_hora: "2026-09-29T21:28:00",
      tipo: "transferencia",
      descripcion: "LAURA GÓMEZ EJEMPLO",
      monto_centavos: 620_000,
      regla_posible: { campo: "cuenta_destino", texto: "laura gómez ejemplo" },
    }),
    movimientoInventado({
      fecha_hora: "2026-09-29T18:15:00",
      descripcion: "SUPERMERCADO LA ESPIGA",
      monto_centavos: 13_244_950,
      categoria: { id: 1, nombre: "Mercado", clase: "gasto", color: "cat-mercado", icono: "shopping-basket" },
      pendiente: false,
      regla_posible: { campo: "comercio", texto: "supermercado la espiga" },
    }),
    movimientoInventado({
      fecha_hora: "2026-09-28T08:00:00",
      tipo: "ingreso",
      descripcion: "EMPRESA EJEMPLO S.A.S.",
      monto_centavos: 480_000_000,
      es_gasto: false,
      pendiente: false,
      categorizable: false,
      clase_categoria: null,
      regla_posible: null,
    }),
  ];
}

export function sincronizacionCorrecta(terminadaEn = "2026-09-30T06:02:00"): Esquemas["EstadoSincronizacion"] {
  return {
    en_curso: false,
    debe_sincronizar_al_abrir: false,
    ultima_correcta_en: terminadaEn,
    ultima: {
      terminada_en: terminadaEn,
      estado: "ok",
      origen: "comando",
      contadores: { nuevos: 3, duplicados: 0, no_reconocidos: 0, errores: 0, rechazados_autenticacion: 0 },
      codigo_error: null,
      mensaje: "Sincronización terminada: 3 nuevos, 0 duplicados, 0 no reconocidos, 0 errores, 0 rechazados.",
    },
  };
}

export function resultadoFallido(
  codigo: NonNullable<Esquemas["ResultadoSincronizacion"]["codigo_error"]> = "autorizacion_gmail",
): Esquemas["ResultadoSincronizacion"] {
  return {
    terminada_en: "2026-09-30T09:00:00",
    estado: "fallida",
    origen: "web",
    contadores: null,
    codigo_error: codigo,
    mensaje: "Mensaje inventado de la API para este error.",
  };
}

export function sincronizacionFallida(
  ultimaCorrectaEn: string | null = "2026-09-28T12:00:00",
  codigo: NonNullable<Esquemas["ResultadoSincronizacion"]["codigo_error"]> = "autorizacion_gmail",
): Esquemas["EstadoSincronizacion"] {
  return {
    en_curso: false,
    debe_sincronizar_al_abrir: false,
    ultima_correcta_en: ultimaCorrectaEn,
    ultima: resultadoFallido(codigo),
  };
}
