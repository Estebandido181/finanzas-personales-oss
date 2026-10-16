/**
 * Lo que muestra "Correos no reconocidos" (ítem 19), calculado a partir de las
 * respuestas de la API. Lógica pura (sin React), probada en datos.test.ts.
 *
 * La API decide qué se reprocesa y cómo: aquí solo se cuenta el resultado en
 * una frase. Ojo: `siguen_sin_reconocerse` incluye los correos anteriores a la
 * fecha de inicio, así que la frase dice "siguen sin reconocerse" y nunca
 * "el lector no los reconoce".
 */
import type { Esquemas } from "@/compartido/http/cliente";
import { hora, leerFechaHora, MESES } from "@/compartido/formatos/formato";

export type CorreoNoReconocido = Esquemas["CorreoNoReconocido"];
export type ResultadoReproceso = Esquemas["ResultadoReproceso"];
export type ContadoresReproceso = Esquemas["ContadoresReproceso"];

/** Del más reciente al más antiguo; los que no traen fecha, al final. */
export function ordenarPorFecha(correos: readonly CorreoNoReconocido[]): CorreoNoReconocido[] {
  return [...correos].sort((a, b) => (b.fecha ?? "").localeCompare(a.fecha ?? ""));
}

/** "29 de septiembre de 2026, 9:28 p. m." (siempre con año, como el prototipo). */
export function fechaDelCorreo(fecha: string | null): string {
  if (fecha === null) return "Sin fecha";
  const { anio, mes, dia } = leerFechaHora(fecha);
  return `${dia} de ${MESES[mes - 1]} de ${anio}, ${hora(fecha)}`;
}

export interface TextoReproceso {
  /** La primera frase: "Se volvieron a procesar 4 correos." */
  titulo: string;
  /** El detalle: "1 creó un movimiento nuevo; 3 siguen sin reconocerse." */
  detalle: string;
  /** Con errores de lectura el aviso es informativo, no de éxito. */
  tipo: "exito" | "info";
}

/** El aviso de un reproceso que terminó (`ok` o `con_errores`). */
export function textoReproceso(c: ContadoresReproceso): TextoReproceso {
  if (c.revisados === 0) {
    return { titulo: "No había correos para volver a procesar.", detalle: "", tipo: "exito" };
  }
  const titulo =
    c.revisados === 1
      ? "Se volvió a procesar 1 correo."
      : `Se volvieron a procesar ${c.revisados} correos.`;
  const partes: string[] = [
    c.movimientos_creados === 0
      ? c.revisados === 1
        ? "No creó ningún movimiento nuevo"
        : "Ninguno creó un movimiento nuevo"
      : c.movimientos_creados === 1
        ? "1 creó un movimiento nuevo"
        : `${c.movimientos_creados} crearon un movimiento nuevo`,
  ];
  if (c.siguen_sin_reconocerse > 0) {
    partes.push(
      c.siguen_sin_reconocerse === 1
        ? "1 sigue sin reconocerse"
        : `${c.siguen_sin_reconocerse} siguen sin reconocerse`,
    );
  }
  if (c.ya_registrados > 0) {
    partes.push(
      c.ya_registrados === 1 ? "1 ya estaba registrado" : `${c.ya_registrados} ya estaban registrados`,
    );
  }
  if (c.errores > 0) {
    partes.push(
      c.errores === 1
        ? "1 no se pudo leer y sigue en la lista"
        : `${c.errores} no se pudieron leer y siguen en la lista`,
    );
  }
  return { titulo, detalle: `${partes.join("; ")}.`, tipo: c.errores > 0 ? "info" : "exito" };
}
