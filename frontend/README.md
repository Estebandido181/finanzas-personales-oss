> En esta distribución se omitieron las capturas históricas. `npm run capturas` las regenera con datos sintéticos; no se versionan. La organización y los comandos siguientes describen la aplicación conservada.

# Frontend

App React que se publica en `/app` (ítem 12, D16 y D17). Solo habla con la API
(`/api`). El sistema de diseño vive en [`diseno/`](diseno/SISTEMA.md) y es la
única fuente de colores, medidas, fuentes y textos.

```
frontend/
├── diseno/              sistema de diseño, tokens y prototipos aprobados
├── public/              tema inicial, manifest e íconos
├── pwa/                 plugin de compilación y generador de íconos
├── src/
│   ├── app/             entrada, rutas /app, navegación, Más y No encontrada
│   ├── api/             esquema.d.ts generado desde OpenAPI (ruta estable)
│   ├── funcionalidades/ pantallas, controladores y unidades junto a su función:
│   │                    sesión, Inicio, Movimientos, Categorías, Saldo,
│   │                    Sincronización, Importaciones y Arranque
│   ├── compartido/      transporte HTTP/errores, formatos, textos, tema,
│   │                    deshacer y componentes existentes del diseño
│   ├── pwa/             registro y worker: solo cascarón estático
│   └── pruebas/         API simulada y datos inventados compartidos
├── e2e/                 flujos, axe, CSP y capturas contra FastAPI
└── dist/                compilación servida por el backend (ignorada)
```

Las funcionalidades conservan sus estados de carga y refresco. `compartido/`
no importa funcionalidades ni composición. El proveedor de sesión recibe el
aviso `alEntrar`; `app/` lo conecta al reinicio de sincronización, antes de
montar las pantallas autenticadas. Sincronización es dueña de ese controlador,
su marca de apertura, su panel de error y los correos no reconocidos.
Las pruebas de fronteras comprueban estos límites, incluidos imports relativos
y diferidos. Movimientos separa filtros/URL, días y tipos de sus textos de
presentación; el índice conserva su interfaz de consumo.


## Comandos

Necesitan Node 24 (el mismo del CI y de la VM).

| Comando | Qué hace |
|---|---|
| `npm ci --ignore-scripts` | Instala las versiones exactas del lock, sin ejecutar scripts de terceros. |
| `npm run tipos` | Regenera `src/api/esquema.d.ts` desde `../openapi/openapi.json`. |
| `npm run build` | Comprueba tipos (`tsc`) y compila a `dist/`. |
| `npm test` | Pruebas de unidad (Vitest + Testing Library, API simulada). |
| `npm run e2e` | Pruebas en navegador contra la app real (ver abajo). Compila antes. |
| `npm run capturas` | Todas las capturas para los PR en `capturas/` (ver "Capturas"). |
| `npm run dev` | Vite con recarga en caliente; reenvía `/api` a `127.0.0.1:8000`. Sin service worker. |
| `node pwa/generar-iconos.mjs` | Regenera los íconos de `public/iconos/` desde `diseno/favicon.svg` (solo si cambia el favicon). |

Las pruebas en navegador levantan la app de FastAPI con `../scripts/servidor_e2e.py`
(base temporal, contraseña y correos inventados), así prueban también la CSP, la
cookie, el CSRF y cómo se sirve `/app`. Usan `python3` (o `PYTHON`) con los
requisitos del backend instalados. Si no se puede descargar el Chromium de
Playwright, `PLAYWRIGHT_CHROMIUM=/ruta/al/chrome` usa otro ya instalado, y
`PUERTO_E2E=8161` cambia el puerto del servidor de pruebas (por defecto 8123).

Los datos de Inicio del servidor de pruebas son inventados y se fechan en el
mes actual y el anterior (las pruebas sirven cualquier mes); las cifras son las
del prototipo. Gmail es falso: no trae correos, y `GET /e2e/gmail/revocado` (solo
en ese servidor) hace que la siguiente sincronización falle como con el permiso
revocado; `GET /e2e/gmail/ok` lo deja como antes. Para Movimientos (ítem 14) hay
dos reglas inventadas y movimientos categorizados "por regla", "a mano" y sin
origen ("desconocido"); como esas pruebas categorizan y crean reglas,
`GET /e2e/datos/reiniciar` (solo en ese servidor) deja los datos como al arrancar.

**Categorías y reglas (ítem 15).** `/app/categorias` (`funcionalidades/categorias/categorias.tsx`,
lógica en `funcionalidades/categorias/`): hojas de gasto, de ingreso y de reglas; "Nueva
categoría" y "Editar" abren el mismo formulario (nombre, color e ícono como
radios nativos); "Borrar categoría" elige a qué categoría **de la misma clase**
pasan sus movimientos y reglas (`mover_a`). Los diálogos son `<dialog>` nativo
(`compartido/ui/ui/dialogo.tsx`). Color e ícono llegan de la API como claves
(`cat-*` y nombre de Lucide) y se traducen en `compartido/ui/categorias.ts`. En
Movimientos, cada movimiento solo ofrece las categorías de su
`clase_categoria` (un ingreso, las de ingreso; su regla es «Ingresos de …»).
En Inicio, el monto de los ingresos pendientes va en otra frase, nunca sumado
al de los gastos. Los datos de pruebas suman una categoría propia
("Mascotas") con su regla y un ingreso pendiente del mes anterior.
**Pulido (ítem 38).** Inicio sincroniza solo al abrir si el servidor lo pide
(`debe_sincronizar_al_abrir`, una vez por apertura: `useSincronizarAlAbrir`).
«Sin categorizar» muestra los pendientes iguales en grupos (`GrupoCategorizable`,
que el ítem 30 reutiliza para lo importado) y los categoriza con un toque,
con su regla. Borrar un ingreso a mano, una regla o una categoría sin
movimientos ni reglas es tocar y deshacer (`useDeshacer` + `AvisoDeshacer`); el
token del deshacer vive solo en memoria. Con el servidor de pruebas,
`GET /e2e/datos/sincronizacion-vieja` hace que el servidor pida sincronizar al
abrir y `GET /e2e/datos/grupos` agrega un grupo de 20 compras iguales pendientes;
`/e2e/datos/reiniciar` las quita. Las pruebas del aviso que desaparece usan el
reloj de Playwright (`page.clock`), no esperan los 30 segundos.

Con `PUERTO_E2E` las pruebas en navegador usan otro puerto (por si otra copia
del repositorio ya ocupa el 8123).

## Capturas

`npm run capturas` (compila antes con `npm run build`) genera **todas** las
capturas en `capturas/`: cada pantalla y estado en celular (390 px) y computador
(1280 px), claro y oscuro, con los datos inventados del servidor de pruebas.

En esta distribución ninguna captura se versiona: frontend/capturas/ y las
capturas históricas de prototipos están ignoradas. El CI corre las pruebas de
navegador, pero no publica un artefacto de capturas. Para una revisión visual,
genera las imágenes localmente y comprueba que solo contienen datos sintéticos.

## Decisiones técnicas

**Tokens: una sola fuente.** `src/app/estilos.css` importa `diseno/tokens.css` tal
cual y lo conecta a Tailwind con `@theme inline` (`bg-card`,
`text-muted-foreground`, `shadow-hoja`, `rounded-hoja`, `font-montos`…). Las
paletas, tamaños, sombras y cortes propios de Tailwind se borran
(`--color-*: initial`, etc.): una clase como `bg-red-500` no existe, así que no
se puede usar un color suelto por error. El espaciado sigue la escala de 4 px
de Tailwind (`p-4` = `--espacio-4`) y los espaciados con nombre se usan como
`p-(--espacio-hoja)`. El único corte es `computador:` (900 px, el de
`tokens.css`). Las fuentes las resuelve Vite desde `diseno/fuentes/` y salen
con hash en `/app/assets/` (autoalojadas).

**CSP estricta sin excepciones** (`script-src 'self'; style-src 'self'`, la de
la v1):
- Vite compila a `<script src>` y `<link rel=stylesheet>`, sin código en línea;
  `assetsInlineLimit: 0` evita URIs `data:` y no se usa el polyfill de
  `modulepreload`.
- La apariencia se aplica antes de pintar con `public/tema-inicial.js`, un
  archivo aparte (igual que `tema.js` del prototipo).
- La prop `style` de React escribe por CSSOM (`elemento.style`), que la CSP
  permite. Lo que no se permite son `<style>` en el HTML ni atributos `style`.
- **Diálogos: se usará `<dialog>` nativo** (ítems 15 y 16). El `Dialog`,
  `Select` modal, `Popover` y `DropdownMenu` de Radix usan
  `react-remove-scroll`, que inserta un `<style>` al abrirse y la CSP lo
  bloquea. `<dialog>` con `showModal()` ya trae foco atrapado, Escape y fondo
  inerte sin estilos inyectados. Para el selector, el `<select>` nativo (que
  SISTEMA.md ya recomienda en el celular).
- Las pruebas en navegador fallan ante cualquier violación de la CSP
  (evento `securitypolicyviolation` y consola).

**Navegación propia, sin el `Sidebar` de shadcn/ui.** El de shadcn arrastra
Sheet (Dialog), Tooltip y una cookie `sidebar_state`, y el modo plegable no
hace falta. La barra lateral y la inferior son componentes propios que copian
el prototipo (`app/navegacion/marco.tsx`). Los botones de Apariencia son botones
nativos con `aria-pressed` (como el prototipo), sin Radix.

**Sesión.** La cookie `sesion` es HttpOnly y del mismo dominio: el frontend no
la ve. El token CSRF está solo en memoria (`api/cliente.ts`); al recargar se
pide otra vez con `GET /api/sesion`. Todo lo que cambia datos lo manda en
`X-CSRF-Token` (el esquema OpenAPI lo declara obligatorio, así que TypeScript no
deja olvidarlo). Un 401 fuera del login lleva a "Entrar" con el aviso "Tu
sesión se cerró…". `localStorage` solo guarda `finanzas-tema` (y, desde el
ítem 13, `finanzas-grafico`): preferencias, nunca datos financieros. Cache
Storage solo guarda el cascarón estático (ver "Instalable en el celular").

**Instalable en el celular (ítem 18).** Cómo instalarla, en
[`deploy/GUIA.md`](../deploy/GUIA.md) (11.1).
- `public/manifest.webmanifest`: «Finanzas personales» / «Finanzas»,
  `start_url` y `scope` `/app/`, `display: standalone`, fondo y tema del papel
  claro (`--background`). `index.html` lo enlaza junto con el
  `apple-touch-icon` y las `meta` `apple-mobile-web-app-*` y `theme-color`
  (claro y oscuro). Todo son etiquetas `link`/`meta`: la CSP no cambia
  (`manifest-src` y `worker-src` heredan `default-src 'self'`).
- Íconos en `public/iconos/` (192, 512, 512 maskable y 180 de Apple), hechos
  con `pwa/generar-iconos.mjs` desde `diseno/favicon.svg` sobre el papel de
  `tokens.css`, con el Chromium de Playwright (sin dependencias nuevas). Se
  versionan; el build no los genera.
- **Service worker** (`src/pwa/`). Se registra en `/app/sw.js` con alcance
  `/app/` (`registrar.ts`, solo en producción). Chrome en Android lo ha
  exigido para ofrecer «Instalar app» (las versiones nuevas lo relajaron, pero
  no conviene depender de eso), y es lo que permite abrir sin conexión y decir
  "No hay conexión…" en vez de la página de error del navegador. `pwa/plugin-sw.ts` lo compila al final de `vite build`
  como script clásico, con la **lista cerrada** del cascarón (todo `dist/` y el
  índice como `/app/`) y una versión que es el hash de esos archivos.
  Reglas (`trabajador.ts`, con sus pruebas):
  - solo escribe en Cache Storage **al instalarse**, y solo esa lista, pedida
    **sin cookies** (`credentials: "omit"`); nada de lo que pasa por `fetch`
    se guarda;
  - `/api`, lo que no es GET, otros orígenes y la interfaz de la v1 no los
    toca: van directo a la red (la API además responde `no-store`);
  - abrir una pantalla va primero a la red; sin conexión recibe el índice
    guardado (HTML vacío), la app no puede leer `/api/sesion` y muestra
    "No hay conexión…", sin datos;
  - al activarse una versión nueva borra las cachés anteriores, y al cerrar
    sesión (o perderla) la página le pide borrar todo lo que no sea el
    cascarón actual.
  `e2e/pwa.spec.ts` comprueba en Chromium que el manifest es válido y
  instalable para Chrome, que `/api` nunca llega del service worker ni queda en
  Cache Storage, la limpieza al cerrar sesión y la pantalla sin conexión.

**Tipos.** Nunca se escriben a mano las formas de la API: salen de
`src/api/esquema.d.ts` (`components["schemas"][…]`). El CI falla si ese
archivo no coincide con `openapi/openapi.json`.

**Montos, fechas y horas.** Llegan en centavos enteros y solo se convierten a
pesos al mostrarlos, con `pesos()` de `src/compartido/formatos/formato.ts` (TEXTOS.md,
"Montos"): sin pasar por decimales, sin `,00` y con el menos tipográfico. Las
fechas de la API son hora de Colombia sin zona y se leen como texto (la zona
del navegador no las mueve); "hoy" y el mes actual se calculan en
`America/Bogota`. Números y horas no usan `Intl`, cuya salida cambia con la
versión de ICU del navegador.

**Inicio (ítem 13).** Los totales, el gasto por categoría, los porcentajes, los
ingresos y los pendientes vienen hechos de la API; las pruebas actuales de
Inicio validan los resultados contra los datos inventados de la API. El mes va
en la dirección (`/app/?mes=2026-08`). El gráfico "¿En qué se fue?" es SVG y
clases propias, sin librería: el largo de cada barra es una de las 101 clases
`w-[0%]`…`w-[100%]` que genera `@source inline` en `estilos.css` (la CSP no
deja poner el ancho en línea), y las tajadas de la dona son `path` con el `d`
calculado. El color e ícono de cada categoría salen de las claves de la API
(desde el ítem 15 los manda la API; ver abajo); una clave desconocida se pinta
como "Otros".

**Movimientos (ítem 14).** El mes y los filtros van en la dirección
(`/app/movimientos?mes=2026-08&ver=sin-categorizar`, `&categoria=5`) y filtra la
API (`tipo`, `categoria_id`, `sin_categoria`); "Sin categorizar" y una categoría
no se combinan. Se leen a la vez el reporte (selector de mes y número de
pendientes), las categorías, el mes completo y, si hay filtro, la lista
filtrada: el mes completo da el "Gastado" de cada día (la API no lo trae; se
suman enteros en centavos). "Sin categorizar" es **una sola bandeja, de todos
los meses** (`GET /api/movimientos/sin-categorizar`, sin mes ni "Gastado"); su
"(N)" es el mismo número de Inicio. Qué es pendiente, qué se puede categorizar
y qué regla se podría crear lo dice la API (`pendiente`, `categorizable`,
`regla_posible`): el frontend no lo decide. Cambiar de filtro no pasa por
"Cargando…" ni mueve el foco al título. En la bandeja cada pendiente ya muestra
sus categorías (un toque); en la lista, el primero. Tras categorizar, la fila
se queda a la vista (aunque en la bandeja ya no sea pendiente) con el aviso y el
botón de la regla, que repite la llamada con `recordar: true`. Al corregir uno
categorizado por regla no se ofrece la regla (cambiaría la de todos). Los
botones de fila son nativos; el selector de categoría es el `<select>` nativo
(`compartido/ui/ui/selector.tsx`).

**Configurar saldo (ítem 16).** `/app/saldo/configurar`
(`funcionalidades/saldo/configurar-saldo.tsx`, lógica en `funcionalidades/saldo/datos.ts`): saldo inicial
y fecha de inicio con `PUT /api/saldo/configuracion` (con CSRF). El monto pasa
a centavos como texto (`leerSaldoInicial`, sin floats; $0 vale) y la fecha se
compara con el `hoy` de la API (Colombia). «Configurar saldo» de «Empieza por
tu saldo» (Inicio y Saldo) lleva aquí, ya no a la v1. Si queda fija (solo
lectura, con «Ajustar el saldo») lo dice `configuracion_fija` de
`GET /api/saldo`, la misma regla con la que el PUT rechaza; nunca se deduce
del desglose. Si el PUT responde 400 o 409, la pantalla vuelve a leer: si
entró un movimiento, pasa a fija; si no, el error sale bajo el botón. En las
pruebas, `GET /e2e/datos/sin-saldo` borra movimientos y configuración y
`GET /e2e/datos/movimiento-anterior` deja una compra anterior a la fecha de
inicio (las dos idempotentes).

## Dependencias

Van al navegador (unos 92 KB de JS comprimido en total, 6 KB de CSS):

| Paquete | Para qué |
|---|---|
| `react`, `react-dom` 19.3.0 | La base (D16). |
| `wouter` 3.12.0 | Enrutador de ~2 KB, con base `/app`; alcanza para las secciones. |
| `openapi-fetch` 0.17.0 | `fetch` tipado con `esquema.d.ts` (~2 KB, del autor de openapi-typescript). |
| `@radix-ui/react-slot` 1.3.3 | `asChild` del botón de shadcn/ui (un enlace con aspecto de botón). |
| `class-variance-authority`, `clsx`, `tailwind-merge` | Variantes y `cn()` de shadcn/ui. |
| `lucide-react` 1.49.0 | Íconos (los del sprite del prototipo); solo viajan los importados. |

Solo desarrollo: `vite`, `@vitejs/plugin-react`, `tailwindcss` y
`@tailwindcss/vite`, `typescript` **5.9.3** (openapi-typescript 7.13 exige 5.x),
`openapi-typescript` 7.13.0, `vitest`, `jsdom`, Testing Library,
`@playwright/test`, `@axe-core/playwright` y los `@types`. El lock incluye los
binarios de linux-x64 y linux-arm64 (rolldown, lightningcss, oxide de
Tailwind), y ningún paquete tiene scripts de instalación, por eso
`npm ci --ignore-scripts` basta en el CI y en la VM.

## Importación del banco (ítem 30)

`src/funcionalidades/importaciones/` implementa la elección del Excel, vista previa, diagnóstico al
rechazarla, detalle, categorización y diferencias. Los conteos, consecuencias,
sugerencias, reglas propuestas, disponibilidad de deshacer, recordatorio y estado
«Preguntas resueltas» llegan del servidor, mediante los tipos OpenAPI generados. Un
conflicto 409 vuelve a analizar el archivo y exige confirmar la nueva vista previa;
un análisis vencido exige reanalizar. El último Excel solo permanece en memoria
mientras está abierta la pantalla y se elimina al terminar o perder la sesión.

El manifest habilita Compartir → Finanzas en Android instalado. El service worker
recibe un único `.xlsx` de hasta 2 MiB en RAM (máximo 64 KiB extra para multipart),
lo liga al `resultingClientId` de la navegación y lo entrega una sola vez a esa
ventana autenticada. Vence a los 15 minutos; cerrar sesión o perderla lo elimina.
El original nunca pasa por Cache Storage, localStorage, IndexedDB ni el servidor
antes de autenticar. El servidor valida de nuevo el tamaño y el formato real.
La prueba de navegación POST reproduce el transporte en Chromium; la integración
del menú Compartir requiere validar también un Android real con la PWA instalada.

`/e2e/datos/importacion` prepara datos inventados para los flujos reales. El Excel
se genera en memoria con Python, sin subir archivos bancarios a Git. Después de
compilar, `CAPTURAS_30=1 npm run e2e -- importacion.spec.ts` genera las capturas
`v3-30-*` de diecisiete estados en 390/1280 px y claro/oscuro (68 imágenes). Incluyen
preguntas reales del mismo día con ingreso y ajuste negativo, y dos candidatos
indistinguibles con sus etiquetas recibidas del servidor, un candidato manual
rotulado por su origen y confirmaciones exactas de Gmail y de un ingreso a mano
con cero agregados y un confirmado en vista previa, detalle e Inicio. Cada combinación
comprueba contraste y accesibilidad con axe, y áreas táctiles visibles de al menos
44 × 44 px; los controles recortados exclusivos del teclado no son objetivos
táctiles. Las pruebas también vigilan CSP. La preferencia operativa del dueño
es cinco repeticiones para casos nuevos o tocados; veinte solo si una
intermitencia reproducida lo justifica.

## Arranque e historial (ítem 31)

`src/funcionalidades/arranque/` usa `/api/arranque` y los tipos generados. La entrada en Inicio,
los permisos de arranque y extensión, la cobertura, los cálculos y la posibilidad
de deshacer llegan del servidor. Los nombres de archivos elegidos solo viven en
memoria; el contenido se envía al elegirlo y no se conserva en la pantalla.
La categorización reutiliza el ítem 30 y vuelve al resultado del arranque.

`CAPTURAS_31=1 npm run e2e -- arranque.spec.ts` genera doce capturas de entrada,
cálculo y resultado en celular/computador, claro/oscuro. Esos recorridos reales
verifican archivos solapados, saldo preservado al extender, retorno desde
categorización, deshacer, axe y CSP; los Excel se generan por código en memoria.

## Revisiones en Inicio (ítem 38)

La línea de estado consulta `GET /api/inicio/estado`. El texto «Todo al día» o
«N cosas por revisar», el total, las áreas y sus enlaces salen del servidor.
La pantalla no suma movimientos ni agrega una acción extra por una importación
pendiente. El desglose se abre en la misma línea usando los controles existentes.

Durante la consulta o una sincronización se retira el estado anterior. Al terminar
la sincronización manual o automática se consulta de nuevo, también si hubo un
error. Volver a Inicio después de importar, categorizar o deshacer carga el estado
vigente; las consultas retrasadas se descartan. Un error nunca muestra «Todo al
día» como respaldo y ofrece «Volver a consultar las revisiones».

`estado.test.tsx` comprueba texto y destinos del contrato, carga, error, reintento
y cancelación de una respuesta anterior. `estado-inicio.spec.ts` recorre esos
estados y una sincronización real con datos inventados, axe y CSP. Con
`CAPTURAS_38=1` genera las cuatro capturas clave `02-inicio-*`, en 390/1280 px,
claro y oscuro.

## Comprobar el saldo observado

Saldo, las vistas previas, el resultado y las preguntas permiten escribir el saldo
que se ve ahora en Bancolombia y llamar a `POST /api/saldo/comprobar`, con cookie y
CSRF. La hora es la recepción en el servidor, no una consulta al banco. La pantalla
presenta la diferencia firmada banco menos app, el impacto de la importación,
el resto sin explicar, el desglose y los pendientes recibidos en OpenAPI; no
recalcula ni crea un ajuste. «Ajustar el saldo» sigue siendo una acción separada.

El diagnóstico solo vive en memoria y se invalida al editar el monto, cambiar
el análisis o actualizar el historial (incluidas respuestas y deshacer). Tras
confirmar se comprueba el estado actual sin reutilizar el token del preview.
La extensión acepta un saldo observado opcional que no modifica el cálculo del
saldo inicial; el arranque inicial usa el saldo escrito como referencia única,
por lo que su coincidencia no es una verificación independiente. Una coincidencia
tampoco garantiza cobertura: los pendientes y las advertencias siguen visibles.

`comprobar-saldo.spec.ts` verifica la diferencia de un centavo sin ajustar,
invalidación y separación entre preview y estado actual. Con
`CAPTURAS_COMPROBACION=1` produce las cuatro capturas clave `11-saldo-*` (390/1280,
claro/oscuro), con datos inventados y axe. Los casos de unidad incluyen errores
de red, sin configuración y conflictos o vencimiento del análisis.

## Descartar y restaurar movimientos automáticos

Movimientos permite descartar y consultar los descartados de todos los meses en
la misma ruta. Los permisos y sus motivos llegan del servidor. Cada acción exige
confirmar el monto actual mostrado; el resultado presenta los saldos exactos del
servidor y recarga la lista. Una respuesta tardía no publica su resultado en otro
filtro. Recibir otra vez el aviso o importar el archivo no restaura un descarte:
se necesita restaurarlo explícitamente, si el servidor lo permite.

Las preguntas muestran la marca y la nota de descarte recibidas del servidor;
responder no restaura el candidato. `CAPTURAS_DESCARTES=1 npm run e2e --
descartes.spec.ts` verifica confirmaciones, recargas, CSRF, CSP y axe, y genera las
cuatro capturas clave `12-descartados-*` con datos inventados.
