import type { Esquemas } from "@/compartido/http/cliente";
import { fechaEnFrase, fechaYHora, textoSincronizado } from "@/compartido/formatos/formato";
import { cantidad } from "@/compartido/textos/cantidad";

export type EstadoSincronizacionApi = Esquemas["EstadoSincronizacion"];
export type ResultadoSincronizacion = Esquemas["ResultadoSincronizacion"];
export type Contadores = Esquemas["Contadores"];

// --- Sincronización ----------------------------------------------------------------

export type VistaSincronizacion =
  | { tipo: "nunca"; texto: string }
  | { tipo: "correcta"; texto: string }
  | {
      tipo: "fallida";
      texto: string;
      codigo: NonNullable<ResultadoSincronizacion["codigo_error"]>;
      /** "28 de septiembre", o `null` si nunca salió bien. */
      desde: string | null;
      mensajeApi: string;
    };

/** Qué dice el encabezado sobre la última sincronización, y si falló. */
export function vistaSincronizacion(estado: EstadoSincronizacionApi, hoy: string): VistaSincronizacion {
  const ultima = estado.ultima;
  if (!ultima) return { tipo: "nunca", texto: "Todavía no se ha sincronizado." };
  if (ultima.estado !== "fallida") {
    return { tipo: "correcta", texto: textoSincronizado(ultima.terminada_en, hoy) };
  }
  const correcta = estado.ultima_correcta_en;
  return {
    tipo: "fallida",
    texto: correcta
      ? `Falló la sincronización. Última correcta: ${fechaYHora(correcta, hoy)}`
      : "Falló la sincronización. Todavía no hay ninguna sincronización correcta.",
    codigo: ultima.codigo_error ?? "error_inesperado",
    desde: correcta ? fechaEnFrase(correcta, hoy) : null,
    mensajeApi: ultima.mensaje,
  };
}

/**
 * Resultado de «Sincronizar ahora» que salió bien (TEXTOS.md, "Confirmaciones
 * y resultados"): los nuevos, y solo lo demás que importa. Los duplicados no
 * se mencionan. Los rechazados por autenticación también quedan en No
 * reconocidos, así que se cuentan juntos.
 */
export function textoResultado(contadores: Contadores): string {
  const nuevos =
    contadores.nuevos === 0
      ? "Sincronización terminada: no hay movimientos nuevos"
      : `Sincronización terminada: ${cantidad(contadores.nuevos, "movimiento nuevo", "movimientos nuevos")}`;
  const extras: string[] = [];
  const noReconocidos = contadores.no_reconocidos + contadores.rechazados_autenticacion;
  if (noReconocidos > 0) {
    extras.push(
      `${cantidad(noReconocidos, "correo no reconocido", "correos no reconocidos")} (ver No reconocidos)`,
    );
  }
  if (contadores.errores > 0) {
    extras.push(
      contadores.errores === 1
        ? "1 correo que no se pudo leer: se reintenta en la próxima sincronización"
        : `${contadores.errores} correos que no se pudieron leer: se reintentan en la próxima sincronización`,
    );
  }
  if (extras.length === 0) return `${nuevos}.`;
  return `${nuevos} y ${extras.join(" y ")}.`;
}

/** "3 movimientos sin categorizar" / "1 movimiento sin categorizar". */
