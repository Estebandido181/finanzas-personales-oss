/**
 * Saldo, ingresos y ajustes (ítem 16). Sigue el prototipo aprobado
 * (diseno/prototipo/saldo.html) y TEXTOS.md, "Saldo".
 *
 * - Hoja del saldo: "Saldo actual" y, plegado, "Ver cómo se calcula" (un
 *   `<details>` nativo) con el desglose que manda la API.
 * - "Registrar un ingreso" y "Ajustar el saldo", lado a lado en el computador.
 * - "Ingresos y ajustes de {mes}": total de ajustes del mes y la lista. El
 *   botón "Borrar ingreso" sale solo donde la API dice `se_puede_borrar`; al
 *   borrar, la API lo vuelve a comprobar y un 409 se muestra sin tocar la lista.
 *
 * Los montos llegan en centavos y solo se pasan a pesos al mostrarlos.
 */
import { TEXTOS } from "@/compartido/textos/textos";
import { Hoja, Vacio } from "@/compartido/ui/libreta";
import { Encabezado, Pila } from "@/compartido/ui/pantalla";
import { Button } from "@/compartido/ui/ui/button";
import { ComprobarSaldo } from "@/funcionalidades/saldo/comprobar";
import { CircleAlert, RefreshCw, WifiOff } from "lucide-react";
import { useControlSaldo } from "./controlador";
import { AjustarSaldo, RegistrarIngreso } from "./formularios";
import { HojaDelMes } from "./lista";
import { Cargando } from "./piezas";
import { HojaSaldo, SinConfigurar } from "./resumen";

const T = TEXTOS.saldo;


export function Saldo() {
  const { carga, recargar, borrandoId, sincronizacionFallida, setSincronizacionFallida, mutaciones, setMutaciones, deshacer, borrar, sincronizacion } = useControlSaldo();


  return (
    <Pila>
      <Encabezado titulo={T.titulo} />
      {carga.tipo === "cargando" ? (
        <Cargando />
      ) : carga.tipo === "error" ? (
        <Hoja>
          <Vacio
            icono={carga.sinRed ? WifiOff : CircleAlert}
            accion={
              <Button type="button" onClick={() => void recargar()}>
                {TEXTOS.errores.volverAIntentar}
              </Button>
            }
          >
            <p role="alert">{carga.mensaje}</p>
          </Vacio>
        </Hoja>
      ) : carga.datos.configuracion === null || carga.datos.desglose === null ? (
        <SinConfigurar />
      ) : (
        <div aria-busy={carga.actualizando} className="flex flex-col gap-(--espacio-bloques)">
          <HojaSaldo
            saldo={carga.datos.saldo_centavos ?? 0}
            desglose={carga.datos.desglose}
            fechaInicio={carga.datos.configuracion.fecha_inicio}
          />
          <ComprobarSaldo contexto={carga.datos} deshabilitado={carga.actualizando || borrandoId !== null || sincronizacion.enCurso || mutaciones.ingreso || mutaciones.ajuste || deshacer.estado?.fase === "deshaciendo"} />
          <div className="grid gap-(--espacio-bloques) computador:grid-cols-2 computador:items-start">
            <RegistrarIngreso
              datos={carga.datos}
              alOcuparse={(ingreso) => setMutaciones((prev) => ({ ...prev, ingreso }))}
              alCambiar={() => {
                deshacer.limpiar();
                return recargar(true);
              }}
            />
            <AjustarSaldo
              alOcuparse={(ajuste) => setMutaciones((prev) => ({ ...prev, ajuste }))}
              alCambiar={() => {
                deshacer.limpiar();
                return recargar(true);
              }}
              sincronizar={
                <>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={sincronizacion.enCurso}
                    onClick={() => {
                      setSincronizacionFallida(false);
                      void sincronizacion.sincronizar();
                    }}
                  >
                    <RefreshCw aria-hidden="true" className="size-5" />
                    {sincronizacion.enCurso ? TEXTOS.inicio.sincronizando : TEXTOS.inicio.sincronizarAhora}
                  </Button>
                </>
              }
              resultadoSincronizacion={
                sincronizacionFallida
                  ? { tipo: "error", texto: T.ajustar.sincronizacionFallida }
                  : sincronizacion.resultado
              }
            />
          </div>
          <HojaDelMes
            datos={carga.datos}
            aviso={deshacer.estado}
            alDeshacer={() => void deshacer.deshacer()}
            alPausar={deshacer.pausar}
            alReanudar={deshacer.reanudar}
            borrandoId={borrandoId}
            alBorrar={(fila) => void borrar(fila)}
          />
        </div>
      )}
    </Pila>
  );
}

export { Campo,Cargando,ErrorCampo,FilaCifra } from "./piezas";
