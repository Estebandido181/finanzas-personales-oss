import type { Esquemas } from "@/compartido/http/cliente";

export type Movimiento = Esquemas["Movimiento"];
export type Categoria = Esquemas["Categoria"];
export type Reporte = Esquemas["Reporte"];
export type ReglaAplicada = Esquemas["ReglaAplicada"];
export type ReglaPosible = Esquemas["ReglaPosible"];
/** Ítem 38: pendientes iguales que se categorizan juntos (los arma el servidor). */
export type GrupoPendientes = Esquemas["GrupoPendientes"];
/** Ítem 17: una regla que se ofrece crear al categorizar (`reglas_posibles`). */
export type OpcionRegla = Esquemas["OpcionRegla"];
export type Condiciones = OpcionRegla["condiciones"];
/** Los parámetros de GET /api/movimientos, tal como los declara la API. */
export type ConsultaMovimientos = NonNullable<
  import("@/api/esquema").operations["ver_movimientos"]["parameters"]["query"]
>;
