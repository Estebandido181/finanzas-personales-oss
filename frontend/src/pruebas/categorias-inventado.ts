/**
 * Datos inventados de "Categorías y reglas" (ítem 15) para las pruebas de
 * unidad: las categorías iniciales con su uso y unas reglas, como las del
 * prototipo aprobado (categorias.html).
 */
import type { Esquemas } from "@/compartido/http/cliente";

type ConUso = Esquemas["CategoriaConUso"];

function categoria(
  id: number,
  nombre: string,
  clase: ConUso["clase"],
  color: ConUso["color"],
  icono: ConUso["icono"],
  movimientosMes: number,
  movimientosTotal: number,
  reglas: number,
): ConUso {
  return {
    id,
    nombre,
    clase,
    color,
    icono,
    movimientos_mes: movimientosMes,
    movimientos_total: movimientosTotal,
    reglas,
    // Dato inventado; en la app lo calcula el servidor (ítem 38).
    se_puede_deshacer_borrado: movimientosTotal === 0 && reglas === 0,
  };
}

/** En el orden de la API: primero las de gasto ("Otros" al final) y luego las de ingreso. */
export const CATEGORIAS_CON_USO: ConUso[] = [
  categoria(1, "Mercado", "gasto", "cat-mercado", "shopping-basket", 14, 40, 1),
  categoria(2, "Restaurantes", "gasto", "cat-restaurantes", "utensils", 11, 30, 0),
  categoria(3, "Transporte", "gasto", "cat-transporte", "bus", 38, 90, 1),
  categoria(4, "Vivienda y servicios", "gasto", "cat-vivienda", "house", 4, 10, 1),
  categoria(5, "Salud", "gasto", "cat-salud", "heart-pulse", 3, 6, 0),
  categoria(6, "Entretenimiento", "gasto", "cat-entretenimiento", "ticket", 2, 5, 1),
  categoria(7, "Compras", "gasto", "cat-compras", "shopping-bag", 5, 9, 0),
  categoria(9, "Antojos", "gasto", "cat-antojos", "ice-cream-cone", 12, 12, 1),
  categoria(8, "Otros", "gasto", "cat-otros", "shapes", 2, 4, 0),
  categoria(10, "Sueldo", "ingreso", "cat-sueldo", "briefcase", 1, 2, 1),
  categoria(11, "Préstamos", "ingreso", "cat-prestamos", "handshake", 0, 0, 0),
  categoria(12, "Otros ingresos", "ingreso", "cat-otros-ingresos", "coins", 1, 1, 0),
];

export function reglaInventada(cambios: Partial<Esquemas["Regla"]> = {}): Esquemas["Regla"] {
  return {
    modo_texto: "exacta",
    origen_regla: "todos",
    id: 21,
    tipo_movimiento: "compra",
    campo: "comercio",
    texto: "supermercado la espiga",
    // Ítem 17: regla por texto (sin monto).
    monto_centavos: null,
    condiciones: "texto",
    categoria: { id: 1, nombre: "Mercado", clase: "gasto", color: "cat-mercado", icono: "shopping-basket" },
    frase: "Si es una compra en «supermercado la espiga», va a Mercado",
    ...cambios,
  };
}

export function reglasInventadas(): Esquemas["Regla"][] {
  return [
    reglaInventada(),
    reglaInventada({
      id: 22,
      tipo_movimiento: "transferencia",
      campo: "cuenta_destino",
      texto: "*3000000001",
      categoria: { id: 3, nombre: "Transporte", clase: "gasto", color: "cat-transporte", icono: "bus" },
      frase: "Si es una transferencia a «*3000000001», va a Transporte",
    }),
    reglaInventada({
      id: 23,
      tipo_movimiento: "ingreso",
      campo: "quien_envia",
      texto: "empresa ejemplo s.a.s.",
      categoria: { id: 10, nombre: "Sueldo", clase: "ingreso", color: "cat-sueldo", icono: "briefcase" },
      frase: "Si es un ingreso de «empresa ejemplo s.a.s.», va a Sueldo",
    }),
  ];
}
