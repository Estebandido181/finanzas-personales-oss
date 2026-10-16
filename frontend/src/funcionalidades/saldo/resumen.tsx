/** Saldo actual, desglose y estado sin configurar. */
import { pesos } from "@/compartido/formatos/formato";
import { TEXTOS } from "@/compartido/textos/textos";
import { Monto, NombreCifra, SubrayadoDoble } from "@/compartido/ui/cifras";
import { Ayuda, Hoja, Vacio } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { cn } from "@/compartido/ui/utils";
import { montoConSigno, RUTA_CONFIGURAR, textoLlevasDesde, type Desglose } from "@/funcionalidades/saldo/datos";
import { ChevronDown, Wallet } from "lucide-react";
import { useId } from "react";
import { Link } from "wouter";
import { COLOR_MONTO, FilaCifra } from "./piezas";

const T = TEXTOS.saldo;


/** Sin saldo configurado: lleva a "Configurar saldo" (funcionalidades/saldo/configurar-saldo.tsx). */
export function SinConfigurar() {
  const t = T.sinConfigurar;
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
        <p>{TEXTOS.inicio.sinSaldo.texto}</p>
        <p>{t.texto}</p>
      </Vacio>
    </Hoja>
  );
}


// --- Saldo actual y desglose ------------------------------------------------------

export function HojaSaldo({ saldo, desglose, fechaInicio }: { saldo: number; desglose: Desglose; fechaInicio: string }) {
  const ajustes = montoConSigno(desglose.ajustes_centavos);
  return (
    <Hoja aria-label={T.saldoActual}>
      <div className="flex flex-col gap-(--espacio-texto)">
        <NombreCifra>{T.saldoActual}</NombreCifra>
        <p>
          <Monto className="text-monto-grande font-fuerte tracking-[-0.02em]">{pesos(saldo)}</Monto>
        </p>
        <Ayuda>{textoLlevasDesde(fechaInicio)}</Ayuda>
      </div>
      <details className="group mt-(--espacio-grupo) border-t border-regla pt-2">
        <summary
          className={cn(
            "flex items-center gap-2 w-fit min-h-(--tactil-min) font-fuerte cursor-pointer list-none",
            "[&::-webkit-details-marker]:hidden hover:[&>span]:underline hover:[&>span]:underline-offset-3",
          )}
        >
          <ChevronDown
            aria-hidden="true"
            className="size-5 transition-transform duration-(--duracion-corta) ease-libreta motion-reduce:transition-none group-open:rotate-180"
          />
          <span>{T.verComoSeCalcula}</span>
        </summary>
        <div className="pt-3 pb-1 max-w-[30rem] flex flex-col gap-3">
          <FilaCifra nombre={T.saldoInicial}>
            <Monto>{pesos(desglose.saldo_inicial_centavos)}</Monto>
          </FilaCifra>
          <FilaCifra nombre={T.ingresos}>
            <Monto className={cn(desglose.ingresos_centavos > 0 && "text-monto-positivo")}>
              {pesos(desglose.ingresos_centavos, { conSigno: true })}
            </Monto>
          </FilaCifra>
          <FilaCifra nombre={T.gastos}>
            <Monto>{pesos(-desglose.gastos_centavos)}</Monto>
          </FilaCifra>
          <FilaCifra nombre={T.ajustes}>
            <Monto className={COLOR_MONTO[ajustes.clase]}>{ajustes.texto}</Monto>
          </FilaCifra>
          {/* Total de libreta: raya simple arriba y doble abajo. */}
          <div className="flex justify-between items-baseline gap-3 pt-3 border-t border-border font-fuerte">
            <span>{T.saldoActual}</span>
            <SubrayadoDoble>
              <Monto>{pesos(saldo)}</Monto>
            </SubrayadoDoble>
          </div>
        </div>
      </details>
    </Hoja>
  );
}
