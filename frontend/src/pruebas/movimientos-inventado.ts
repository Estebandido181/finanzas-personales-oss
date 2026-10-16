/**
 * Respuestas inventadas de la API para las pruebas de Movimientos (ítem 14),
 * con los datos del prototipo aprobado. Tipadas con el esquema generado.
 */
import type { Esquemas } from "@/compartido/http/cliente";
import { movimientoInventado } from "@/pruebas/inicio-inventado";
import { pesos } from "@/compartido/formatos/formato";

export const CATEGORIAS_INVENTADAS: Esquemas["Categoria"][] = [
  { id: 1, nombre: "Mercado", clase: "gasto", color: "cat-mercado", icono: "shopping-basket" },
  { id: 2, nombre: "Restaurantes", clase: "gasto", color: "cat-restaurantes", icono: "utensils" },
  { id: 3, nombre: "Transporte", clase: "gasto", color: "cat-transporte", icono: "bus" },
  { id: 4, nombre: "Vivienda y servicios", clase: "gasto", color: "cat-vivienda", icono: "house" },
  { id: 5, nombre: "Salud", clase: "gasto", color: "cat-salud", icono: "heart-pulse" },
  { id: 6, nombre: "Entretenimiento", clase: "gasto", color: "cat-entretenimiento", icono: "ticket" },
  { id: 7, nombre: "Compras", clase: "gasto", color: "cat-compras", icono: "shopping-bag" },
  { id: 8, nombre: "Otros", clase: "gasto", color: "cat-otros", icono: "shapes" },
  { id: 9, nombre: "Antojos", clase: "gasto", color: "cat-antojos", icono: "ice-cream-cone" },
  // Ítem 15: las de ingreso.
  { id: 10, nombre: "Sueldo", clase: "ingreso", color: "cat-sueldo", icono: "briefcase" },
  { id: 11, nombre: "Préstamos", clase: "ingreso", color: "cat-prestamos", icono: "handshake" },
  { id: 12, nombre: "Otros ingresos", clase: "ingreso", color: "cat-otros-ingresos", icono: "coins" },
];

const CAMPO_POR_TIPO = { compra: "comercio", transferencia: "cuenta_destino", ingreso: "quien_envia" } as const;

/** Ítem 17: como la API, transferencias e ingresos ofrecen por texto, por monto y las dos; las compras, por texto. */
function reglasPosibles(base: Esquemas["Movimiento"]): Esquemas["OpcionRegla"][] {
  if (base.tipo === "ajuste") return [];
  const tipo = base.tipo;
  const campo = CAMPO_POR_TIPO[tipo];
  const texto = base.descripcion.toLowerCase();
  const monto = pesos(base.monto_centavos);
  const conector = { compra: "en", transferencia: "a", ingreso: "de" }[tipo];
  const porTexto = { condiciones: "texto", tipo_movimiento: tipo, campo, texto, monto_centavos: null, frase: `${tipo} ${conector} «${texto}»` } as const;
  if (tipo === "compra") return [porTexto];
  return [
    porTexto,
    { condiciones: "monto", tipo_movimiento: tipo, campo, texto: null, monto_centavos: base.monto_centavos, frase: `${tipo} de ${monto}` },
    { condiciones: "texto_y_monto", tipo_movimiento: tipo, campo, texto, monto_centavos: base.monto_centavos, frase: `${tipo} ${conector} «${texto}» por ${monto}` },
  ];
}

/**
 * Un movimiento como lo manda la API: `pendiente`, `categorizable` y
 * `regla_posible` coherentes con el tipo y la categoría (en la API los
 * decide el backend; aquí se inventan iguales).
 */
export function movimiento(cambios: Partial<Esquemas["Movimiento"]> = {}): Esquemas["Movimiento"] {
  const base = movimientoInventado(cambios);
  // Ítem 15: los ingresos también se categorizan (con categorías de ingreso, regla por quien envía).
  const categorizable = base.tipo !== "ajuste";
  return {
    ...base,
    pendiente: categorizable && base.categoria === null,
    categorizable,
    clase_categoria: !categorizable ? null : base.tipo === "ingreso" ? "ingreso" : "gasto",
    regla_posible:
      base.tipo === "ajuste"
        ? null
        : { campo: CAMPO_POR_TIPO[base.tipo], texto: base.descripcion.toLowerCase() },
    reglas_posibles: reglasPosibles(base),
    ...cambios,
  };
}

/**
 * Septiembre de 2026 (hoy es el 30): dos pendientes, uno por regla de
 * comercio, uno por regla de cuenta destino, uno a mano, uno de antes de
 * guardar cómo, uno cuya regla se borró, un ingreso y un ajuste.
 */
export function movimientosDelMesInventados(): Esquemas["Movimiento"][] {
  return [
    movimiento({ id: 101 }),
    movimiento({
      id: 102,
      fecha_hora: "2026-09-30T07:12:00",
      tipo: "transferencia",
      descripcion: "*3000000001",
      monto_centavos: 320_000,
      categoria: { id: 3, nombre: "Transporte", clase: "gasto", color: "cat-transporte", icono: "bus" },
      origen_categoria: "regla",
      regla: { modo_texto: "exacta", origen_regla: "todos", id: 11, tipo_movimiento: "transferencia", campo: "cuenta_destino", texto: "*3000000001", monto_centavos: null, condiciones: "texto", frase: "transferencia a «*3000000001»" },
    }),
    movimiento({
      id: 103,
      fecha_hora: "2026-09-29T18:15:00",
      descripcion: "SUPERMERCADO LA ESPIGA",
      monto_centavos: 13_244_950,
      categoria: { id: 1, nombre: "Mercado", clase: "gasto", color: "cat-mercado", icono: "shopping-basket" },
      origen_categoria: "regla",
      regla: { modo_texto: "exacta", origen_regla: "todos", id: 12, tipo_movimiento: "compra", campo: "comercio", texto: "supermercado la espiga", monto_centavos: null, condiciones: "texto", frase: "compra en «supermercado la espiga»" },
    }),
    movimiento({
      id: 104,
      fecha_hora: "2026-09-29T13:10:00",
      descripcion: "DROGUERIA SAN ROQUE EJEMPLO",
      monto_centavos: 4_200_050,
      categoria: { id: 5, nombre: "Salud", clase: "gasto", color: "cat-salud", icono: "heart-pulse" },
      origen_categoria: "manual",
    }),
    movimiento({
      id: 106,
      fecha_hora: "2026-09-28T17:52:00",
      descripcion: "TIENDA DON PEPE EJEMPLO",
      monto_centavos: 1_300_000,
    }),
    movimiento({
      id: 107,
      fecha_hora: "2026-09-28T13:30:00",
      descripcion: "RESTAURANTE DOÑA TERE EJEMPLO",
      monto_centavos: 3_890_000,
      categoria: { id: 2, nombre: "Restaurantes", clase: "gasto", color: "cat-restaurantes", icono: "utensils" },
      origen_categoria: "desconocido",
    }),
    movimiento({
      id: 105,
      fecha_hora: "2026-09-28T08:00:00",
      tipo: "ingreso",
      descripcion: "EMPRESA EJEMPLO S.A.S.",
      monto_centavos: 480_000_000,
      es_gasto: false,
      categoria: { id: 10, nombre: "Sueldo", clase: "ingreso", color: "cat-sueldo", icono: "briefcase" },
      origen_categoria: "regla",
      regla: { modo_texto: "exacta", origen_regla: "todos", id: 13, tipo_movimiento: "ingreso", campo: "quien_envia", texto: "empresa ejemplo s.a.s.", monto_centavos: null, condiciones: "texto", frase: "ingreso de «empresa ejemplo s.a.s.»" },
    }),
    movimiento({
      id: 109,
      fecha_hora: "2026-09-27T23:00:00",
      tipo: "ajuste",
      descripcion: "Ajuste de saldo",
      monto_centavos: -1_840_000,
      es_gasto: false,
    }),
    movimiento({
      id: 108,
      fecha_hora: "2026-09-27T16:20:00",
      descripcion: "HELADERIA POLO NORTE EJEMPLO",
      monto_centavos: 1_200_000,
      categoria: { id: 9, nombre: "Antojos", clase: "gasto", color: "cat-antojos", icono: "ice-cream-cone" },
      origen_categoria: "regla",
      regla: null,
    }),
  ];
}

/**
 * Ítem 38: un grupo de pendientes iguales, como lo arma el servidor (`grupos`
 * de GET /api/movimientos/sin-categorizar). Por omisión, 20 viajes de bus
 * inventados de $3.200 cada uno, con ids 301 a 320.
 */
export function grupoInventado(cambios: Partial<Esquemas["GrupoPendientes"]> = {}): Esquemas["GrupoPendientes"] {
  const cuantos = cambios.cuantos ?? cambios.ids?.length ?? 20;
  const ids = cambios.ids ?? Array.from({ length: cuantos }, (_, i) => 320 - i);
  return {
    clave: "compra|cobro viaje transporte masivo",
    tipo: "compra",
    descripcion: "COBRO VIAJE TRANSPORTE MASIVO",
    clase_categoria: "gasto",
    es_gasto: true,
    suma_centavos: cuantos * 320_000,
    ids,
    regla: {
      condiciones: "texto",
      tipo_movimiento: "compra",
      campo: "comercio",
      texto: "cobro viaje transporte masivo",
      monto_centavos: null,
      frase: "compra en «cobro viaje transporte masivo»",
    },
    ...cambios,
    cuantos,
  };
}
