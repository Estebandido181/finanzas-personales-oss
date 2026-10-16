/**
 * Movimientos y "Sin categorizar" (ítem 14). Sigue el prototipo aprobado
 * (diseno/prototipo/movimientos.html) y TEXTOS.md, "Movimientos".
 *
 * El mes y los filtros van en la dirección (/app/movimientos?mes=2026-08&ver=
 * sin-categorizar); la API filtra. Cada día es una hoja. Un pendiente se
 * categoriza con un toque (sus opciones ya están abiertas en "Sin
 * categorizar", y en el primer pendiente de la lista); la regla, con un toque
 * más. "Cambiar" corrige la categoría: el movimiento queda "a mano".
 *
 * Ítem 15: los ingresos también se categorizan (solo con categorías de
 * ingreso) y su regla es por quien envía. Ítem 17: al categorizar se ofrecen
 * las reglas que manda la API (`reglas_posibles`): por texto, por monto y "Las
 * dos cosas juntas" en transferencias e ingresos; en compras, solo por texto.
 */
import { Aviso, Ayuda, Hoja, Vacio } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { Dialogo } from "@/compartido/ui/ui/dialogo";
import { CircleAlert, WifiOff } from "lucide-react";
import { pesos } from "@/compartido/formatos/formato";
import { TEXTOS } from "@/compartido/textos/textos";
import { Monto } from "@/compartido/ui/cifras";
import { Encabezado, Pila } from "@/compartido/ui/pantalla";
import { totalPendientes } from "@/funcionalidades/movimientos/cargar";
import { rutaMovimientos } from "@/funcionalidades/movimientos/datos";
import { useControlMovimientos } from "./controlador";
import { PanelFiltros, SelectorMes } from "./filtros";
import { Lista, ListaDescartados } from "./lista";
import { Cargando } from "./piezas";

const T = TEXTOS.movimientos;


export function Movimientos() {
  const { mes, filtros, carga, recargar, sincronizacion, bandeja, descartados, enviando, seleccion, setSeleccion, mutando, setListaOcupada, resultado, setResultado, error, navegacionBloqueada, bloqueado, revisar, cambiarDescarte, ultimoMes } = useControlMovimientos();


  return (
    <Pila>
      <Encabezado
        titulo={T.titulo}
        pantalla={`/movimientos?mes=${ultimoMes.current ?? ""}`}
        debajo={
          descartados ? <p className="font-fuerte">Descartados de todos los meses</p> : bandeja ? (
            <p className="font-fuerte">{T.bandejaTodosLosMeses}</p>
          ) : carga.tipo === "listo" && carga.datos.tipo === "mes" ? (
            <SelectorMes reporte={carga.datos.reporte} filtros={filtros} />
          ) : null
        }
      />
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
      ) : (
        <>
          <fieldset disabled={navegacionBloqueada}><PanelFiltros
            filtros={filtros}
            mes={mes}
            categorias={carga.datos.categorias}
            pendientes={totalPendientes(carga.datos)}
          /></fieldset>
          {error ? <Aviso tipo="error">{error}</Aviso> : null}
          {resultado ? <Hoja>
            <h2>{resultado.descartado ? "Movimiento descartado" : "Movimiento restaurado"}</h2>
            <div role="status" className="mt-4 space-y-3">
              <p>Monto actual: <Monto>{pesos(resultado.monto_centavos)}</Monto></p>
              <p>Saldo antes: {resultado.saldo_antes_centavos === null ? "Sin configurar" : <Monto>{pesos(resultado.saldo_antes_centavos)}</Monto>}</p>
              <p>Saldo después: {resultado.saldo_despues_centavos === null ? "Sin configurar" : <Monto>{pesos(resultado.saldo_despues_centavos)}</Monto>}</p>
              <Ayuda>{resultado.descartado ? "El movimiento queda fuera del saldo. Importarlo o recibir su aviso de nuevo no lo restaura." : "Se restauró el monto actual. El movimiento vuelve a estar incluido en el saldo."}</Ayuda>
            </div>
          </Hoja> : null}
          {sincronizacion.resultado ? (
            <Aviso tipo={sincronizacion.resultado.tipo}>{sincronizacion.resultado.texto}</Aviso>
          ) : null}
          {carga.datos.tipo === "descartados" ? <ListaDescartados datos={carga.datos.movimientos} ocupada={bloqueado} alRestaurar={(m) => revisar(m, true)} /> : <fieldset disabled={bloqueado}><Lista
            // Otro mes u otro filtro: la lista empieza de cero (sin resultados ni filas abiertas).
            key={rutaMovimientos(mes, filtros)}
            datos={carga.datos}
            actualizando={carga.actualizando}
            mes={mes}
            recargar={recargar}
            sincronizacion={sincronizacion}
            alRevisar={revisar}
            alOcupar={(ocupada) => { setListaOcupada(ocupada); if (ocupada) setResultado(null); }}
          /></fieldset>}
        </>
      )}
      {seleccion ? <Dialogo titulo={seleccion.restaurar ? "Restaurar movimiento" : "Descartar movimiento"}
        descripcion={<><p className="font-fuerte">{seleccion.movimiento.descripcion}</p><p>Monto actual: <Monto>{pesos(seleccion.movimiento.monto_centavos)}</Monto></p>
          <Ayuda>{seleccion.restaurar ? "Se restaurará el monto actual que ves aquí y volverá a estar incluido en el saldo." : "Quedará fuera del saldo. Seguirá en Descartados para que puedas restaurarlo; importar el archivo o recibir el aviso de nuevo no lo restaurará."}</Ayuda></>}
        alCerrar={() => { if (!enviando.current) setSeleccion(null); }} acciones={<>
          <Button variant="outline" disabled={mutando} onClick={() => setSeleccion(null)}>Cancelar</Button>
          <Button disabled={bloqueado} onClick={() => void cambiarDescarte()}>{mutando ? "Guardando…" : seleccion.restaurar ? "Sí, restaurar movimiento" : "Sí, descartar movimiento"}</Button>
        </>} /> : null}
    </Pila>
  );
}
