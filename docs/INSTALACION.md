# Instalación

## Requisitos

Ubuntu/Linux, Python 3.12, Node 24, npm y Git. La interfaz está en español y
trabaja con los formatos de Bancolombia descritos en el código. Cada instancia
es de un solo propietario. Las pruebas de permisos, respaldo y migración se
validan en Linux; Windows no ofrece las mismas garantías POSIX.

## Demo local

Desde la raíz, instala las dependencias y compila:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -c backend/constraints-linux-py312.txt -r backend/requirements-dev.txt -e .
cd frontend
npm ci --ignore-scripts
npm run build
cd ..
python scripts/servidor_e2e.py --puerto 8123
```

Abre http://127.0.0.1:8123/app/ y entra con `clave-e2e-inventada`.
El servidor usa una base temporal y Gmail falso. Al cerrarlo se pierde esa base.
La contraseña es pública y las rutas de reinicio son de pruebas: usa solo datos
inventados, mantén el puerto en loopback y no lo despliegues como servidor real.

## Instancia personal con datos propios

Con el entorno activado y el frontend compilado:

1. Copia `.env.example` a `.env`. Este archivo está ignorado por Git.
2. Ejecuta `python -m finanzas.seguridad`: pide dos veces una contraseña de al
   menos 12 caracteres y devuelve su hash. Copia solo el hash en APP_PASSWORD_HASH.
3. Genera SESSION_SECRET con el comando siguiente y guárdalo solo en `.env`:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

4. Para HTTP en loopback usa COOKIE_SECURE=false. En un servidor real exige HTTPS
   y COOKIE_SECURE=true. Deja GMAIL_TOKEN vacío si aún no autorizaste Gmail.
5. Protege el archivo y prepara una base nueva o respaldada:

   ```bash
   chmod 600 .env
   set -a
   . ./.env
   set +a
   mkdir -p respaldos
   python -m finanzas.migrar --respaldos respaldos
   uvicorn --factory finanzas.web.app:crear_app --host 127.0.0.1 --port 8000
   ```

Abre http://127.0.0.1:8000/app/. La aplicación no crea tablas automáticamente.
No ejecutes la demo de pruebas sobre esta base. Para Gmail sigue [GMAIL.md](GMAIL.md).
Para un servidor HTTPS consulta [deploy/GUIA.md](../deploy/GUIA.md) y revisa antes
sus comandos: son ejemplos para una instalación propia de Ubuntu, no un servicio
administrado. No necesitas ejecutar infraestructura cloud para probar la app.

## Actualizaciones y límites

Haz y verifica un respaldo antes de migrar una base con datos. Conserva las doce
migraciones existentes; no edites revisiones ya aplicadas. El comando de migración
respalda una base con datos antes de modificarla. Comprueba la posibilidad de
reversión en la guía y conserva un respaldo restaurable.

Consulta [SECURITY.md](../SECURITY.md) para cookies de siete días, revocación,
protección del token y almacenamiento sensible. Se admite un solo worker; las
vistas previas y límites de intentos son de memoria. Verifica el saldo con el banco
y resuelve las preguntas ambiguas: importar un reporte no certifica su integridad.
