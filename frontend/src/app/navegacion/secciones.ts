import {
  ArrowLeftRight,
  BookOpen,
  Ellipsis,
  MailQuestionMark,
  Tags,
  Wallet,
  type LucideIcon,
} from "lucide-react";

/**
 * Las secciones de la app y dónde aparece cada una (SISTEMA.md, "Navegación"):
 * - barra lateral (computador): Inicio, Movimientos, Saldo, Categorías y reglas, No reconocidos;
 * - barra inferior (celular): Inicio, Movimientos, Saldo, Categorías, Más.
 * Las rutas son relativas a /app (el enrutador tiene base "/app").
 */
export interface Seccion {
  id: "inicio" | "movimientos" | "saldo" | "categorias" | "no-reconocidos" | "mas";
  ruta: string;
  /** Título de la pantalla y texto en la barra lateral. */
  nombre: string;
  /** Texto en la barra inferior, donde el espacio es poco. */
  nombreCorto: string;
  icono: LucideIcon;
  enLateral: boolean;
  enInferior: boolean;
}

export const SECCIONES: readonly Seccion[] = [
  {
    id: "inicio",
    ruta: "/",
    nombre: "Inicio",
    nombreCorto: "Inicio",
    icono: BookOpen,
    enLateral: true,
    enInferior: true,
  },
  {
    id: "movimientos",
    ruta: "/movimientos",
    nombre: "Movimientos",
    nombreCorto: "Movimientos",
    icono: ArrowLeftRight,
    enLateral: true,
    enInferior: true,
  },
  {
    id: "saldo",
    ruta: "/saldo",
    nombre: "Saldo",
    nombreCorto: "Saldo",
    icono: Wallet,
    enLateral: true,
    enInferior: true,
  },
  {
    id: "categorias",
    ruta: "/categorias",
    nombre: "Categorías y reglas",
    nombreCorto: "Categorías",
    icono: Tags,
    enLateral: true,
    enInferior: true,
  },
  {
    id: "no-reconocidos",
    ruta: "/no-reconocidos",
    nombre: "No reconocidos",
    nombreCorto: "No reconocidos",
    icono: MailQuestionMark,
    enLateral: true,
    enInferior: false,
  },
  {
    id: "mas",
    ruta: "/mas",
    nombre: "Más",
    nombreCorto: "Más",
    icono: Ellipsis,
    enLateral: false,
    enInferior: true,
  },
];

/** Nombre largo en el menú "Más" (TEXTOS.md: "Correos no reconocidos"). */
export const NOMBRE_EN_MAS: Partial<Record<Seccion["id"], string>> = {
  "no-reconocidos": "Correos no reconocidos",
};

/**
 * ¿Es `ruta` la sección de `ubicacion`? `ubicacion` es la ruta actual sin la
 * base /app ("/", "/saldo", "/saldo/algo"). Inicio solo es actual en "/".
 */
export function esSeccionActual(ruta: string, ubicacion: string): boolean {
  const limpia = ubicacion.length > 1 ? ubicacion.replace(/\/+$/, "") : ubicacion;
  if (ruta === "/") return limpia === "/" || limpia === "";
  return limpia === ruta || limpia.startsWith(`${ruta}/`);
}

export function seccion(id: Seccion["id"]): Seccion {
  const encontrada = SECCIONES.find((s) => s.id === id);
  if (!encontrada) throw new Error(`Sección desconocida: ${id}`);
  return encontrada;
}
