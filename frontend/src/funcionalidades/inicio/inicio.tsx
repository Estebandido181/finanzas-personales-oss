import { ErrorSincronizacion } from "@/funcionalidades/sincronizacion/error";
/**
 * Inicio: el reporte del mes (ítem 13). Sigue el prototipo aprobado
 * (diseno/prototipo/inicio.html e inicio-error.html) y TEXTOS.md.
 *
 * El mes va en la dirección (/app/?mes=2026-08, como en la v1); sin él, el mes
 * actual. Los totales, el gasto por categoría y los porcentajes vienen hechos
 * de la API (los mismos de la v1): aquí solo se muestran.
 */
import {
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  CircleDashed,
  HandCoins,
  Info,
  TriangleAlert,
  RefreshCw,
  Scale,
  Wallet,
  WifiOff,
} from "lucide-react";
import { useCallback, useId, useState, type ReactNode } from "react";
import { Link, useSearch } from "wouter";
import { Aviso, AvisoConTitulo, Ayuda, Hoja, Vacio } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { cn } from "@/compartido/ui/utils";
import { useSesion } from "@/funcionalidades/sesion/sesion";
import {
  TEXTOS,
  textosMesVacio,
} from "@/compartido/textos/textos";
import { useDatosInicio, type DatosInicio } from "@/funcionalidades/inicio/cargar";
import { useSincronizar, useSincronizarAlAbrir } from "@/funcionalidades/sincronizacion/sincronizar";
import { mesSiguienteVisible } from "@/compartido/formatos/mes";
import { montoDeFila, llevaMarcaDeCategoria } from "@/funcionalidades/movimientos/presentacion";
import { queEs, rutaDelMes, tituloPendientes, partesPendientes, type PartesPendientes, ultimosMovimientos, type Movimiento } from "@/funcionalidades/inicio/datos";
import { vistaSincronizacion, type VistaSincronizacion } from "@/funcionalidades/sincronizacion/estado";
import {
  esMes,
  hora,
  hoyColombia,
  mesActualColombia,
  nombreMes,
  nombreMesCorto,
  pesos,
  tituloMes,
} from "@/compartido/formatos/formato";
import { EnQueSeFue } from "@/funcionalidades/inicio/grafico";
import { EstadoRevisionesInicio } from "@/funcionalidades/inicio/estado";
import { rutaMovimientos } from "@/funcionalidades/movimientos/datos";
import { MarcaCategoria, MarcaNeutra, Monto, NombreCifra, SubrayadoDoble } from "@/compartido/ui/cifras";
import { ResumenImportacionInicio } from "@/funcionalidades/importaciones/inicio";
import { ArranqueBanco } from "@/funcionalidades/arranque/arranque";
import { dato } from "@/compartido/http/dato";
import { useCarga } from "@/compartido/http/carga";
import { RUTA_CONFIGURAR } from "@/funcionalidades/saldo/datos";
import { Encabezado, Pila, useVisibleTras } from "@/compartido/ui/pantalla";

export function Inicio() {
  const { cliente } = useSesion();
  const obtenerArranque = useCallback(() => dato(cliente.GET("/api/arranque/estado")), [cliente]);
  const arranque = useCarga(obtenerArranque);
  const parametro = new URLSearchParams(useSearch()).get("mes");
  const mes = parametro === null || parametro === "" ? null : parametro;
  const { carga, recargar } = useDatosInicio(cliente, mes);
  // Cada vez que la sincronización falla, el aviso grande se vuelve a montar
  // (role="alert" se anuncia de nuevo aunque ya estuviera).
  const [vecesFallida, setVecesFallida] = useState(0);
  const alTerminar = useCallback(
    async (fallida: boolean) => {
      if (fallida) setVecesFallida((n) => n + 1);
      await recargar(true);
    },
    [recargar],
  );
  const sincronizacion = useSincronizar(cliente, alTerminar, mes);
  // Ítem 38: si el servidor dice que toca, sincroniza sola, una vez, al abrir.
  useSincronizarAlAbrir(
    carga.tipo === "listo" && carga.datos.sincronizacion.debe_sincronizar_al_abrir,
    sincronizacion.sincronizar,
  );

  // El título sale de la dirección, así ya está mientras carga.
  const mesPedido = mes ?? mesActualColombia();
  const titulo = esMes(mesPedido) ? tituloMes(mesPedido) : seccionInicio;

  if (arranque.carga.tipo === "listo" && arranque.carga.datos.mostrar_arranque_inicial) return <ArranqueBanco />;
  if (arranque.carga.tipo === "error") return <Pila><Encabezado titulo="Inicio" /><Aviso tipo="error">{arranque.carga.mensaje}</Aviso><Button onClick={() => void arranque.recargar()}>Volver a intentar</Button></Pila>;
  if (arranque.carga.tipo === "cargando") return <Pila><Encabezado titulo={titulo} /><Cargando /></Pila>;

  if (carga.tipo !== "listo") {
    return (
      <Pila>
        <Encabezado titulo={titulo} />
        {carga.tipo === "cargando" ? (
          <Cargando />
        ) : (
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
        )}
      </Pila>
    );
  }

  return (
    <Reporte
      datos={carga.datos}
      sincronizacion={sincronizacion}
      claveAviso={vecesFallida}
    />
  );
}

const seccionInicio = "Inicio";

function Cargando() {
  const visible = useVisibleTras();
  return visible ? (
    <p role="status" className="text-muted-foreground">
      {TEXTOS.app.cargando}
    </p>
  ) : null;
}

function Reporte({
  datos,
  sincronizacion,
  claveAviso,
}: {
  datos: DatosInicio;
  sincronizacion: ReturnType<typeof useSincronizar>;
  claveAviso: number;
}) {
  const { reporte, movimientos, sincronizacion: estadoSinc } = datos;
  const hoy = hoyColombia();
  const mes = nombreMes(reporte.mes);
  const siguiente = mesSiguienteVisible(reporte, mesActualColombia());
  const vista = vistaSincronizacion(estadoSinc, hoy);
  const sinSaldo = reporte.saldo_centavos === null;
  const mesVacio = movimientos.length === 0;

  return (
    <Pila>
      <Encabezado
        titulo={tituloMes(reporte.mes)}
        antes={<SelectorMes anterior={reporte.mes_anterior} siguiente={siguiente} />}
      >
        <div className="flex flex-wrap items-center gap-3">
          <Button asChild variant="outline"><Link href="/importar">Importar movimientos del banco</Link></Button>
          <EstadoSincronizacion vista={vista} {...sincronizacion} />
        </div>
      </Encabezado>
      <EstadoRevisionesInicio revision={datos} ocupado={sincronizacion.enCurso} />

      {sincronizacion.resultado ? (
        <Aviso tipo={sincronizacion.resultado.tipo}>{sincronizacion.resultado.texto}</Aviso>
      ) : null}

      {vista.tipo === "fallida" ? <ErrorSincronizacion key={claveAviso} vista={vista} /> : null}

      <ResumenImportacionInicio revision={estadoSinc.ultima?.terminada_en} />

      {reporte.pendientes > 0 ? (
        <Pendientes cantidad={reporte.pendientes} montos={partesPendientes(reporte)} />
      ) : null}

      {sinSaldo ? (
        <SinSaldo />
      ) : (
        <>
          <Resumen
            mes={mes}
            gasto={reporte.total_gasto_centavos}
            saldo={reporte.saldo_centavos ?? 0}
            ingresos={reporte.total_ingresos_centavos}
          />
          {mesVacio ? (
            <MesVacio
              mes={mes}
              esMesActual={reporte.es_mes_actual}
              sincronizacion={sincronizacion}
            />
          ) : (
            <div className="grid gap-(--espacio-bloques) computador:grid-cols-[7fr_5fr] computador:items-start">
              <EnQueSeFue
                categorias={reporte.por_categoria}
                totalCentavos={reporte.total_gasto_centavos}
                nombreMes={mes}
              />
              <UltimosMovimientos movimientos={ultimosMovimientos(movimientos)} />
            </div>
          )}
        </>
      )}
    </Pila>
  );
}

function SelectorMes({ anterior, siguiente }: { anterior: string | null; siguiente: string | null }) {
  if (!anterior && !siguiente) return null;
  return (
    <nav aria-label={TEXTOS.inicio.cambiarDeMes} className="flex flex-wrap items-center gap-2">
      {anterior ? (
        <Button asChild variant="ghost">
          <Link href={rutaDelMes(anterior)} rel="prev">
            <ChevronLeft aria-hidden="true" className="size-5" />
            {nombreMesCorto(anterior)}
          </Link>
        </Button>
      ) : null}
      {siguiente ? (
        <Button asChild variant="ghost" className="ml-auto">
          <Link href={rutaDelMes(siguiente)} rel="next">
            {nombreMesCorto(siguiente)}
            <ChevronRight aria-hidden="true" className="size-5" />
          </Link>
        </Button>
      ) : null}
    </nav>
  );
}

function EstadoSincronizacion({
  vista,
  enCurso,
  sincronizar,
}: {
  vista: VistaSincronizacion;
} & ReturnType<typeof useSincronizar>) {
  const fallida = vista.tipo === "fallida";
  const Icono = fallida ? TriangleAlert : vista.tipo === "correcta" ? CircleCheck : Info;
  return (
    <div className="flex flex-wrap items-center gap-3">
      <p
        className={cn(
          "inline-flex items-center gap-2 text-sm",
          fallida ? "text-destructive font-fuerte" : "text-muted-foreground",
        )}
      >
        <Icono
          aria-hidden="true"
          className={cn("size-5", vista.tipo === "correcta" && "text-exito")}
        />
        <span>{vista.texto}</span>
      </p>
      <BotonSincronizar enCurso={enCurso} sincronizar={sincronizar} />
    </div>
  );
}

function BotonSincronizar({
  enCurso,
  sincronizar,
  variante = "outline",
}: {
  enCurso: boolean;
  sincronizar: () => Promise<void>;
  variante?: "outline" | "default";
}) {
  return (
    <Button type="button" variant={variante} disabled={enCurso} onClick={() => void sincronizar()}>
      <RefreshCw aria-hidden="true" className="size-5" />
      {enCurso ? TEXTOS.inicio.sincronizando : TEXTOS.inicio.sincronizarAhora}
    </Button>
  );
}

function Pendientes({ cantidad, montos }: { cantidad: number; montos: PartesPendientes }) {
  const t = TEXTOS.inicio.pendientes;
  const id = useId();
  return (
    <AvisoConTitulo
      tipo="advertencia"
      icono={CircleDashed}
      titulo={tituloPendientes(cantidad)}
      idTitulo={id}
      acciones={
        <Button asChild>
          {/* La bandeja es una sola, de todos los meses (como este número): sin mes. */}
          <Link href={rutaMovimientos(null, { vista: "sin-categorizar", categoria: null })}>
            {TEXTOS.inicio.categorizarAhora}
          </Link>
        </Button>
      }
    >
      {/* Gastos e ingresos pendientes nunca se suman en una sola cifra (ítem 15). */}
      {montos.tipo === "gastos" ? (
        <p>
          {t.suman} <Monto>{pesos(montos.gastos)}</Monto>. {t.enElGrafico}
        </p>
      ) : montos.tipo === "ambos" ? (
        <>
          <p>
            {t.gastosSuman} <Monto>{pesos(montos.gastos)}</Monto>. {t.enElGrafico}
          </p>
          <p>
            {t.aparteIngresos} <Monto>{pesos(montos.ingresos, { conSigno: true })}</Monto>.
          </p>
        </>
      ) : (
        <p>
          {t.soloIngresos} <Monto>{pesos(montos.ingresos, { conSigno: true })}</Monto>.
        </p>
      )}
    </AvisoConTitulo>
  );
}

function Resumen({
  mes,
  gasto,
  saldo,
  ingresos,
}: {
  mes: string;
  gasto: number;
  saldo: number;
  ingresos: number;
}) {
  return (
    <Hoja
      aria-label={`Resumen de ${mes}`}
      className="grid gap-6 computador:grid-cols-[1.4fr_1fr] computador:items-stretch"
    >
      <div className="flex flex-col gap-(--espacio-texto)">
        <NombreCifra>Gastado en {mes}</NombreCifra>
        <p>
          <SubrayadoDoble>
            <Monto className="text-monto-grande font-fuerte tracking-[-0.02em]">{pesos(gasto)}</Monto>
          </SubrayadoDoble>
        </p>
        <Ayuda>{TEXTOS.inicio.ayudaGasto}</Ayuda>
      </div>
      <div
        className={cn(
          "grid gap-4 border-t border-renglon pt-6",
          "computador:border-t-0 computador:pt-0 computador:border-l computador:pl-8",
          "computador:content-center computador:gap-6",
        )}
      >
        <Cifra nombre={TEXTOS.inicio.saldoActual}>
          <Monto className={CLASE_MONTO_MEDIO}>{pesos(saldo)}</Monto>
        </Cifra>
        <Cifra nombre={`Ingresos de ${mes}`}>
          <Monto className={cn(CLASE_MONTO_MEDIO, ingresos > 0 && "text-monto-positivo")}>
            {pesos(ingresos, { conSigno: true })}
          </Monto>
        </Cifra>
      </div>
    </Hoja>
  );
}

const CLASE_MONTO_MEDIO = "text-lg computador:text-xl font-fuerte";

/** En el celular, fila de libreta (nombre a la izquierda, monto a la derecha); en el computador, apilada. */
function Cifra({ nombre, children }: { nombre: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-3 computador:block computador:[&>*+*]:mt-(--espacio-texto)">
      <NombreCifra>{nombre}</NombreCifra>
      <p>{children}</p>
    </div>
  );
}

function UltimosMovimientos({ movimientos }: { movimientos: Movimiento[] }) {
  const id = useId();
  return (
    <Hoja aria-labelledby={id}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-2 mb-(--espacio-cabeza-hoja) pb-3 border-b-[3px] border-double border-regla">
        <h2 id={id}>{TEXTOS.inicio.ultimosMovimientos}</h2>
      </div>
      <ul>
        {movimientos.map((m) => (
          <FilaMovimiento key={m.id} movimiento={m} />
        ))}
      </ul>
      <p className="mt-(--espacio-grupo)">
        <Button asChild variant="outline" className="w-full">
          <Link href="/movimientos">{TEXTOS.inicio.verTodos}</Link>
        </Button>
      </p>
    </Hoja>
  );
}

function FilaMovimiento({ movimiento }: { movimiento: Movimiento }) {
  const monto = montoDeFila(movimiento);
  return (
    <li
      className={cn(
        "grid grid-cols-[auto_minmax(0,1fr)_auto] gap-x-3 items-start py-(--espacio-fila) last:pb-0",
        "[grid-template-areas:'marca_desc_monto'_'marca_meta_meta'] not-first:border-t not-first:border-renglon",
      )}
    >
      {llevaMarcaDeCategoria(movimiento) ? (
        <MarcaCategoria categoria={movimiento.categoria} className="[grid-area:marca] mt-0.5" />
      ) : (
        <MarcaNeutra
          icono={movimiento.tipo === "ingreso" ? HandCoins : Scale}
          className="[grid-area:marca] mt-0.5"
        />
      )}
      <p className="[grid-area:desc] font-medio [overflow-wrap:anywhere]">{movimiento.descripcion}</p>
      <p className="[grid-area:meta] text-muted-foreground text-sm">
        {queEs(movimiento)} · {hora(movimiento.fecha_hora)}
      </p>
      <p className="[grid-area:monto] text-right">
        <Monto
          className={cn(
            monto.clase === "suma" && "text-monto-positivo",
            monto.clase === "resta" && "text-monto-negativo",
          )}
        >
          {monto.texto}
        </Monto>
      </p>
    </li>
  );
}

function SinSaldo() {
  const t = TEXTOS.inicio.sinSaldo;
  const id = useId();
  return (
    <Hoja aria-labelledby={id}>
      <Vacio
        icono={Wallet}
        titulo={t.titulo}
        idTitulo={id}
        accion={
          <Button asChild>
            <Link href={RUTA_CONFIGURAR}>{t.boton}</Link>
          </Button>
        }
      >
        <p>{t.texto}</p>
      </Vacio>
    </Hoja>
  );
}

function MesVacio({
  mes,
  esMesActual,
  sincronizacion,
}: {
  mes: string;
  esMesActual: boolean;
  sincronizacion: ReturnType<typeof useSincronizar>;
}) {
  const t = textosMesVacio(mes, esMesActual);
  const id = useId();
  return (
    <Hoja aria-labelledby={id}>
      <Vacio
        icono={CircleDashed}
        titulo={t.titulo}
        idTitulo={id}
        accion={
          esMesActual ? (
            <BotonSincronizar
              enCurso={sincronizacion.enCurso}
              sincronizar={sincronizacion.sincronizar}
              variante="default"
            />
          ) : undefined
        }
      >
        <p>{t.texto}</p>
      </Vacio>
    </Hoja>
  );
}
