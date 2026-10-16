import { reiniciarSincronizacionAlAbrir } from "@/funcionalidades/sincronizacion/sincronizar";
import { CircleAlert, WifiOff } from "lucide-react";
import { useEffect } from "react";
import { Route, Router, Switch } from "wouter";
import type { BaseLocationHook, BaseSearchHook } from "wouter";
import { Hoja, Vacio } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { ProveedorContadorNoReconocidos } from "@/funcionalidades/sincronizacion/contador";
import { Marco } from "@/app/navegacion/marco";
import { useVisibleTras } from "@/compartido/ui/pantalla";
import { Categorias } from "@/funcionalidades/categorias/categorias";
import { ConfigurarSaldo } from "@/funcionalidades/saldo/configurar-saldo";
import { RUTA_CONFIGURAR } from "@/funcionalidades/saldo/datos";
import { Entrar } from "@/funcionalidades/sesion/entrar";
import { Inicio } from "@/funcionalidades/inicio/inicio";
import { Mas } from "@/app/pantallas/mas";
import { Movimientos } from "@/funcionalidades/movimientos/movimientos";
import { NoReconocidos } from "@/funcionalidades/sincronizacion/no-reconocidos";
import { NoEncontrada } from "@/app/pantallas/no-encontrada";
import { Saldo } from "@/funcionalidades/saldo/saldo";
import { ProveedorSesion, useSesion, type EstadoSesion } from "@/funcionalidades/sesion/sesion";
import type { ClienteApi } from "@/compartido/http/cliente";
import { ImportarBanco } from "@/funcionalidades/importaciones/importar";
import { ArranqueBanco, ResultadoArranqueBanco } from "@/funcionalidades/arranque/arranque";
import { PreguntasConciliacion, NoEstaEnBanco } from "@/funcionalidades/importaciones/diferencias";
import { DetalleBanco, CategorizarImportacion } from "@/funcionalidades/importaciones/detalle";
import { TEXTOS } from "@/compartido/textos/textos";

/** La app se publica en /app (D17); las rutas del enrutador van sin ese prefijo. */
export const BASE = "/app";

/** `hook` y `searchHook` sirven para las pruebas (wouter/memory-location). */
export function App({
  cliente,
  hook,
  searchHook,
}: {
  cliente?: ClienteApi;
  hook?: BaseLocationHook;
  searchHook?: BaseSearchHook;
}) {
  return (
    <ProveedorSesion cliente={cliente} alEntrar={reiniciarSincronizacionAlAbrir}>
      <Raiz hook={hook} searchHook={searchHook} />
    </ProveedorSesion>
  );
}

function Raiz({ hook, searchHook }: { hook?: BaseLocationHook; searchHook?: BaseSearchHook }) {
  const { estado, comprobar } = useSesion();
  switch (estado.tipo) {
    case "comprobando":
      return <Cargando />;
    case "error":
      return <ErrorAlAbrir estado={estado} reintentar={comprobar} />;
    case "fuera":
      return <Entrar aviso={estado.aviso} />;
    case "dentro":
      return (
        <Router
          base={hook ? "" : BASE}
          {...(hook ? { hook } : {})}
          {...(searchHook ? { searchHook } : {})}
        >
          <ProveedorContadorNoReconocidos>
            <Marco>
              <Switch>
                <Route path="/">
                  <Inicio />
                </Route>
                <Route path="/movimientos">
                  <Movimientos />
                </Route>
                <Route path="/categorias">
                  <Categorias />
                </Route>
                <Route path="/no-reconocidos">
                  <NoReconocidos />
                </Route>
                <Route path="/importar"><ImportarBanco /></Route>
                <Route path="/arranque"><ArranqueBanco /></Route>
                <Route path="/extender-historial"><ArranqueBanco extension /></Route>
                <Route path="/arranque/:id/categorizar">{(params) => <CategorizarImportacion id={Number(params.id)} volver={`/arranque/${params.id}`} />}</Route>
                <Route path="/arranque/:id">{(params) => <ResultadoArranqueBanco id={Number(params.id)} />}</Route>
                <Route path="/compartir"><ImportarBanco compartido /></Route>
                <Route path="/importacion"><DetalleBanco /></Route>
                <Route path="/importaciones/:id/categorizar">{(params) => <CategorizarImportacion id={Number(params.id)} />}</Route>
                <Route path="/importaciones/:id">{(params) => <DetalleBanco id={Number(params.id)} />}</Route>
                <Route path="/conciliacion/preguntas"><PreguntasConciliacion /></Route>
                <Route path="/conciliacion/no-esta-en-el-banco"><NoEstaEnBanco /></Route>
                {/* Ítem 16. */}
                <Route path={RUTA_CONFIGURAR}>
                  <ConfigurarSaldo />
                </Route>
                <Route path="/saldo">
                  <Saldo />
                </Route>
                <Route path="/mas">
                  <Mas />
                </Route>
                <Route>
                  <NoEncontrada />
                </Route>
              </Switch>
            </Marco>
          </ProveedorContadorNoReconocidos>
        </Router>
      );
  }
}

export { ESPERA_CARGANDO_MS } from "@/compartido/ui/pantalla";

function Cargando() {
  const visible = useVisibleTras();
  useEffect(() => {
    document.title = TEXTOS.app.nombre;
  }, []);
  return (
    <main className="min-h-screen grid place-items-center">
      {visible ? (
        <p role="status" className="text-muted-foreground">
          {TEXTOS.app.cargando}
        </p>
      ) : null}
    </main>
  );
}

/** No se pudo saber si hay sesión: sin red o el servidor falló (no es "sin sesión"). */
function ErrorAlAbrir({
  estado,
  reintentar,
}: {
  estado: Extract<EstadoSesion, { tipo: "error" }>;
  reintentar: () => Promise<void>;
}) {
  return (
    <main className="min-h-screen grid place-items-center px-4 py-6">
      <Hoja className="w-full max-w-[28rem]">
        <h1 className="sr-only">{TEXTOS.app.nombre}</h1>
        <Vacio
          icono={estado.sinRed ? WifiOff : CircleAlert}
          accion={
            <Button type="button" onClick={() => void reintentar()}>
              {TEXTOS.errores.volverAIntentar}
            </Button>
          }
        >
          <p role="alert">{estado.mensaje}</p>
        </Vacio>
      </Hoja>
    </main>
  );
}
