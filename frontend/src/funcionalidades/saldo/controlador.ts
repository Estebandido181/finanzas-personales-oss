/** Estado de la pantalla y coordinación de sus operaciones. */
import { useDeshacer } from "@/compartido/deshacer/usar";
import { pesos } from "@/compartido/formatos/formato";
import { ingresoRestaurado } from "@/compartido/textos/textos";
import { borrarIngreso, useDatosSaldo } from "@/funcionalidades/saldo/cargar";
import { textoIngresoBorrado, type FilaDelMes } from "@/funcionalidades/saldo/datos";
import { useSesion } from "@/funcionalidades/sesion/sesion";
import { useSincronizar } from "@/funcionalidades/sincronizacion/sincronizar";
import { useCallback, useState } from "react";

export function useControlSaldo() {
  const { cliente } = useSesion();
  const { carga, recargar } = useDatosSaldo(cliente);
  const [borrandoId, setBorrandoId] = useState<number | null>(null);
  const [sincronizacionFallida, setSincronizacionFallida] = useState(false);
  const [mutaciones, setMutaciones] = useState({ ingreso: false, ajuste: false });
  // Borrar un ingreso es tocar y deshacer (ítem 38): sin diálogo de confirmación.
  const deshacer = useDeshacer(cliente, () => recargar(true));

  const borrar = async (fila: FilaDelMes) => {
    deshacer.limpiar();
    setBorrandoId(fila.id);
    const r = await borrarIngreso(cliente, fila.id);
    setBorrandoId(null);
    if (r.tipo === "sin-sesion") return;
    if (r.tipo === "error") {
      // 409 y 404 no cambian al reintentar: se vuelve a leer para que el botón desaparezca si ya no aplica.
      deshacer.mostrarError(r.texto);
      if (r.estado === 409 || r.estado === 404) void recargar(true);
      return;
    }
    deshacer.ofrecer({
      deshacer: r.datos.deshacer,
      texto: textoIngresoBorrado(r.datos.monto_centavos),
      restaurado: (d) => ingresoRestaurado(d.saldo_centavos === null ? null : pesos(d.saldo_centavos)),
    });
    void recargar(true);
  };

  const alTerminarSincronizacion = useCallback(
    async (fallida: boolean) => {
      setSincronizacionFallida(fallida);
      await recargar(true);
    },
    [recargar],
  );
  const sincronizacion = useSincronizar(cliente, alTerminarSincronizacion, null);
  return { carga, recargar, borrandoId, sincronizacionFallida, setSincronizacionFallida, mutaciones, setMutaciones, deshacer, borrar, sincronizacion };
}
