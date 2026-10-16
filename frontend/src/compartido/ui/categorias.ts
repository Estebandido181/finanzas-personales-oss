/**
 * Color e ícono de cada categoría (SISTEMA.md, "Categorías: color e ícono").
 *
 * Desde el ítem 15 la API manda en cada categoría su `color` (un token
 * `cat-*`) y su `icono` (un nombre de Lucide): son claves, no valores. Aquí
 * se traducen a una clase y a un componente. Las listas salen del esquema
 * (`esquema.d.ts`): si la API suma un color o un ícono, TypeScript obliga a
 * agregarlo aquí. Una clave desconocida se pinta como "Otros".
 *
 * `clase` fija la variable `--c` con el token de la categoría; los
 * componentes la usan con `bg-(--c)` o `fill-(--c)`. Las clases van escritas
 * enteras para que Tailwind las encuentre.
 */
import {
  Briefcase,
  Bus,
  CircleDashed,
  Coins,
  Handshake,
  HeartPulse,
  House,
  IceCreamCone,
  Shapes,
  ShoppingBag,
  ShoppingBasket,
  Ticket,
  Utensils,
  type LucideIcon,
} from "lucide-react";
import type { Esquemas } from "@/compartido/http/cliente";

export type ClaveColor = Esquemas["Categoria"]["color"];
export type ClaveIcono = Esquemas["Categoria"]["icono"];
/** Lo que hace falta para pintar una categoría. */
export type ConEstilo = Pick<Esquemas["Categoria"], "color" | "icono">;

export interface EstiloCategoria {
  color: string;
  icono: LucideIcon;
  /** "Sin categorizar": cuadro hueco con borde punteado. */
  vacia: boolean;
}

/** El nombre que usa la API (finanzas/reporte.py, SIN_CATEGORIZAR). */
export const SIN_CATEGORIZAR = "Sin categorizar";

/**
 * La paleta (SISTEMA.md), en su orden: clase de Tailwind y nombre del color
 * para el selector de "Nueva categoría" (el lector de pantalla lo lee).
 */
const COLOR: Readonly<Record<ClaveColor, { clase: string; nombre: string }>> = {
  "cat-mercado": { clase: "[--c:var(--cat-mercado)]", nombre: "Oliva" },
  "cat-restaurantes": { clase: "[--c:var(--cat-restaurantes)]", nombre: "Óxido" },
  "cat-transporte": { clase: "[--c:var(--cat-transporte)]", nombre: "Azul desteñido" },
  "cat-vivienda": { clase: "[--c:var(--cat-vivienda)]", nombre: "Verde azulado" },
  "cat-salud": { clase: "[--c:var(--cat-salud)]", nombre: "Vino" },
  "cat-entretenimiento": { clase: "[--c:var(--cat-entretenimiento)]", nombre: "Ciruela" },
  "cat-compras": { clase: "[--c:var(--cat-compras)]", nombre: "Mostaza" },
  "cat-antojos": { clase: "[--c:var(--cat-antojos)]", nombre: "Rosa viejo" },
  "cat-otros": { clase: "[--c:var(--cat-otros)]", nombre: "Pizarra" },
  "cat-sueldo": { clase: "[--c:var(--cat-sueldo)]", nombre: "Verde botella" },
  "cat-prestamos": { clase: "[--c:var(--cat-prestamos)]", nombre: "Índigo desteñido" },
  "cat-otros-ingresos": { clase: "[--c:var(--cat-otros-ingresos)]", nombre: "Bronce" },
};

/** Los 12 íconos de categoría (SISTEMA.md), con un nombre para el lector de pantalla. */
const ICONO: Readonly<Record<ClaveIcono, { icono: LucideIcon; nombre: string }>> = {
  "shopping-basket": { icono: ShoppingBasket, nombre: "Canasta" },
  utensils: { icono: Utensils, nombre: "Cubiertos" },
  bus: { icono: Bus, nombre: "Bus" },
  house: { icono: House, nombre: "Casa" },
  "heart-pulse": { icono: HeartPulse, nombre: "Corazón" },
  ticket: { icono: Ticket, nombre: "Boleta" },
  "shopping-bag": { icono: ShoppingBag, nombre: "Bolsa de compras" },
  "ice-cream-cone": { icono: IceCreamCone, nombre: "Helado" },
  shapes: { icono: Shapes, nombre: "Figuras" },
  briefcase: { icono: Briefcase, nombre: "Maletín" },
  handshake: { icono: Handshake, nombre: "Apretón de manos" },
  coins: { icono: Coins, nombre: "Monedas" },
};

export const COLORES = Object.keys(COLOR) as ClaveColor[];
export const ICONOS = Object.keys(ICONO) as ClaveIcono[];

export function nombreColor(clave: ClaveColor): string {
  return COLOR[clave].nombre;
}

export function nombreIcono(clave: ClaveIcono): string {
  return ICONO[clave].nombre;
}

export function claseColor(clave: ClaveColor): string {
  return Object.hasOwn(COLOR, clave) ? COLOR[clave].clase : COLOR["cat-otros"].clase;
}

export function componenteIcono(clave: ClaveIcono): LucideIcon {
  return Object.hasOwn(ICONO, clave) ? ICONO[clave].icono : Shapes;
}

const SIN: EstiloCategoria = {
  color: "[--c:var(--cat-sin-categorizar)]",
  icono: CircleDashed,
  vacia: true,
};

/** Estilo de una categoría de la API; `null` es "Sin categorizar" (hueca). */
export function estiloCategoria(categoria: ConEstilo | null | undefined): EstiloCategoria {
  if (!categoria) return SIN;
  return { color: claseColor(categoria.color), icono: componenteIcono(categoria.icono), vacia: false };
}
