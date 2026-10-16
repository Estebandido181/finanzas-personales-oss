> Las referencias a capturas históricas describen el desarrollo privado; esas imágenes no se distribuyen en este snapshot. El código y los tokens se conservan.

# Sistema de diseño "libreta de cuentas" (v2)

Dirección D28 (que actualiza D18) de `docs/especificacion.md`, con el estilo **«Libro mayor, noche petróleo»** (variante D, elegida por el dueño tras ver el ítem 12: «se ve muy minimalista, parece una presentación de PowerPoint… la idea es que sea vintage, retro, soft»):

- **Claro:** páginas de un libro mayor antiguo. Papel envejecido con grano, hojas que se separan del fondo por el tono y una sombra difusa (no por un borde de tinta), doble raya roja en el margen, doble raya bajo los títulos y renglones.
- **Oscuro:** verde petróleo con texto color papel y botón principal mostaza.
- Serif caligráfica de libro en títulos (Alegreya), sans humanista en textos (Alegreya Sans), letra de máquina de escribir **solo en montos** (Courier Prime). Esquinas poco redondeadas; colores de categoría apagados con ícono propio.

**Especificación vigente:** D28 actualizó D18 y formalizó este estilo; no está pendiente de aprobación. Las variantes que se compararon, con sus capturas, están en la rama de la exploración (`frontend/diseno/variantes/`).

Esta carpeta es la **fuente única** del sistema. El ítem 12 la importa tal cual; ninguna pantalla define colores, medidas ni tipos de letra por su cuenta.

| Archivo | Qué es |
|---|---|
| `tokens.css` | Variables de color (claro y oscuro), tipografía, espaciado, radios, bordes, sombras de papel, textura y colores de categoría. Declara las fuentes. |
| `fuentes/` | Las fuentes en `woff2` (subconjunto latino, solo los pesos usados) y sus licencias OFL. |
| `texturas/` | Grano de papel: dos SVG de menos de 1 KB (motas de tinta en claro, motas claras en oscuro), con ruido que genera el navegador (`feTurbulence`). |
| `iconos/iconos.svg` | Sprite con los íconos de Lucide que usa el prototipo, y su licencia ISC. |
| `favicon.svg` | Favicon: una hoja de libreta (margen rojo y renglones). Se adapta al modo oscuro. |
| `medir_contraste.py` | Mide los contrastes de `tokens.css` y genera las tablas de este documento. Falla si algún par no cumple. |
| `TEXTOS.md` | Guía de textos: tono, botones, ayudas, estados vacíos, errores, montos y fechas. |
| `prototipo/` | Prototipo aprobado en el ítem 11 (estructura, textos y flujos de todas las pantallas): páginas HTML con datos inventados, `componentes.css`, `tema.js` y `capturas/`. **Es histórico:** conserva su sombra sólida desplazada (medidas propias en `componentes.css`) y sus bordes de tinta, aunque toma colores y letras del `tokens.css` actual. La referencia visual vigente son las capturas de la app en `frontend/capturas/` y este documento. |

## Principios

1. **La libreta manda.** Cada pantalla es una o varias hojas de libro mayor sobre papel. **Papel sobre papel:** la hoja se separa del fondo por el tono y una sombra difusa, nunca por un borde de tinta ni una sombra sólida. Las filas se separan con renglones; bajo el título de una hoja va una doble raya fina; los totales llevan raya simple arriba y **doble abajo**, como en contabilidad. Como pide la D28, los únicos adornos son los de un libro de cuentas (doble raya roja del margen, doble raya bajo los títulos, renglones) y la única textura es el grano tenue del papel.
2. **La tinta es la acción.** El botón principal es tinta sepia en claro y mostaza apagada en oscuro, relleno plano. Nunca un bloque blanco sobre fondo oscuro.
3. **El color de una categoría nunca va solo.** Siempre acompaña a su ícono y a su nombre. Los textos se escriben con los colores de texto, nunca con el color de la categoría.
4. **Los montos se leen como en una libreta.** Letra de máquina de escribir, alineados a la derecha y sin partirse en dos líneas.
5. **Nada se mueve solo.** Solo hay movimiento como respuesta a una acción (el botón se hunde 1 px en el papel al presionarlo).

## Paleta

Valores exactos en `tokens.css`. Los nombres son los de shadcn/ui para que el ítem 12 los conecte a Tailwind sin traducir (`@theme inline { --color-background: var(--background); … }`).

| Token | Claro | Oscuro | Para qué |
|---|---|---|---|
| `background` | `#E6DAC0` papel envejecido | `#182422` petróleo | Fondo de la página (con grano) |
| `foreground` | `#33241A` tinta café | `#F0E8D8` papel | Texto normal |
| `card` | `#F5EDDB` hoja | `#22312E` petróleo claro | Hojas, campos, barra inferior |
| `muted` / `secondary` | `#EADFC8` | `#2C3D39` | Fondos apagados; botón secundario y segmentos |
| `accent` | `#E9DDC4` | `#2B3B38` | "Pasar el cursor" |
| `muted-foreground` | `#655041` | `#BCC3B5` | Texto secundario: ayudas, detalles, nombres de cifras |
| `primary` / `primary-foreground` | `#4A3223` / `#F5EDDB` | `#D2A24C` / `#182422` | Botón principal (tinta sepia; mostaza en oscuro) |
| `destructive` | `#983224` | `#F0A08C` | Tinta roja: borrar, errores, montos que restan |
| `border` | `#6E5846` | `#9FAA9C` | Rayas de total y de día (reglas de contabilidad); ya no es el borde de las hojas |
| `input` | `#7C6654` | `#8E9A8C` | Borde de campos y selectores (se conserva: sin él un campo no se reconoce) |
| `ring` | `#2F5F8A` | `#9CC3E6` | Anillo de foco (tinta azul, distinto de todo lo demás) |
| `regla` | `#CFC3A6` | `#34463F` | Doble raya bajo el título de una hoja (decorativa) |
| `renglon` | `#C7D0CB` | `#33483F` | Renglones entre filas, divisiones del resumen (decorativos) |
| `margen-libro` | `#C98E7E` | `#8A4C3E` | Doble raya roja del margen de cada hoja (decorativa) |
| `borde-hoja` | tinta al 10 % | papel al 7 % | Canto apenas visible de la hoja |
| `borde-suave` | `foreground` al 20 % | `foreground` al 20 % | Canto de botones secundarios y segmentos |
| `sombra-hoja` / `sombra-boton` / `sombra-campo` / `sombra-barra` | — | — | Sombras de papel (ver "Radios, bordes y sombra") |
| `textura` | `texturas/grano-tinta.svg` | `texturas/grano-papel.svg` | Grano del papel |
| `velo` | tinta al 55 % | negro al 60 % | Fondo detrás de un diálogo |
| `exito` / `advertencia` | `#3C5A2E` / `#7A5500` | `#A3CB92` / `#E6BE5A` | Íconos de éxito y advertencia |
| `aviso-*-fondo` | error `#F2D9CD`, advertencia `#F2E1B0`, éxito `#E3E6CC`, info `#DDE3E0` | `#43291F`, `#3A3319`, `#253624`, `#1D3136` | Fondo de los avisos |
| `monto-positivo` / `monto-negativo` | `#3C5A2E` / `#983224` | `#A3CB92` / `#F0A08C` | Ingresos y ajustes a favor / ajustes en contra |
| `sidebar*` | `#DDD0B3` … | `#131D1B` … | Barra lateral (computador) |

**Por qué verde petróleo en oscuro y no cuero:** el dueño eligió la noche de la variante C (petróleo con mostaza) sobre el cuero. Al combinarla con las hojas de A se ajustaron: la sombra de las hojas, la raya del margen a un óxido más claro (sobre petróleo el rojo oscuro se veía marrón sucio), los renglones a un petróleo claro y el dorado viejo a mostaza.

**Los gastos van en tinta normal**, no en rojo: son lo habitual y pintarlos todos de rojo sería ruido. El rojo se reserva para borrar, errores y ajustes que restan.

### Contrastes medidos

Calculados con la fórmula de WCAG 2.x por `python3 frontend/diseno/medir_contraste.py`, que lee `tokens.css` (no son estimaciones). Si cambias un color, vuelve a correrlo y pega aquí la salida.

#### Textos (mínimo 4,50:1)

| Uso | Primer plano / fondo | Claro | Oscuro |
|---|---|---|---|
| Texto normal sobre el fondo | `foreground` / `background` | 10,76:1 ✓ | 13,12:1 ✓ |
| Texto normal sobre una hoja | `foreground` / `card` | 12,80:1 ✓ | 11,15:1 ✓ |
| Texto sobre fondo apagado | `foreground` / `muted` | 11,28:1 ✓ | 9,40:1 ✓ |
| Texto secundario (ayudas, detalles) | `muted-foreground` / `background` | 5,46:1 ✓ | 8,83:1 ✓ |
| Texto secundario sobre una hoja | `muted-foreground` / `card` | 6,49:1 ✓ | 7,51:1 ✓ |
| Texto secundario sobre fondo apagado | `muted-foreground` / `muted` | 5,72:1 ✓ | 6,33:1 ✓ |
| Botón principal | `primary-foreground` / `primary` | 10,17:1 ✓ | 6,86:1 ✓ |
| Botón de borrar | `destructive-foreground` / `destructive` | 6,40:1 ✓ | 7,69:1 ✓ |
| Texto de error y botón Borrar sin borde | `destructive` / `card` | 6,40:1 ✓ | 6,54:1 ✓ |
| Error sobre el fondo | `destructive` / `background` | 5,38:1 ✓ | 7,69:1 ✓ |
| Monto que suma (ingresos) | `monto-positivo` / `card` | 6,69:1 ✓ | 7,44:1 ✓ |
| Monto que resta (ajustes) | `monto-negativo` / `card` | 6,40:1 ✓ | 6,54:1 ✓ |
| Texto de un aviso de error | `foreground` / `aviso-error-fondo` | 11,07:1 ✓ | 10,94:1 ✓ |
| Ícono y título de error dentro del aviso | `destructive` / `aviso-error-fondo` | 5,53:1 ✓ | 6,42:1 ✓ |
| Texto del aviso de pendientes | `foreground` / `aviso-advertencia-fondo` | 11,49:1 ✓ | 10,34:1 ✓ |
| Detalle en una fila pendiente | `muted-foreground` / `aviso-advertencia-fondo` | 5,82:1 ✓ | 6,96:1 ✓ |
| Texto de un aviso de éxito | `foreground` / `aviso-exito-fondo` | 11,69:1 ✓ | 10,56:1 ✓ |
| Texto de un aviso informativo | `foreground` / `aviso-info-fondo` | 11,46:1 ✓ | 11,16:1 ✓ |
| Texto de la barra lateral | `sidebar-foreground` / `sidebar` | 9,76:1 ✓ | 14,14:1 ✓ |
| Texto secundario en la barra lateral | `muted-foreground` / `sidebar` | 4,95:1 ✓ | 9,52:1 ✓ |
| Barra lateral al pasar el cursor | `sidebar-foreground` / `sidebar-accent` | 8,67:1 ✓ | 11,15:1 ✓ |
| Botón al pasar el cursor | `foreground` / `accent` | 11,08:1 ✓ | 9,66:1 ✓ |
| Monto que suma sobre el papel | `monto-positivo` / `background` | 5,63:1 ✓ | 8,76:1 ✓ |
| Monto que resta sobre el papel | `monto-negativo` / `background` | 5,38:1 ✓ | 7,69:1 ✓ |
| Texto secundario dentro de un aviso de error | `muted-foreground` / `aviso-error-fondo` | 5,61:1 ✓ | 7,37:1 ✓ |

#### Elementos de interfaz (mínimo 3,00:1)

| Uso | Primer plano / fondo | Claro | Oscuro |
|---|---|---|---|
| Borde de hojas y botones | `border` / `background` | 4,81:1 ✓ | 6,62:1 ✓ |
| Borde de botones sobre una hoja | `border` / `card` | 5,73:1 ✓ | 5,63:1 ✓ |
| Borde de campos y selectores | `input` / `card` | 4,64:1 ✓ | 4,62:1 ✓ |
| Borde de campos sobre el fondo | `input` / `background` | 3,90:1 ✓ | 5,44:1 ✓ |
| Anillo de foco sobre una hoja | `ring` / `card` | 5,77:1 ✓ | 7,35:1 ✓ |
| Anillo de foco sobre el fondo | `ring` / `background` | 4,85:1 ✓ | 8,65:1 ✓ |
| Ícono de éxito | `exito` / `aviso-exito-fondo` | 6,11:1 ✓ | 7,06:1 ✓ |
| Borde punteado de «Sin categorizar» | `cat-sin-categorizar` / `card` | 3,62:1 ✓ | 8,47:1 ✓ |
| Anillo de foco en la barra lateral | `ring` / `sidebar` | 4,40:1 ✓ | 9,32:1 ✓ |
| Anillo de foco sobre un botón secundario | `ring` / `secondary` | 5,08:1 ✓ | 6,20:1 ✓ |
| Anillo de foco dentro de un aviso de error | `ring` / `aviso-error-fondo` | 4,99:1 ✓ | 7,21:1 ✓ |
| Anillo de foco dentro del aviso de pendientes | `ring` / `aviso-advertencia-fondo` | 5,18:1 ✓ | 6,81:1 ✓ |
| Borde de campos sobre fondo apagado | `input` / `secondary` | 4,09:1 ✓ | 3,90:1 ✓ |

#### Categorías (mínimo 3,00:1 contra el fondo y la hoja; el ícono del chip usa `cat-icono`)

| Categoría | Claro | vs. fondo | vs. hoja | Oscuro | vs. fondo | vs. hoja |
|---|---|---|---|---|---|---|
| Mercado | `#5A6B1C` | 4,26:1 | 5,07:1 | `#A7B874` | 7,42:1 | 6,30:1 |
| Restaurantes | `#9E5234` | 4,08:1 | 4,86:1 | `#D98C72` | 6,04:1 | 5,14:1 |
| Transporte | `#4F7896` | 3,40:1 | 4,04:1 | `#A3C4E0` | 8,77:1 | 7,45:1 |
| Vivienda y servicios | `#15605A` | 5,31:1 | 6,32:1 | `#6FB3AA` | 6,62:1 | 5,63:1 |
| Salud | `#6E2833` | 7,52:1 | 8,95:1 | `#D0848B` | 5,60:1 | 4,76:1 |
| Entretenimiento | `#664468` | 5,85:1 | 6,95:1 | `#A87BAE` | 4,65:1 | 3,95:1 |
| Compras | `#8F6E12` | 3,44:1 | 4,09:1 | `#E5C57E` | 9,60:1 | 8,16:1 |
| Antojos | `#A5647E` | 3,21:1 | 3,81:1 | `#E6B3C3` | 8,83:1 | 7,50:1 |
| Otros | `#666E7A` | 3,72:1 | 4,42:1 | `#98A6B6` | 6,44:1 | 5,47:1 |
| Sueldo | `#2E5B3A` | 5,67:1 | 6,74:1 | `#6AA37C` | 5,43:1 | 4,62:1 |
| Préstamos | `#4A5690` | 5,01:1 | 5,96:1 | `#A3AEE0` | 7,37:1 | 6,26:1 |
| Otros ingresos | `#8C6A3A` | 3,58:1 | 4,25:1 | `#E0BC7E` | 8,87:1 | 7,54:1 |
| Sin categorizar | `#7E7B74` | 3,05:1 | 3,62:1 | `#CFCCC6` | 9,97:1 | 8,47:1 |

Todos los pares cumplen.

Las categorías del modo claro mostaza, azul, rosa y gris se oscurecieron un poco respecto del prototipo, para mantener 3:1 sobre el papel envejecido (más oscuro). Las del oscuro vienen de la variante C y se midieron contra el petróleo.

## Categorías: color e ícono

Cada categoría tiene siempre el mismo color y el mismo ícono, en todas las pantallas y meses. Los íconos son de Lucide (ver "Íconos").

| Categoría | Clase | Color de época | Nivel de luminosidad | Ícono (Lucide) |
|---|---|---|---|---|
| Mercado | gasto | oliva | medio | `shopping-basket` |
| Restaurantes | gasto | óxido | medio | `utensils` |
| Transporte | gasto | azul desteñido | claro | `bus` |
| Vivienda y servicios | gasto | verde azulado | oscuro | `house` |
| Salud | gasto | vino | oscuro | `heart-pulse` |
| Entretenimiento | gasto | ciruela | oscuro | `ticket` |
| Compras | gasto | mostaza | claro | `shopping-bag` |
| Antojos | gasto | rosa viejo | claro | `ice-cream-cone` |
| Otros | gasto | pizarra | medio | `shapes` |
| Sueldo | ingreso | verde botella | oscuro | `briefcase` |
| Préstamos | ingreso | índigo desteñido | medio | `handshake` |
| Otros ingresos | ingreso | bronce | claro | `coins` |
| Sin categorizar | — | gris, **hueco con borde punteado** | — | `circle-dashed` |

**Distinguirse también por luminosidad.** Los colores de la misma familia de tono están en niveles distintos: vino (oscuro) / óxido (medio) / rosa viejo (claro); verde azulado (oscuro) / oliva (medio) / mostaza (claro); ciruela (oscuro) / pizarra (medio) / azul desteñido (claro). El modo oscuro conserva el mismo orden (el vino sigue siendo el más oscuro de su familia).

**Lo que no se puede lograr, dicho con honestidad.** Con 10 colores de gasto *apagados* (poca saturación, por pedido de D18) no existe una paleta en la que todos los pares se distingan con daltonismo rojo-verde. Lo medí con el validador de la skill de visualización (OKLab, simulación Machado 2009, todos los pares): la peor pareja de gasto es ciruela/verde azulado en claro (ΔE 2,4 con deuteranopía; la meta es 8) y óxido/oliva en oscuro (ΔE 3,7); con visión normal la peor es pizarra/azul desteñido en claro (ΔE 7,5; la meta es 15). Las tres de ingreso sí pasan en ambos modos. Por eso el sistema **no confía la identidad al color**:

- El chip siempre lleva ícono, y el nombre de la categoría siempre está escrito al lado o en la misma fila.
- El gráfico por defecto es **una barra por fila** junto a su nombre, monto y porcentaje. La vista en dona (que el dueño puede elegir) no tiene leyenda aparte: su leyenda es esa misma lista, y cada tajada va separada de la vecina por un filo del color de la hoja (ver "Gráfico").
- "Sin categorizar" no es un gris más: es un cuadro **hueco con borde punteado** y su barra también es punteada.

**Categorías nuevas** (aprobado por el dueño). Al crear una categoría se elige un color de esta misma paleta (se puede repetir un color, nunca el par color + ícono) y un ícono de una lista corta de Lucide.

## Tipografía

Las tres familias tienen licencia **SIL Open Font License 1.1** (se pueden usar, incrustar y servir desde el propio servidor). Están en `fuentes/` con sus licencias (archivos `woff2` tomados de los paquetes `@fontsource`); nada se carga desde un CDN de fuentes, por privacidad y porque la CSP de la app es estricta. Solo se incluyen los pesos que se usan.

| Rol | Fuente | Por qué | Archivo |
|---|---|---|---|
| Títulos | **Alegreya** 700 (Huerta Tipográfica) | Serif caligráfica de libro, de contraste moderado: cálida y "blanda", como la rotulación de un libro de cuentas. Reemplaza a la Bodoni, cuyo alto contraste se veía de presentación. | `alegreya-latin-700-normal.woff2` (24 KB) |
| Textos | **Alegreya Sans** 400, 500 y 700 (Huerta Tipográfica) | Sans humanista, pareja de la Alegreya: el texto y los títulos se sienten de la misma familia. Su ojo es pequeño, por eso el texto va a 17 px. | `alegreya-sans-latin-400/500/700-normal.woff2` (24 KB c/u) |
| Montos | **Courier Prime** (400 y 700) | Máquina de escribir hecha para leerse en pantalla, sin el aspecto gastado de las fuentes "vintage" con textura. Monoespaciada: los montos quedan alineados en columna. | `courier-prime-400/700-latin.woff2` (19 KB c/u) |

Total: unos 134 KB (antes 118 KB), con `font-display: swap`.

**Reglas de uso**

- La letra de máquina de escribir es **solo para montos**: en filas, totales, campos de monto, dentro de una frase ("Suman $27.700") y dentro del texto de una regla. **Nunca** en títulos, botones, fechas, horas, porcentajes ni textos (D18).
- Títulos de pantalla (h1), de sección (h2) y de hoja (h3) en Alegreya, peso 700. Todo lo demás en Alegreya Sans.
- Sin mayúsculas sostenidas para etiquetas: los títulos van en tipo oración ("Últimos movimientos"). Las descripciones de Bancolombia se muestran tal como llegan (a veces en mayúsculas).

**Escala** (razón ~1,25; ningún texto baja de 15 px)

| Token | Tamaño | Uso |
|---|---|---|
| `--texto-sm` | 15 px | Ayudas, detalles de fila, porcentajes (Alegreya Sans a 15 px se lee como otra sans a 14) |
| `--texto-base` | 17 px | Texto, botones, campos |
| `--texto-lg` | 18 px | h3; montos en campos |
| `--texto-xl` | 22 px | h2; montos medianos |
| `--texto-2xl` | 28 px | h1 en el celular |
| `--texto-3xl` | 36 px | h1 en el computador |
| `--texto-monto-grande` | 28–40 px (`clamp`) | Gasto del mes y saldo |

Interlineado: 1,15 en títulos, 1,5 en textos, 1,2 en montos.

## Espaciado: que la app respire

Pedido del dueño al aprobar el prototipo: que no se vea todo cerrado ni amontonado. La regla de fondo es **proximidad**: el espacio entre bloques siempre es mayor que el espacio dentro de un bloque, así se ve qué va junto sin agregar bordes ni adornos. Las pantallas usan estos tokens con nombre (en `tokens.css`), no la escala suelta.

| Token | Celular | Computador | Dónde |
|---|---|---|---|
| `--espacio-pagina` | 20 px | 48 px | Margen lateral de la página |
| `--espacio-bloques` | 32 px | 40 px | Entre hojas, avisos y secciones de una pantalla; entre días en Movimientos; entre columnas de la rejilla |
| `--espacio-hoja` | 20 px | 32 px | Relleno interior de una hoja |
| `--espacio-cabeza-hoja` | 20 px | 24 px | Del título de la hoja a su contenido |
| `--espacio-grupo` | 28 px | 32 px | Entre grupos dentro de una hoja (aviso y formulario, lista y nota, cifra y desglose) |
| `--espacio-fila` | 16 px | 16 px | Arriba y abajo de cada fila de libreta (movimientos, reglas, categorías) |
| `--espacio-fila-grafico` | 12 px | 12 px | Filas del gráfico (son 10 o más y se leen como tabla) |
| `--espacio-texto` | 8 px | 8 px | Título → ayuda, etiqueta → campo, nombre → cifra |

Antes (prototipo aprobado): página 16 px, bloques 24 px, hoja 16/24 px, filas 12 px.

**Menos cosas por hoja** (mismo pedido):

- **Inicio:** "Últimos movimientos" muestra 4 filas (antes 6); el resto está a un toque en "Ver todos los movimientos".
- **Movimientos:** cada día es **su propia hoja** (antes todos los días iban en una sola hoja larga), separada de la siguiente por `--espacio-bloques`.
- **Saldo:** el desglose va plegado; la nota sobre qué se puede borrar pasa al pie de la lista.
- **Categorías y reglas:** tres hojas ("Categorías de gasto", "Categorías de ingreso", "Reglas") en vez de una con subtítulos.
- La última fila de una hoja no suma su relleno al de la hoja (quedaba un hueco al pie).

## Radios, bordes y sombra

- **Espaciado base:** múltiplos de 4 px (`--espacio-1` = 4 px … `--espacio-16` = 64 px), solo para detalles internos de un componente; entre bloques se usan los tokens con nombre de arriba.
- **Radios:** 4 px en hojas, botones, campos y diálogos (`--radius`); 2 px en chips; 1 px en barras del gráfico.
- **Hojas: papel sobre papel.** Sin borde de tinta ni sombra sólida desplazada (lo que el dueño sintió "pegado", como de presentación). La hoja se separa por el tono (`card` sobre `background`), un canto casi invisible (`borde-hoja`) y `sombra-hoja`, una sombra difusa. **Pendiente de aprobación (D28):** el prototipo D mostraba además dos páginas que asoman debajo de cada hoja (tono sobre tono). Queda aislada en el token `--sombra-hoja-paginas`, sin usar; si el dueño la aprueba, basta con apuntar `--shadow-hoja` a ella en `src/estilos.css`. Lleva grano (`textura`) y la doble raya roja del margen (`margen-libro`), dibujadas con la utilidad `hoja-libro` de `src/estilos.css` (solo CSS, sin estilos en línea).
- **Botones:** canto suave (`borde-suave`) y `sombra-boton` (luz arriba, sombra difusa corta). El prototipo D daba al principal un leve brillo "estampado" (degradado); se quitó por la D28 (adorno no previsto) y queda pendiente de que el dueño lo apruebe.
- **Campos:** conservan el borde `input` (≥ 3:1) y llevan `sombra-campo`, una sombra interior leve: se ven hundidos en el papel.
- **Reglas de contabilidad:** las rayas de total, de día y el subrayado doble siguen en `border`: dan información, no son el borde de una caja.
- **Textura:** el fondo de la página, las hojas, la barra inferior y la pestaña actual llevan el grano. Son SVG locales (la CSP `img-src 'self'` los permite).
- **Foco:** 2 px `ring`.

## Navegación

- **Celular (< 900 px): barra inferior** (aprobada por el dueño) fija de 64 px con ícono y texto: Inicio, Movimientos, Saldo, Categorías, Más. La sección actual se marca con texto en negrita y una raya gruesa de tinta arriba (no depende del color). "Más" lleva a Correos no reconocidos, Apariencia y Cerrar sesión.
- **Computador (≥ 900 px): barra lateral** de 248 px con la marca, las cinco secciones (Inicio, Movimientos, Saldo, Categorías y reglas, No reconocidos con su contador), Apariencia y Cerrar sesión. La sección actual es una "pestaña": hoja con grano y `sombra-boton`, sin borde.
- **Selector de mes:** botón "‹ Agosto" antes del título del mes. **En el mes actual no hay "mes siguiente"**; en un mes pasado aparece "Octubre ›" a la derecha. El mes más antiguo es el de la fecha de inicio.
- **Favicon:** `favicon.svg` (hoja de libreta). El ítem 18 (PWA) generará a partir de él los PNG de 192 y 512 px y el ícono de Apple.

## Componentes base y cómo se adaptan de shadcn/ui

La referencia visual de cada uno está en `prototipo/componentes.css`. En el ítem 12 se instalan los componentes de shadcn/ui y se ajustan sus clases a estos tokens; no se crean estilos sueltos.

| Componente | En shadcn/ui | Adaptación |
|---|---|---|
| **Botón** | `Button` | Variantes: `default` → principal (tinta sepia; mostaza en oscuro), `outline` → secundario (relleno `secondary` tono sobre tono), `destructive` → borrar (tinta roja), `ghost` → quieto (sin borde ni sombra, para "Cambiar", "Editar", "Borrar" dentro de una fila). Todos: alto mínimo 44 px, radio 4 px, canto `borde-suave` y `sombra-boton` (salvo `ghost`); al presionar se hunde 1 px y pierde la sombra. Texto en negrita 16 px, ícono de 20 px a la izquierda si ayuda. Se quita la variante `link`: los enlaces sueltos usan la clase `enlace` (44 px de alto). |
| **Hoja (tarjeta)** | `Card` | Fondo `card` con grano y doble raya roja del margen, canto `borde-hoja`, radio 4 px, `sombra-hoja` (papel sobre papel). La cabecera de una hoja con título lleva una doble raya fina `regla` debajo. Sin `CardDescription` gris claro: la ayuda usa `muted-foreground`. |
| **Campo** | `Input` + `Label` | Alto 44 px, borde `input`, fondo `card`, `sombra-campo`, foco con borde y anillo `ring`. Etiqueta siempre visible arriba (nunca solo placeholder). Campos de monto en Courier Prime, `inputmode="decimal"`. Error: borde 2 px `destructive`, `aria-invalid` y mensaje con ícono debajo, unido con `aria-describedby`. |
| **Selector** | `Select` (o `select` nativo en el celular) | Mismo aspecto que un campo, flecha de tinta. En el celular se recomienda el nativo: abre la rueda del sistema, que es más cómoda. |
| **Grupo de opciones** | `ToggleGroup` | "Segmentos" de 44 px sobre `secondary` con canto suave: la opción elegida va en `primary` con `sombra-boton` (`aria-pressed="true"`). Filtros de movimientos y Apariencia. |
| **Barra lateral** | `Sidebar` | Fondo `sidebar`, borde derecho `sidebar-border` (suave); elemento actual como pestaña (hoja con grano + `sombra-boton`). El contenido queda fijo al hacer scroll. |
| **Barra inferior** | — (no existe en shadcn) | Componente propio: `nav` fija sobre `card` con grano, canto `borde-hoja` arriba y `sombra-barra` (difusa, hacia arriba), 5 elementos, ícono de 22 px sobre texto de 15 px, `aria-current="page"` en el actual, respeta `safe-area-inset-bottom`. |
| **Diálogo** | `Dialog` en computador, `Drawer` (hoja inferior) en el celular | Título en Alegreya, `sombra-hoja`, texto que explica la consecuencia, botones: acción a la derecha (computador) o arriba a todo el ancho (celular), "Cancelar" siempre presente. Velo `velo`. |
| **Aviso** | `Alert` | Ícono + título en negrita + texto + acciones. Variantes por fondo: `aviso-error-fondo`, `aviso-advertencia-fondo`, `aviso-exito-fondo`, `aviso-info-fondo`; el texto siempre en `foreground`. Sin borde. El aviso importante (sincronización fallida) lleva `sombra-hoja`. Los resultados de una acción se muestran como aviso cerca de donde se hizo (`role="status"`), no como notificación flotante que desaparece. |
| **Aviso de deshacer** (`AvisoDeshacer`) | — (hecho con `AvisoConTitulo`) | Aviso de éxito en la misma pantalla, justo donde se borró algo, con el botón 'Deshacer'. Desaparece solo cuando se acaba el plazo que manda el servidor (`deshacer.segundos`, mínimo 10 s); la cuenta se pausa mientras tenga el foco o el cursor encima. Se anuncia con `role="status"` (error: `role="alert"`), recibe el foco al aparecer y, al expirar, devuelve el foco al título de la pantalla. Solo hay uno a la vez: un borrado nuevo reemplaza al anterior. Nunca se usa para confirmar acciones que no se pueden deshacer. Textos: ver TEXTOS.md > deshacer. |
| **Chip de categoría** | — (componente propio, parecido a `Badge`) | Cuadro de 32 px (24 px en listas densas) con el color de la categoría y su ícono en `cat-icono`, seguido del nombre. "Sin categorizar": cuadro hueco con borde punteado. |
| **Botón de categoría** | `Button` variante propia | Para "categorizar en un toque": chip de 28 px + nombre de 15 px, 44 px de alto, en rejilla de 2 columnas en el celular y 5 en el computador. |
| **Fila de movimiento** | — (componente propio) | Chip · descripción (y monto a la derecha) · tipo y hora · cómo se categorizó ("Transporte, por regla: transferencia de $3.200" o "Salud, a mano") con el botón "Cambiar" en la misma línea. Pendiente: fondo `aviso-advertencia-fondo` y botón "Categorizar" o las opciones desplegadas. |
| **Encabezado de día** | — | Cada día es una hoja. Arriba, fecha en negrita a la izquierda y "Gastado: $X" a la derecha, raya de tinta debajo. |
| **Total** | — | Raya simple arriba y subrayado doble bajo el monto. |
| **Estado vacío** | — | Ícono de 40 px, título en Alegreya, una frase que dice qué pasa y qué hacer, y un botón si hay algo que hacer. |
| **Vista del gráfico** | `ToggleGroup` (tipo `single`) | "Ver como" + segmentos "Barras" y "Dona" de 44 px (mínimo 104 px de ancho), con ícono y texto; el elegido en tinta llena, `aria-pressed`. Ver "Gráfico". |
| **Desglose plegable** | `Collapsible` (o `<details>` nativo) | Botón "Ver cómo se calcula" de 44 px con flecha `chevron-down` que gira 180° al abrir; debajo, filas nombre/monto y total con subrayado doble. Plegado por defecto. |

### Gráfico "¿En qué se fue?"

El dueño **elige cómo verlo**: barras (por defecto) o dona. Las dos vistas usan los mismos colores e íconos de categoría y la misma lista.

**Selector "Ver como".** Debajo del título de la hoja: la etiqueta "Ver como" y dos segmentos, "Barras" (ícono `chart-bar-decreasing`) y "Dona" (ícono `chart-pie`), de 44 px de alto. El elegido va en tinta llena y lleva `aria-pressed="true"`; el grupo se llama "Ver como". La elección **se recuerda en el dispositivo** (`localStorage`, clave `finanzas-grafico`, igual que la apariencia: no es un dato financiero ni se guarda en el servidor, así cada dispositivo puede tener la suya) y se aplica con `data-grafico` en `<html>` antes de pintar, para que no "salte" de una vista a otra al cargar.

**Barras (por defecto).** Una fila por categoría, de mayor a menor: chip + nombre, barra horizontal del color de la categoría (largo proporcional a la mayor), porcentaje y monto. Al final, "Total gastado" con subrayado doble.

- Por qué es la vista por defecto: se comparan largos (más preciso que ángulos) y cada barra está pegada a su nombre, así el color no carga con la identidad, que es lo que exige una paleta apagada.

**Dona.** Anillo de 240 px de ancho como máximo (grosor 32 de 240 unidades), empezando a las 12 y en sentido del reloj, en el mismo orden de la lista. En el centro, "Total gastado" y el monto. Debajo, la **misma lista** como leyenda, sin barras: en el celular, chip + nombre y monto en una línea y el porcentaje debajo del nombre (así cabe entero "Vivienda y servicios" en 390 px); en el computador, nombre, porcentaje y monto en columnas fijas.

- Cada tajada lleva un filo de 2 px del color de la hoja: separa tajadas vecinas aunque sus colores se parezcan.
- "Sin categorizar" es una tajada **hueca con borde punteado**, igual que su chip y su barra.
- Tajadas pequeñas: con 1,5 % la tajada mide unos 10 px en el borde exterior; se ve, pero no se lee sin la lista, por eso la lista va siempre.
- En el prototipo la dona es un SVG con arcos calculados (`d` de cada `path`). En el ítem 12 se puede dibujar igual con SVG propio (recomendado: una dependencia menos) o con Recharts (`PieChart` con `innerRadius`), que la especificación permite; en ese caso se desactivan su leyenda y su tooltip, porque la lista ya cumple esa función.

**Accesibilidad (las dos vistas).** La lista es un `ul` llamado "Gasto por categoría en septiembre"; cada fila se lee como "Mercado, $486.249,50, 26,4 %". El dibujo (barras o anillo) es decorativo para el lector de pantalla. Cambiar de vista no cambia lo que se lee.

## Íconos

**Lucide** (licencia ISC, la que usa shadcn/ui). En el ítem 12 se usa el paquete `lucide-react` (cada ícono se importa por separado, así solo viajan los que se usan). El prototipo usa `iconos/iconos.svg`, un sprite con los mismos íconos, copiado de `lucide-static` 1.49.0.

- Trazo de 1,75 px (algo más fino que el 2 por defecto, más cercano a una pluma), extremos redondeados, 20 px en botones y filas, 22 px en la barra inferior, 16–18 px dentro de chips.
- Siempre `aria-hidden` cuando hay texto al lado; si un ícono va solo, lleva nombre accesible.

| Uso | Ícono |
|---|---|
| Inicio / Movimientos / Saldo / Categorías y reglas / No reconocidos / Más | `book-open` / `arrow-left-right` / `wallet` / `tags` / `mail-question-mark` / `ellipsis` |
| Sincronizar ahora | `refresh-cw` |
| Sincronización correcta / fallida | `circle-check` / `triangle-alert` |
| Mes anterior / siguiente | `chevron-left` / `chevron-right` |
| Vista del gráfico: Barras / Dona | `chart-bar-decreasing` / `chart-pie` |
| Abrir o cerrar el desglose | `chevron-down` |
| Cambiar, Editar / Borrar / Nueva categoría, Registrar ingreso | `pencil` / `trash-2` / `plus` |
| Categorizado por regla / a mano | `tags` / `pencil` |
| Ingreso manual / Ajuste / Ajustar saldo | `hand-coins` / `scale` / `scale` |
| Información / Guardado | `info` / `check` |
| Apariencia: Sistema / Claro / Oscuro | `monitor` / `sun` / `moon` |
| Cerrar sesión | `log-out` |

## Áreas táctiles

Todo lo que se toca mide al menos **44 × 44 px** (`--tactil-min`): botones, segmentos, campos, selectores, elementos de las barras, botones de categoría, "Cambiar", "Editar", "Borrar" y los enlaces sueltos (clase `enlace`). Entre botones sueltos hay 8 px o más; en la navegación y en los tres botones de Apariencia de la barra lateral quedan más juntos (0–4 px), pero cada uno mide 44 px o más. Lo medí en las 10 páginas del prototipo (12 estados, contando la dona y el desglose abierto) a 390 y 1280 px, en claro y oscuro: ningún elemento queda por debajo de 44 px.

## Modo claro y oscuro

- Por defecto sigue al sistema (`prefers-color-scheme`). En "Apariencia" se elige Sistema, Claro u Oscuro; se guarda en `localStorage` (no es un dato financiero) y se aplica con `data-tema` en `<html>` antes de pintar, para evitar el destello.
- El modo oscuro no es una inversión automática: cada color se eligió y midió contra el verde petróleo. El grano del oscuro son motas claras muy tenues (`grano-papel.svg`).

## Movimiento

Solo en respuesta a una acción: el botón se hunde 1 px (120 ms); los diálogos pueden aparecer con un fundido corto. Nada se anima al cargar. Con `prefers-reduced-motion: reduce` no hay transiciones.

## Accesibilidad del prototipo (resultado)

- **axe-core 4.13** (reglas WCAG 2.0/2.1/2.2 A y AA y buenas prácticas), inyectado en el navegador sin agregarlo al repositorio: **0 violaciones** en los 12 estados del prototipo (las 10 páginas, más Inicio con la dona y Saldo con el desglose abierto), a 390 y 1280 px, en claro y en oscuro (48 revisiones; última pasada con los ajustes del dueño). Quedan casos "incompletos" de contraste que axe no puede decidir solo: el texto de la barra inferior (por el seudoelemento de la raya), el selector (su flecha es un degradado), el texto bajo el velo del diálogo y el texto del centro de la dona (queda sobre el hueco del anillo, que es la hoja). En todos los colores son tokens ya medidos arriba (`foreground` y `muted-foreground` sobre `card`).
- Los ajustes del dueño no cambiaron ningún color; `medir_contraste.py` sigue dando "Todos los pares cumplen". Las tajadas de la dona usan los colores de categoría, que ya miden ≥ 3:1 contra la hoja (tabla de arriba).
- Foco visible en todo (anillo `ring` de 2 px), navegación por teclado en orden de lectura, `aria-current` en la navegación, `aria-pressed` en los segmentos, `role="alert"` en el error de sincronización, `role="status"` en los resultados.

## Cómo ver el prototipo

Las páginas cargan los íconos desde un archivo aparte, así que conviene servirlas (no abrirlas con doble clic):

```
cd frontend/diseno && python3 -m http.server 8000
# y abrir http://localhost:8000/prototipo/
```

Con `?captura` en la dirección, la barra inferior se dibuja al pie de la página (solo sirve para las capturas de página completa; no pasa al frontend). Las capturas están en `prototipo/capturas/`: `NN-pantalla-{celular|computador}-{claro|oscuro}.png`. Con los ajustes del dueño se agregaron `02b-inicio-grafico-dona-*` (la vista en dona) y `05b-saldo-desglose-abierto-*` (el desglose abierto; en `05-saldo-*` está plegado, que es como se ve al entrar). En el computador, con `?captura` la barra lateral deja de ser fija para no quedar a mitad de una captura de página completa.

En el prototipo los campos de fecha se ven en el formato del navegador de las capturas (inglés); en un celular en español se ven en formato local.

## Decisiones del dueño sobre el prototipo

El dueño aprobó el prototipo del ítem 11 con estos ajustes (ya aplicados en esta carpeta):

1. **Gráfico:** puede **elegir** entre barras y dona; barras por defecto; la elección se recuerda por dispositivo (ver "Gráfico").
2. **Centavos:** se ocultan cuando son `,00` (`$486.250`) y se muestran cuando no (`$486.250,50`) (ver `TEXTOS.md`, "Montos").
3. **Hora:** 12 horas ("7:40 a. m."), como ya estaba.
4. **Barra inferior del celular:** aprobada (Inicio, Movimientos, Saldo, Categorías, Más). Pidió que la app "respire": más aire, menos cosas por hoja y jerarquía clara (ver "Espaciado: que la app respire").
5. **Desglose del saldo:** visible pero **plegado** por defecto.
6. **Permiso de Gmail revocado:** sin cambios; la app explica qué pasó y manda a la guía.
7. **Categorías nuevas:** aprobado (color de la paleta e ícono de una lista corta).
8. **Dirección vintage:** aprobada tal cual.
9. **Estilo «Libro mayor, noche petróleo»** (después del ítem 12, al ver la app en su celular): el dueño pidió cambiar la letra e integrar mejor "los tableros blancos" (hojas y botones con borde de tinta y sombra dura). Entre tres variantes eligió la A (libro mayor) en claro con el oscuro de la C (petróleo y mostaza), y la confirmó. Aplicada en tokens, fuentes y componentes; ver arriba. La decisión D28 formaliza esta actualización de D18.

## Preguntas abiertas

1. **¿Autorizar Gmail desde la app?** Hoy, si el permiso de Gmail se vence o se revoca, la app solo puede explicar qué pasó y enviar a la guía de despliegue (paso 8), porque volver a autorizar se hace en el servidor. Autorizarlo desde la propia app (un botón "Autorizar Gmail" que abra el consentimiento de Google) sería una función nueva, con su propio análisis de seguridad. **Propuesta:** anotarla como sugerencia en la sección "Sugerencias" del roadmap para que el dueño decida si entra en una versión futura. No se diseña ni se construye hasta entonces.
2. **Archivos de fuentes en el repositorio** (unos 134 KB en `fuentes/`, licencia OFL): siguen versionados para no depender de un CDN. Sin respuesta explícita del dueño; se asume que sí al aprobar el prototipo.
