/**
 * Estado de la sesión en el frontend.
 *
 * Al abrir la app se pregunta GET /api/sesion: si hay sesión (la misma cookie
 * que usa la interfaz de plantillas), se entra directo; si responde 401, se
 * muestra la pantalla de entrar. El token CSRF queda solo en memoria
 * (compartido/http/cliente.ts). Si más adelante cualquier llamada responde 401, la sesión
 * se cerró (venció, o se cambió SESSION_SECRET) y se vuelve a entrar con el
 * aviso "Tu sesión se cerró…".
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  alCerrarseLaSesion,
  api as apiPorDefecto,
  cabeceraCsrf,
  ErrorSinToken,
  guardarTokenCsrf,
  type ClienteApi,
  type Esquemas,
} from "@/compartido/http/cliente";
import { detalleDe, mensajeDeError, mensajeDeErrorAlEntrar } from "@/compartido/http/errores";
import { limpiarCachesAlSalir } from "@/pwa/registrar";
import { TEXTOS } from "@/compartido/textos/textos";

export type EstadoSesion =
  | { tipo: "comprobando" }
  /**
   * No se pudo saber si hay sesión: sin red (`sinRed`) o el servidor falló
   * (5xx u otra respuesta que no es 200 ni 401). No es lo mismo que no tener
   * sesión: mandar a "Entrar" haría creer que la contraseña es el problema.
   */
  | { tipo: "error"; sinRed: boolean; mensaje: string }
  /** Sin sesión: pantalla de entrar, con un aviso opcional. */
  | { tipo: "fuera"; aviso?: string }
  | { tipo: "dentro"; usuario: Esquemas["Usuario"] };

export interface ContextoSesion {
  estado: EstadoSesion;
  cliente: ClienteApi;
  /** Devuelve el mensaje de error, o `null` si entró. */
  entrar: (contrasena: string) => Promise<string | null>;
  /** Devuelve el mensaje de error, o `null` si cerró la sesión. */
  salir: () => Promise<string | null>;
  comprobar: () => Promise<void>;
}

const Contexto = createContext<ContextoSesion | null>(null);

export function ProveedorSesion({
  children,
  cliente = apiPorDefecto,
  alEntrar,
}: {
  children: ReactNode;
  cliente?: ClienteApi;
  alEntrar?: () => void;
}) {
  const [estado, setEstado] = useState<EstadoSesion>({ tipo: "comprobando" });
  const estadoActual = useRef(estado);
  estadoActual.current = estado;

  const cambiar = useCallback((nuevo: EstadoSesion) => {
    estadoActual.current = nuevo;
    setEstado(nuevo);
  }, []);

  const comprobar = useCallback(async () => {
    cambiar({ tipo: "comprobando" });
    try {
      const { data, error, response } = await cliente.GET("/api/sesion");
      if (data) {
        guardarTokenCsrf(data.csrf_token);
        cambiar({ tipo: "dentro", usuario: data.usuario });
      } else if (response.status === 401) {
        guardarTokenCsrf(null);
        cambiar({ tipo: "fuera" });
      } else {
        cambiar({
          tipo: "error",
          sinRed: false,
          mensaje: mensajeDeError(response.status, detalleDe(error)),
        });
      }
    } catch {
      cambiar({ tipo: "error", sinRed: true, mensaje: mensajeDeError(null) });
    }
  }, [cliente, cambiar]);

  // Un 401 con la sesión abierta: se cerró por fuera (venció, SESSION_SECRET).
  useEffect(() => {
    alCerrarseLaSesion(() => {
      if (estadoActual.current.tipo === "dentro") {
        void limpiarCachesAlSalir();
        cambiar({ tipo: "fuera", aviso: TEXTOS.errores.sesionCerrada });
      }
    });
    return () => alCerrarseLaSesion(null);
  }, [cambiar]);

  useEffect(() => {
    void comprobar();
  }, [comprobar]);

  const entrar = useCallback(
    async (contrasena: string) => {
      try {
        const { data, response } = await cliente.POST("/api/sesion", {
          body: { contrasena },
        });
        if (data) {
          guardarTokenCsrf(data.csrf_token);
          // Entrar es abrir la app: Inicio puede volver a sincronizar al abrir (ítem 38).
          alEntrar?.();
          cambiar({ tipo: "dentro", usuario: data.usuario });
          return null;
        }
        return mensajeDeErrorAlEntrar(response.status);
      } catch {
        return mensajeDeErrorAlEntrar(null);
      }
    },
    [cliente, cambiar, alEntrar],
  );

  const salir = useCallback(async () => {
    try {
      const { response } = await cliente.DELETE("/api/sesion", {
        params: { header: cabeceraCsrf() },
      });
      if (response.ok) {
        guardarTokenCsrf(null);
        // Ítem 18: que en Cache Storage no quede nada más que el cascarón.
        void limpiarCachesAlSalir();
        cambiar({ tipo: "fuera" });
        return null;
      }
      // 401: la sesión ya se había cerrado por fuera. El cliente ya avisó
      // (vigilarSesion) y la app muestra "Tu sesión se cerró…".
      if (response.status === 401) return null;
      return TEXTOS.errores.cerrarSesionFallo;
    } catch (e) {
      // Sin token en memoria no hay sesión que cerrar en este navegador.
      if (e instanceof ErrorSinToken) {
        void limpiarCachesAlSalir();
        cambiar({ tipo: "fuera" });
        return null;
      }
      return mensajeDeError(null);
    }
  }, [cliente, cambiar]);

  const valor = useMemo(
    () => ({ estado, cliente, entrar, salir, comprobar }),
    [estado, cliente, entrar, salir, comprobar],
  );
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useSesion(): ContextoSesion {
  const contexto = useContext(Contexto);
  if (!contexto) throw new Error("useSesion fuera de <ProveedorSesion>");
  return contexto;
}
