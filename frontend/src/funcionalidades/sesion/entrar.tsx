import { CircleAlert } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import favicon from "../../../diseno/favicon.svg";
import { Aviso, Ayuda, Hoja } from "@/compartido/ui/libreta";
import { Button } from "@/compartido/ui/ui/button";
import { Etiqueta, Input } from "@/compartido/ui/ui/input";
import { useSesion } from "@/funcionalidades/sesion/sesion";
import { TEXTOS } from "@/compartido/textos/textos";

/** Errores que son del campo (van debajo de él); los demás, junto al botón. */
const ERRORES_DEL_CAMPO: readonly string[] = [
  TEXTOS.errores.contrasenaIncorrecta,
  TEXTOS.errores.contrasenaVacia,
];

/** Pantalla de entrar (prototipo login.html). */
export function Entrar({ aviso }: { aviso?: string }) {
  const { entrar } = useSesion();
  const [contrasena, setContrasena] = useState("");
  const [enCurso, setEnCurso] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const campo = useRef<HTMLInputElement>(null);
  const errorDelCampo = error !== null && ERRORES_DEL_CAMPO.includes(error);

  useEffect(() => {
    document.title = `Entrar · ${TEXTOS.app.nombre}`;
  }, []);

  useEffect(() => {
    if (errorDelCampo) campo.current?.focus();
  }, [error, errorDelCampo]);

  async function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (enCurso) return;
    if (contrasena === "") {
      setError(TEXTOS.errores.contrasenaVacia);
      return;
    }
    setEnCurso(true);
    setError(null);
    const mensaje = await entrar(contrasena);
    // Si entró, esta pantalla ya no existe.
    if (mensaje !== null) {
      setEnCurso(false);
      setError(mensaje);
      setContrasena("");
    }
  }

  return (
    <main className="min-h-screen grid place-items-center px-4 py-6">
      <Hoja className="w-full max-w-[24rem]" aria-labelledby="titulo-entrar">
        <div className="flex flex-col items-center gap-3 text-center mb-8">
          <img src={favicon} alt="" className="size-14" />
          <h1 id="titulo-entrar">{TEXTOS.entrar.titulo}</h1>
          <Ayuda>{TEXTOS.entrar.ayuda}</Ayuda>
        </div>
        {aviso ? (
          <Aviso tipo="info" className="mb-6">
            {aviso}
          </Aviso>
        ) : null}
        <form noValidate onSubmit={alEnviar}>
          <div className="flex flex-col gap-(--espacio-texto)">
            <Etiqueta htmlFor="contrasena">{TEXTOS.entrar.campo}</Etiqueta>
            <Input
              ref={campo}
              id="contrasena"
              name="contrasena"
              type="password"
              autoComplete="current-password"
              value={contrasena}
              onChange={(e) => setContrasena(e.target.value)}
              aria-invalid={errorDelCampo || undefined}
              aria-describedby={errorDelCampo ? "error-contrasena" : undefined}
            />
            {errorDelCampo ? (
              <p
                id="error-contrasena"
                className="flex items-start gap-1 text-destructive text-sm font-fuerte"
              >
                <CircleAlert aria-hidden="true" className="size-4 mt-0.5" />
                {error}
              </p>
            ) : null}
          </div>
          <Button type="submit" className="w-full mt-6" disabled={enCurso}>
            {enCurso ? TEXTOS.entrar.botonEnCurso : TEXTOS.entrar.boton}
          </Button>
          {error !== null && !errorDelCampo ? (
            <Aviso tipo="error" className="mt-4">
              {error}
            </Aviso>
          ) : null}
        </form>
      </Hoja>
    </main>
  );
}
