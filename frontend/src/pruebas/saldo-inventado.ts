/**
 * `GET /api/saldo` inventado (ítem 16), con las cifras del prototipo
 * aprobado (diseno/prototipo/saldo.html). Todos los datos son inventados.
 */
import type { Esquemas } from "@/compartido/http/cliente";

type Fila = Esquemas["IngresoOAjusteDelMes"];

/** Del más reciente al más antiguo, como los manda la API. */
export function filasInventadas(): Fila[] {
  return [
    {
      id: 41,
      fecha_hora: "2026-09-29T10:00:00",
      tipo: "ingreso",
      descripcion: "Efectivo venta bicicleta",
      monto_centavos: 15_000_000,
      origen: "manual",
      se_puede_borrar: true,
    },
    {
      id: 40,
      fecha_hora: "2026-09-28T08:00:00",
      tipo: "ingreso",
      descripcion: "EMPRESA EJEMPLO S.A.S.",
      monto_centavos: 480_000_000,
      origen: "gmail",
      se_puede_borrar: false,
    },
    {
      id: 33,
      fecha_hora: "2026-09-20T19:30:00",
      tipo: "ajuste",
      descripcion: "Ajuste de saldo",
      monto_centavos: -1_239_950,
      origen: "manual",
      se_puede_borrar: false,
    },
    {
      id: 30,
      fecha_hora: "2026-09-15T12:00:00",
      tipo: "ingreso",
      descripcion: "Efectivo arriendo garaje EJEMPLO",
      monto_centavos: 20_000_000,
      origen: "manual",
      // Anterior al último ajuste: la API no deja borrarlo.
      se_puede_borrar: false,
    },
    {
      id: 22,
      fecha_hora: "2026-09-05T09:10:00",
      tipo: "ajuste",
      descripcion: "Ajuste de saldo",
      monto_centavos: -600_050,
      origen: "manual",
      se_puede_borrar: false,
    },
  ];
}

export function saldoInventado(cambios: Partial<Esquemas["Saldo"]> = {}): Esquemas["Saldo"] {
  return {
    configuracion: { saldo_inicial_centavos: 125_000_000, fecha_inicio: "2026-09-01" },
    // Hay movimientos inventados: el backend diría que la configuración quedó fija.
    configuracion_fija: true,
    saldo_centavos: 473_915_000,
    desglose: {
      saldo_inicial_centavos: 125_000_000,
      ingresos_centavos: 535_000_000,
      gastos_centavos: 184_245_000,
      ajustes_centavos: -1_840_000,
    },
    mes: "2026-09",
    nombre_mes: "septiembre de 2026",
    del_mes: filasInventadas(),
    ajustes_del_mes: { total_centavos: -1_840_000, cantidad: 2 },
    ultimos: [],
    token_ingreso: "token-ingreso-inventado-1",
    fecha_hora_minima: "2026-09-01T00:00:00",
    ahora: "2026-09-30T09:15:00",
    hoy: "2026-09-30",
    maximo_descripcion: 200,
    ...cambios,
  };
}

/** Sin saldo configurado: solo `configuracion: null` y lo del mes. */
export function saldoSinConfigurar(): Esquemas["Saldo"] {
  return saldoInventado({
    configuracion: null,
    configuracion_fija: false,
    saldo_centavos: null,
    desglose: null,
    del_mes: [],
    ajustes_del_mes: null,
    token_ingreso: null,
    fecha_hora_minima: null,
  });
}
