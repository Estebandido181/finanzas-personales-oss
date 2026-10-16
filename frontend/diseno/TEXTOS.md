> Las referencias a capturas históricas describen el desarrollo privado; esas imágenes no se distribuyen en este snapshot. El código y los tokens se conservan.

# Guía de textos (v2)

Cómo habla la app. La regla de fondo (especificación, "Alcance de la versión 2", punto 2): **cada botón dice lo que hace, hay ayudas cortas donde algo no es obvio y cada pantalla vacía explica qué hacer.** Todos los ejemplos usan datos inventados.

## Tono

- **Español de Colombia, de tú**, claro y directo: "Categoriza", "Escribe", "Vuelve a autorizar".
- **Frases cortas y verbos simples.** Una idea por frase. Sin tecnicismos: "permiso de Gmail", no "token OAuth"; "correo que la app no supo leer", no "parser".
- **Sin disculpas ni exclamaciones.** Un error no dice "¡Ups!" ni "Lo sentimos": dice qué pasó y qué hacer. Un éxito no celebra: confirma.
- **Tipo oración** en títulos, botones y etiquetas: "Últimos movimientos", no "Últimos Movimientos" ni "ÚLTIMOS MOVIMIENTOS".
- **Comillas:** una sola regla, en la sección «Comillas» (más abajo). En resumen: «…» (latinas) dentro de la app; "…" (rectas) solo en este documento, para mostrar un texto de la app.

## Vocabulario fijo

Una cosa, un nombre, en toda la app. Si un botón dice "Borrar ingreso", el aviso que sigue dice "Ingreso borrado".

| Se dice | No se dice | Qué es |
|---|---|---|
| movimiento | transacción, operación | Cualquier compra, transferencia, ingreso o ajuste |
| compra, transferencia, ingreso, ajuste | débito, crédito, egreso | Los cuatro tipos de movimiento |
| gasto | egreso, débito | Compras y transferencias (lo que cuenta en "Gastado") |
| categoría | etiqueta, rubro | Mercado, Transporte, Sueldo… |
| sin categorizar | pendiente, sin clasificar | Movimiento sin categoría |
| regla | automatización, filtro | Condiciones que categorizan solos los movimientos nuevos |
| a mano / por regla | manual / automático | Cómo se categorizó un movimiento |
| sincronizar | actualizar, importar, refrescar | Traer los avisos nuevos de Gmail |
| correo no reconocido | error de lectura, fallido | Aviso que la app no supo leer o que no pasó la verificación |
| saldo | balance | Lo que hay en la cuenta según la app |
| ajuste de saldo | corrección, cuadre | Diferencia entre el saldo real y el calculado |
| comercio, destino, quien envía | contraparte, beneficiario | El otro lado del movimiento |

## Comillas

Una sola regla para citar textos (ítem 38; solo ordena cómo se escribe, no cambia lo que hace la app):

- **Dentro de la app, siempre comillas latinas «…»**, nunca rectas ni inglesas, y solo en dos casos:
  1. **El nombre de un botón o de una opción citado dentro de una frase:** "toca «Sincronizar ahora», arriba"; "aparecen como «Sin categorizar» en el gráfico".
  2. **El texto que viene de los datos del dueño dentro de la frase de una regla** (comercio, destino o quien envía): "Si es una compra en «SUPERMERCADO LA ESPIGA», va a Mercado"; "Si es un ingreso de «CARLOS RUIZ EJEMPLO» por $400.000, va a Préstamos". El texto va tal como llega del banco (en mayúsculas si así llegó), aunque la API lo guarde normalizado.
- **El monto de una regla va fuera de las comillas**, en la letra de los montos y sin comillas: «CARLOS RUIZ EJEMPLO» por $400.000; transferencia de $3.200. Entre comillas va el texto, nunca el monto.
- **Sin comillas** cuando el texto del dueño ya es un botón o la parte de un aviso que lo muestra en su propia línea: "Compras en PANADERIA EL TRIGAL" (botón de regla), "Regla creada: compras en PANADERIA EL TRIGAL van a Mercado.", el nombre de un movimiento en una fila, "Categorizar las 20 de COBRO VIAJE TRANSPORTE MASIVO" (nombre para lectores de pantalla).
- **En este documento**, los textos de la app que se muestran como ejemplo van entre comillas rectas "…" para separarlos de la explicación. Las latinas «…» solo aparecen cuando la app las lleva dentro del texto.

## Botones: dicen lo que hacen

- **Verbo + objeto** cuando el verbo solo no basta: "Registrar ingreso", "Ajustar saldo", "Borrar regla", "Crear regla", "Volver a procesar todos".
- **Nunca** "Aceptar", "Enviar", "OK", "Sí", "Continuar" ni "Guardar" a secas cuando hay algo más preciso.
- En una confirmación, el botón repite la consecuencia: "Borrar y pasar a Otros", no "Confirmar". El otro botón es siempre "Cancelar".
- Un solo botón principal (tinta) por hoja. Las acciones de fila son quietas ("Cambiar", "Editar", "Borrar") y llevan, para lectores de pantalla, el objeto: "Cambiar categoría de PANADERIA EL TRIGAL".
- Si el botón dispara algo que tarda, cambia su texto mientras dura: "Sincronizando…", y queda deshabilitado.

## Ayudas cortas

Solo donde algo no es obvio, en una o dos frases, **debajo del título o del campo** (nunca solo en un placeholder, que desaparece al escribir).

| Dónde | Ayuda |
|---|---|
| Gasto del mes | "Compras y transferencias. Los ingresos y los ajustes de saldo no cuentan como gasto." |
| Campo de monto | "Punto para los miles y coma para los centavos." |
| Registrar un ingreso | "Para dinero que entra sin aviso de Bancolombia, como efectivo. Los ingresos con aviso entran solos: no los registres aquí." |
| Ajustar el saldo | "Escribe el saldo que ves en Bancolombia. La diferencia se guarda como un ajuste (cuota de manejo, 4x1000 y otros cobros sin aviso) y no cuenta como gasto." |
| Antes de ajustar | "Sincroniza antes de ajustar: si el banco ya descontó una compra que la app todavía no trajo, se restaría dos veces." |
| Borrar ingresos | "Solo se puede borrar un ingreso registrado a mano y posterior al último ajuste. Los ajustes y lo que llega de Gmail no se borran." |
| Reglas | "Una regla categoriza sola los movimientos nuevos que cumplen todas sus condiciones. Si dos reglas coinciden, gana la más específica. Se crean al categorizar un movimiento." |
| No reconocidos | "Avisos de Bancolombia que la app no supo leer o que no pasaron la verificación de autenticidad. No crean movimientos. Después de corregir el lector, vuelve a procesarlos." |
| Configurar saldo inicial | "El saldo inicial es el que tenías al comenzar el día de la fecha de inicio (a las 00:00): los movimientos de ese día sí cuentan. Una vez haya movimientos ya no se puede cambiar." |
| Apariencia | "«Sistema» sigue el modo claro u oscuro de tu celular." |

## Estados vacíos: qué pasa y qué hacer

Título corto que dice qué pasa + una frase con lo que se puede hacer + un botón si hay una acción.

| Pantalla | Título | Texto | Botón |
|---|---|---|---|
| Inicio, sin saldo configurado | Empieza por tu saldo | Escribe el saldo de tu cuenta y la fecha desde la que la app lleva las cuentas. Solo se leen los avisos desde esa fecha. | Configurar saldo |
| Inicio, mes sin movimientos | Sin movimientos en octubre | Todavía no hay compras, transferencias ni ingresos este mes. Si acabas de pagar algo, sincroniza para traerlo. | Sincronizar ahora |
| Inicio, mes pasado sin movimientos | Sin movimientos en julio | No hubo compras, transferencias ni ingresos en julio. | — |
| "¿En qué se fue?" sin gastos | No hay gastos en octubre | — | — |
| Movimientos con filtro sin resultados | Nada con este filtro | No hay movimientos de Salud en septiembre. | Ver todos los movimientos |
| Movimientos con filtro "Gastos" o "Ingresos" sin resultados | Nada con este filtro | No hay gastos en julio. / No hay ingresos en julio. | Ver todos los movimientos |
| Filtro "Sin categorizar" vacío | Todo categorizado | Cada movimiento de septiembre tiene su categoría. | — |
| Reglas | Todavía no hay reglas | Se crean al categorizar un movimiento: después de elegir la categoría, toca una de las reglas que te propone la app. | Ir a Movimientos |
| Ingresos y ajustes del mes | Sin ingresos ni ajustes en septiembre | Los ingresos con aviso de Bancolombia aparecen solos; los demás se registran arriba. | — |
| No reconocidos | No hay correos sin reconocer | Todos los avisos de Bancolombia que llegaron se leyeron bien. Si un día aparece uno aquí, es porque su formato cambió o no pasó la verificación de autenticidad. | Volver al inicio |

## Errores: qué pasó y cómo arreglarlo

Formato: **qué pasó** (en términos del dueño) + **qué hacer**. Sin códigos ni nombres internos. El error de un campo va debajo del campo; el de una acción, en un aviso cerca del botón que la disparó; el que afecta a toda la app (sincronización), arriba del inicio.

| Situación | Texto |
|---|---|
| Contraseña vacía (al tocar «Entrar») | Escribe tu contraseña. |
| Contraseña incorrecta | Contraseña incorrecta. Revísala y vuelve a intentarlo. |
| Demasiados intentos | Demasiados intentos fallidos. Espera unos minutos y vuelve a intentarlo. |
| No se pudo entrar (falla del servidor, no de la contraseña) | No se pudo entrar. Vuelve a intentarlo en unos minutos. |
| No se pudo cerrar la sesión (falla del servidor) | No se pudo cerrar la sesión. Vuelve a intentarlo en unos minutos. |
| Sesión vencida | Tu sesión se cerró. Entra de nuevo para seguir. |
| Falla del servidor sin un texto propio para el caso (respaldo) | La app no pudo completar la acción. Vuelve a intentarlo en unos minutos. |
| Monto con letras u otros signos | Ese monto tiene una letra O en lugar de un cero. Escríbelo solo con números, por ejemplo 4.730.000. |
| Monto con formato no válido (general) | Escribe el monto en pesos, con punto para los miles y coma para los centavos, por ejemplo 1.234.567,89. |
| Monto vacío o en cero | Escribe un monto mayor que cero. |
| Fecha anterior a la de inicio | La fecha es anterior al 1 de septiembre de 2026, cuando empezaste a llevar las cuentas. Elige una fecha desde ese día. |
| Fecha de inicio futura | La fecha de inicio no puede ser futura. Elige hoy o un día anterior. |
| Saldo inicial vacío | Escribe el saldo inicial. Si empiezas en cero, escribe 0. |
| Fecha de inicio vacía | Elige la fecha de inicio. |
| Configurar saldo cuando ya hay movimientos (la API responde que no se puede) | No se puede cambiar: ya hay movimientos desde el 1 de septiembre de 2026. Si el saldo no coincide con el de Bancolombia, corrígelo con un ajuste de saldo. |
| Saldo real igual al calculado | Tu saldo ya coincide con el de Bancolombia: no se registró ningún ajuste. (aviso informativo, no de error) |
| Ingreso enviado dos veces | Este ingreso ya se registró. Revisa la lista antes de registrarlo otra vez. |
| Borrar un ingreso anterior al último ajuste | No se puede borrar: es anterior al último ajuste (20 de septiembre). Si fue un error, corrígelo con un ajuste de saldo. |
| Sincronización ya en curso | Ya hay una sincronización en curso. Espera a que termine. |
| Sincronización fallida sin causa clara | No se pudo sincronizar con Gmail. Vuelve a intentarlo en unos minutos; si se repite, revisa el registro del servidor (guía de despliegue, «Solución de problemas»). |
| Sin conexión | No hay conexión con la app. Revisa tu internet y vuelve a intentarlo. |
| Nombre de categoría repetido | Ya existe una categoría «Antojos». Usa otro nombre. |
| Regla que ya existe | Ya hay una regla igual: transferencias de $3.200 van a Transporte. |
| Algo que ya no existe (otra pestaña) | Ese movimiento ya no existe. Recarga la página. |
| Deshacer cuando venció o ya se usó (410) | Ya no se puede deshacer: pasó el tiempo o ya se deshizo. |
| Deshacer cuando algo cambió (409), con el motivo que manda la API | No se puede deshacer: ya hay una regla con esas mismas condiciones. (otros motivos: "…la categoría de la regla ya no existe", "…hay un ajuste posterior"; sin motivo: "No se puede deshacer: algo cambió mientras tanto.") |
| Categorizar un grupo cuando ya no estaba pendiente | Esos movimientos ya no estaban sin categorizar. No se cambió nada. |

Notas (decisiones del ítem 12):

- **Sin red al entrar o al cerrar sesión** no hay un texto propio: se usa el de "Sin conexión" ("No hay conexión con la app. Revisa tu internet y vuelve a intentarlo."). Así el dueño no cree que el problema es la contraseña.
- "Contraseña vacía" y "Contraseña incorrecta" van **debajo del campo**; "Demasiados intentos", "No se pudo entrar" y "Sin conexión", en un aviso **debajo del botón «Entrar»**. "No se pudo cerrar la sesión" va en un aviso debajo del botón «Cerrar sesión».
- Si al cerrar sesión resulta que la sesión ya se había cerrado por fuera, no se muestra error: la app vuelve a "Entrar" con el aviso "Tu sesión se cerró. Entra de nuevo para seguir."
- El texto de respaldo solo se usa cuando la API no manda un `detalle` ya escrito para el dueño ni hay un texto más preciso en esta tabla.

### Caso del ítem 13: sincronización fallida por permiso de Gmail revocado o vencido

Es el error más importante: si pasa, la app deja de traer movimientos y el reporte queda incompleto sin que se note. Se muestra **arriba del inicio**, con sombra, `role="alert"`, y el estado de sincronización del encabezado cambia a rojo. No desaparece hasta que una sincronización salga bien.

- **Estado en el encabezado:** "Falló la sincronización. Última correcta: 28 de septiembre, 12:00 p. m."
- **Título del aviso:** "No se pudo sincronizar con Gmail"
- **Qué pasó:** "Gmail rechazó el permiso de lectura de la app: se venció o se revocó. Desde el 28 de septiembre no entran movimientos nuevos, así que el reporte puede estar incompleto."
- **Qué hacer:** "Vuelve a autorizar Gmail con el paso 8 de la guía de despliegue («Gmail») y después toca «Sincronizar ahora», arriba."
- **Botón:** "Ver cómo autorizar Gmail" (abre la sección de la guía).
- Si la sincronización automática (cada 6 horas) falla, el aviso se muestra igual la próxima vez que se abra la app.
- **Nunca hubo una sincronización correcta:** estado "Falló la sincronización. Todavía no hay ninguna sincronización correcta."; en el aviso, en vez de "Desde el 28 de septiembre…": "Mientras no se arregle, no entran movimientos nuevos y el reporte puede estar incompleto."
- **Otras causas:** sin causa clara, el texto de "Sincronización fallida sin causa clara" (arriba); si falta configurar algo, el texto que manda la API. El botón "Ver cómo autorizar Gmail" solo aparece cuando Gmail rechazó el permiso.
- **Nunca se ha sincronizado:** estado "Todavía no se ha sincronizado."

(Ver `prototipo/capturas/03-inicio-error-sincronizacion-*.png`.)

## Confirmaciones y resultados

- **Confirmar solo lo que no se puede deshacer** (ítem 38): borrar una categoría que tiene movimientos o reglas (la API dice `se_puede_deshacer_borrado: false`). El diálogo dice qué pasa con lo que depende: "Antojos tiene 12 movimientos y 1 regla. Elige a qué categoría pasan; los movimientos no se borran."
- **Lo que se puede deshacer se hace al tocar y muestra «Deshacer»** unos segundos (ver «Deshacer», más abajo): borrar un ingreso a mano, borrar una regla y borrar una categoría sin movimientos ni reglas.
- **Resultado en pasado y con el mismo verbo del botón**: "Registrar ingreso" → "Ingreso de $150.000 registrado."; "Ajustar saldo" → "Saldo ajustado: se registró un ajuste de −$12.400."; "Borrar regla" → "Regla borrada. Los movimientos que ya categorizó conservan su categoría." (con «Deshacer»).
- **Sincronización correcta**: "Sincronización terminada: 4 movimientos nuevos." Si hubo algo más, se agrega solo lo que importa: "…y 1 correo no reconocido (ver No reconocidos)." Los duplicados no se mencionan: no son algo que el dueño deba atender.
  - Sin nada nuevo: "Sincronización terminada: no hay movimientos nuevos."
  - Con correos que no se pudieron leer: "Sincronización terminada: 4 movimientos nuevos y 2 correos que no se pudieron leer: se reintentan en la próxima sincronización." (en singular: "1 correo que no se pudo leer: se reintenta…").
  - Los correos rechazados por la verificación de autenticidad también quedan en No reconocidos: se cuentan junto con los no reconocidos.
- **Volver a procesar**: "Se volvieron a procesar 4 correos. 1 creó un movimiento nuevo; 3 siguen sin reconocerse." Si no se creó ninguno: "Ninguno creó un movimiento nuevo; 3 siguen sin reconocerse." (con 1 solo correo revisado: "No creó ningún movimiento nuevo; 1 sigue sin reconocerse.").

## Deshacer

Cada borrado reversible se hace al tocar, sin diálogo. El resultado es un aviso de éxito en la misma pantalla, cerca de donde se tocó (no una notificación flotante), con un botón «Deshacer». El servidor manda cuántos segundos dura (hoy, 30); pasado ese tiempo el aviso desaparece y lo borrado se queda borrado. El aviso recibe el foco al aparecer (el botón que se tocó ya no está) y, si desaparece con el foco dentro, el foco pasa al título de la pantalla.

| Se borra | Aviso al borrar | Al deshacer |
|---|---|---|
| Ingreso a mano (Saldo) | Ingreso borrado. El saldo bajó $150.000. | Ingreso restaurado. El saldo volvió a $4.739.150. |
| Regla (Categorías y reglas) | Regla borrada. Los movimientos que ya categorizó conservan su categoría. | Regla restaurada. |
| Categoría sin movimientos ni reglas | Categoría Préstamos borrada. | Categoría Préstamos restaurada. |

- **Botón:** «Deshacer» (mientras dura la petición: "Deshaciendo…", deshabilitado). Un solo aviso a la vez: si se borra otra cosa, el aviso nuevo reemplaza al anterior.
- **El saldo que se muestra al restaurar un ingreso lo manda la API**, no se calcula en la pantalla.
- **Si ya no se puede** (venció, ya se usó o algo cambió), el aviso pasa a error con el motivo; ver «Errores». Lo borrado no cambia.
- **Mientras se borra**, el botón de la fila dice "Borrando…" y no se puede tocar otra vez.
- **Si borrar no se puede** (409 o 404 de la API), el texto de la API va en el mismo lugar, como error, y la pantalla se vuelve a leer.
- El token del deshacer vive solo en la memoria de la pantalla: al salir de ella o recargar, ya no se puede deshacer.

## Montos en pesos colombianos

- Formato (decisión del dueño, ajuste al ítem 11): signo pegado al número, punto para los miles y coma para los centavos. **Los centavos se ocultan cuando son cero y se muestran completos cuando no:**
  - `$486.250` (486.250,00: sin centavos)
  - `$486.250,50` (siempre dos cifras de centavos: nunca `$486.250,5`)
  - `$0` para cero; `−$12.399,50` y `+$4.800.000` con signo.
- La regla se aplica a **cada monto por separado**, también en totales: un total puede no llevar centavos aunque alguno de sus sumandos sí (`$12.399,50` + `$6.000,50` = `$18.400`).
- En listas, los montos van alineados a la derecha. Cuando unos llevan centavos y otros no, las cifras de las unidades no quedan en la misma columna: es el costo aceptado de esta decisión (se lee más limpio y la mayoría de montos no tiene centavos).
- Los montos se guardan siempre en centavos (especificación): ocultar ",00" es solo cómo se muestran, nunca se redondea.
- Negativos con el signo menos tipográfico (−, U+2212) antes del signo de pesos: `−$12.400`. Ingresos y ajustes a favor con `+` cuando aparecen junto a gastos: `+$4.800.000`.
- Un monto nunca se parte en dos líneas y siempre va en la letra de máquina de escribir.
- Implementación: se parte del entero en centavos, sin pasar por decimales. Si `centavos % 100 === 0` se formatea con `minimumFractionDigits: 0, maximumFractionDigits: 0`; si no, con `2` y `2`. `Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", … })` pone un espacio tras el `$` (`$ 68.630`): hay que quitarlo (con `formatToParts` o armando el texto), porque en letra monoespaciada ese espacio se ve como un hueco grande. Para no perder precisión se le pasa el monto como texto (`"68630.50"`), no como número. Casos de prueba mínimos: `0` → `$0`, `5` → `$0,05`, `50` → `$0,50`, `4862500` → `$48.625`, `48625050` → `$486.250,50`, `-1239950` → `−$12.399,50`.
- En campos: se aceptan `1.234.567,89`, `1.234.567`, `1234567,89` y `1234567`; el ejemplo dentro del campo va sin centavos (`150.000`). Nunca se adivina: si hay letras o dos comas, se muestra el error del campo.

## Fechas y horas

- **Fecha en frase:** "29 de septiembre" (del año en curso) o "29 de septiembre de 2025" (de otro año). En encabezados de día: "Martes 29 de septiembre"; el día de hoy: "Hoy, miércoles 30 de septiembre"; el de ayer: "Ayer, martes 29 de septiembre".
- **Hora:** formato de 12 horas de Colombia, "7:40 a. m.", "9:28 p. m." (con espacio que no se parte). Es lo que da `Intl.DateTimeFormat("es-CO")`. Decidido con el dueño (ajuste al ítem 11): se queda en 12 horas.
- **Mes:** "Septiembre de 2026" en títulos (con mayúscula inicial); "septiembre" dentro de una frase ("Gastado en septiembre").
- **Estado de sincronización:** "Sincronizado hoy a las 6:02 a. m.", "Sincronizado ayer a las 11:30 p. m.", "Sincronizado el 27 de septiembre a las 6:00 a. m.".
- **Nunca** fechas numéricas tipo 29/09/26 en la interfaz: se prestan a confusión.

## Textos por pantalla

### Al abrir la app (ítem 12)
- **Cargando:** "Cargando…", solo si la app tarda más de unos 300 ms en saber si hay sesión; si responde antes, no se muestra nada (así no parpadea).
- **Error al abrir** (sin red, o el servidor falló con un 5xx): no se manda a "Entrar", porque haría creer que la contraseña es el problema. Se muestra una hoja con ícono (sin conexión o alerta), el texto del error ("No hay conexión con la app. Revisa tu internet y vuelve a intentarlo." o "La app no pudo completar la acción. Vuelve a intentarlo en unos minutos.") y el botón "Volver a intentar".
- Título de la pestaña del navegador: "Finanzas personales"; en cada pantalla, "{pantalla} · Finanzas personales" ("Entrar · Finanzas personales", "Saldo · Finanzas personales").

### Entrar
- Título: "Finanzas personales". Ayuda: "Tus cuentas del mes, al día y sin anotar nada a mano."
- Campo: "Contraseña". Botón: "Entrar" (mientras dura: "Entrando…").

### Navegación (ítem 12)
- Barra lateral (computador): la marca "Finanzas" y "Inicio", "Movimientos", "Saldo", "Categorías y reglas", "No reconocidos" (con contador); abajo, "Apariencia" y "Cerrar sesión".
- Barra inferior (celular): "Inicio", "Movimientos", "Saldo", "Categorías", "Más".
- Las dos se llaman "Secciones" para lectores de pantalla. Primer enlace de la página, visible solo con el teclado: "Saltar al contenido".
- "Cerrar sesión" (mientras dura: "Cerrando sesión…").

### Pantallas extra (ítem 12, aprobadas por el dueño)
- **Página que no existe:** título "Esta página no existe", texto "Revisa la dirección o vuelve al inicio.", botón "Volver al inicio".
- **Sin conexión** y **Cargando:** ver "Al abrir la app", arriba.

### Inicio (reporte del mes)
- Título: "Septiembre de 2026". Antes, "‹ Agosto"; en un mes pasado, además "Octubre ›" a la derecha. En el mes actual no hay mes siguiente.
- Estado: "Sincronizado hoy a las 6:02 a. m." + botón "Sincronizar ahora".
- **Sincronizar al abrir** (ítem 38): si el servidor dice que toca (la última sincronización tiene más de una hora), la app sincroniza sola al abrir, una sola vez por apertura: el botón dice "Sincronizando…" y, al terminar, el resultado de siempre ("Sincronización terminada: 3 movimientos nuevos."). Si falla, el aviso grande de siempre explica qué hacer y la app no reintenta sola; queda el botón. La pantalla no calcula la hora: decide el servidor.
- Aviso de pendientes: título "3 movimientos sin categorizar" (singular: "1 movimiento sin categorizar"), texto "Suman $27.700. Mientras no tengan categoría, aparecen como «Sin categorizar» en el gráfico.", botón "Categorizar ahora". Sin pendientes, el aviso no aparece.
  - Ítem 15: gastos e ingresos pendientes nunca se suman en una sola cifra; van en frases aparte. Solo gastos: "Suman $27.700. Mientras no tengan categoría…". Gastos e ingresos: "Los gastos suman $27.700. Mientras no tengan categoría, aparecen como «Sin categorizar» en el gráfico." y en otro párrafo "Aparte, los ingresos suman +$400.000.". Solo ingresos: "Los ingresos suman +$400.000." (cambio propuesto en la revisión del ítem 15 en lugar de "Son ingresos y suman", que con un solo pendiente queda en plural).
- Cifras: "Gastado en septiembre", "Saldo actual", "Ingresos de septiembre".
- Hojas: "¿En qué se fue?" (enlace "Ver movimientos"; pie "Total gastado") y "Últimos movimientos" (4 filas y botón "Ver todos los movimientos").
- Fila de "Últimos movimientos": descripción, "<Categoría> · 7:40 a. m." y el monto. Sin categoría: "Sin categorizar · …" (gastos), "Ingreso · …" o "Ajuste · …". Ingresos con "+" en verde y ajustes con su signo ("−$18.400" en rojo, con el menos tipográfico).
- Vista del gráfico: etiqueta "Ver como" y dos botones, "Barras" (por defecto) y "Dona". El que está elegido se ve en tinta llena. En la dona, el centro dice "Total gastado" y el monto; debajo va la misma lista de categorías (nombre, porcentaje y monto) como leyenda. No hace falta un aviso al cambiar: el cambio se ve de inmediato y se recuerda en el dispositivo.

### Movimientos
- Título: "Movimientos", con el selector de mes.
- Filtros: "Todos", "Gastos", "Ingresos", "Sin categorizar (2)"; selector "Categoría" con "Todas las categorías".
- Encabezado de día: "Martes 29 de septiembre" y "Gastado: $183.850".
- Fila: descripción tal como llega; "Transferencia · 7:12 a. m."; cómo se categorizó: "Transporte, por regla: transferencia de $3.200", "Salud, a mano" o "Sin categorizar".
- Categorizar en un toque: "¿En qué categoría va? Toca una:" y un botón por categoría (de gasto para compras y transferencias, de ingreso para ingresos).
- Crear la regla en el mismo paso: "Guardado en Restaurantes. ¿Categorizar igual las siguientes? Crea una regla con un toque:" con botones que dicen la regla completa: "Transferencias a LAURA GÓMEZ EJEMPLO", "Transferencias de $6.200", "Las dos cosas juntas". Para compras: "Compras en PANADERIA EL TRIGAL". Para ingresos: "Ingresos de EMPRESA EJEMPLO S.A.S.". Al crearla: "Regla creada: transferencias de $6.200 van a Restaurantes."
- Corregir: botón "Cambiar". Al cambiar uno categorizado por regla: "Cambiado a Antojos. Ahora está categorizado a mano; la regla sigue igual para los demás."
  - Al tocar "Cambiar" se abren las mismas opciones ("¿En qué categoría va? Toca una:") y un botón "Cancelar" que las cierra sin cambiar nada. Las filas sin categorizar no lo llevan.
  - Al corregir uno categorizado por regla no se ofrece crear otra regla: la que existe sigue igual para los demás (para cambiarla, en "Categorías y reglas").
- **Grupos en «Sin categorizar»** (ítem 38): los pendientes iguales (2 o más) salen juntos en una hoja arriba de los sueltos, que siguen como siempre. Hoja: título "Movimientos que se repiten", ayuda "Son iguales entre sí. Categorízalos juntos con un toque y la app guarda la regla para los siguientes." Fila del grupo: descripción ("COBRO VIAJE TRANSPORTE MASIVO"), "Compra · 20 veces", la suma ("$64.000"; ingresos con "+" en verde) y el botón "Categorizar las 20" (para lectores de pantalla, "Categorizar las 20 de COBRO VIAJE TRANSPORTE MASIVO"). Al tocarlo: "¿En qué categoría van las 20? Toca una:", la ayuda "Se categorizan juntos y se guarda la regla: compras en COBRO VIAJE TRANSPORTE MASIVO van a la categoría que elijas." y un botón por categoría de la clase del grupo (gasto o ingreso) más "Cancelar". Resultado: "20 movimientos categorizados en Transporte." (singular: "1 movimiento categorizado en Transporte.") y, debajo, "Regla creada: compras en COBRO VIAJE TRANSPORTE MASIVO van a Transporte." El número es el que cuenta el servidor, que puede ser menor que el del grupo si algo ya no estaba pendiente. El resultado queda a la vista hasta cambiar de filtro. Errores: el texto de la API, en el grupo, con las opciones abiertas para reintentar.
- Cómo se categorizó, casos raros: "Otros, por una regla que ya se borró" (la regla se borró, el movimiento conserva su categoría) y "Otros, no se sabe si fue a mano o por regla" (categorizado antes de que la app guardara cómo; ícono de información).

### Saldo
- Título: "Saldo". Cifra "Saldo actual". Ayuda: "Llevas las cuentas desde el 1 de septiembre de 2026."
- Desglose **plegado por defecto** (decisión del dueño): botón "Ver cómo se calcula" (con flecha que gira al abrirlo; el texto no cambia porque el lector de pantalla ya anuncia "contraído"/"expandido"). Al abrirlo: "Saldo inicial / Ingresos / Gastos / Ajustes" y el total "Saldo actual" con subrayado doble.
- "Registrar un ingreso": campos "Monto en pesos", "Fecha y hora", "Descripción (opcional)" (ejemplo: "Por ejemplo: efectivo de una venta"); botón "Registrar ingreso".
- "Ajustar el saldo": campo "Saldo real en Bancolombia"; botón "Ajustar saldo"; aviso con "Sincronizar ahora".
- "Ingresos y ajustes de septiembre": "Total de ajustes del mes: −$18.400 en 2 ajustes". La nota "Solo se puede borrar un ingreso registrado a mano…" va al pie de la lista. Fila: "Ingreso a mano · 29 de septiembre, 10:00 a. m.", "Ingreso de Gmail · …", "Ajuste · …". Botón "Borrar ingreso" solo donde se puede. Desde el ítem 38 no hay confirmación: se borra al tocar y el aviso dice "Ingreso borrado. El saldo bajó $150.000." con «Deshacer» (ver «Deshacer»).

### Configurar saldo (ítem 16, prototipo)
- Título: "Configurar saldo". Ayuda: "Escribe el saldo de tu cuenta y la fecha desde la que la app empieza a llevar las cuentas. Solo se leen los avisos de Bancolombia desde esa fecha."
- Hoja "Tu punto de partida": campos "Saldo inicial en pesos" (ejemplo "1.250.000") y "Fecha de inicio". Ayudas: "El que tenías al comenzar el día de la fecha de inicio (a las 00:00). Punto para los miles y coma para los centavos." y "Los movimientos de ese día sí cuentan. La fecha de inicio no se puede cambiar cuando ya hay movimientos."
- Botón: "Guardar saldo inicial" (mientras dura: "Guardando…"). Resultado: "Saldo inicial guardado: $1.250.000 desde el 1 de septiembre de 2026."
- Errores de campo, debajo de cada campo (ver "Errores"): monto con letras, saldo inicial vacío, fecha de inicio vacía, fecha futura. El de la API ("ya hay movimientos") va en un aviso de error debajo del botón.
- Ya configurado: la hoja muestra "Saldo inicial" y "Fecha de inicio" como lectura, sin campos, y un aviso "El saldo inicial ya no se puede cambiar" con el texto "Ya hay movimientos desde el 1 de septiembre de 2026, así que el saldo inicial y la fecha de inicio quedaron fijos. Si el saldo no coincide con el de Bancolombia, corrígelo con un ajuste de saldo." y el botón "Ajustar el saldo".
- Título de la pestaña: "Configurar saldo · Finanzas personales".

### Categorías y reglas
- Título: "Categorías y reglas"; botón "Nueva categoría".
- Dos hojas separadas, "Categorías de gasto" y "Categorías de ingreso", y una tercera, "Reglas"; fila: nombre y "14 movimientos este mes"; botón "Editar".
- Editar: campos "Nombre", "Color", "Ícono"; botones "Guardar cambios", "Borrar categoría", "Cancelar".
- Borrar: título "Borrar la categoría Antojos", texto "Antojos tiene 12 movimientos y 1 regla. Elige a qué categoría pasan; los movimientos no se borran.", campo "Pasar movimientos y reglas a", botones "Borrar y pasar a Otros" (el nombre cambia con lo elegido) y "Cancelar".
- Fila sin movimientos en el mes: "Sin movimientos este mes" (singular: "1 movimiento este mes").
- Nueva categoría: grupo "Categoría de" con "Gasto" e "Ingreso" (solo al crear; al editar la clase no cambia), campos "Nombre", "Color · Oliva" e "Ícono · Cubiertos" (el nombre de lo elegido va junto a la etiqueta), botones "Crear categoría" (mientras corre: "Creando…") y "Cancelar". Editar: "Guardar cambios" ("Guardando…").
- Resultados: "Categoría Mascotas creada.", "Cambios guardados en Mascotas.", "Categoría Antojos borrada: 12 movimientos y 1 regla pasaron a Otros." (singular: "1 movimiento pasó a Otros"; sin nada que pasar: "Categoría Antojos borrada.").
- Borrar una categoría sin nada que pasar (`se_puede_deshacer_borrado`): desde el ítem 38 no hay diálogo; "Borrar categoría" en «Editar» la borra al tocar y el aviso dice "Categoría Préstamos borrada." con «Deshacer». Si es la última de su clase, el diálogo sigue explicando que no se puede borrar.
- Reglas escritas como frase: "Si es una transferencia de $3.200, va a Transporte", "Si es una compra en «SUPERMERCADO LA ESPIGA», va a Mercado", "Si es un ingreso de «EMPRESA EJEMPLO S.A.S.», va a Sueldo". Botón "Borrar" (desde el ítem 38, sin confirmación: el aviso dice "Regla borrada. Los movimientos que ya categorizó conservan su categoría." con «Deshacer»).

### Correos no reconocidos
- Título: "Correos no reconocidos"; botón "Volver a procesar todos" (mientras corre: "Procesando…").
- Fila: asunto del correo y "29 de septiembre de 2026, 9:28 p. m.". No se muestra el cuerpo (no se guarda).

### Más (celular)
- Título: "Más".
- "Correos no reconocidos" (con contador), "Categorías y reglas", "Apariencia" (Sistema, Claro, Oscuro) y "Cerrar sesión".

## Descripciones de lo que hace un control para lectores de pantalla

- Botones de fila: "Cambiar categoría de {descripción}", "Editar {categoría}", "Borrar regla", "Borrar ingreso {descripción}", "Categorizar las 20 de {descripción}".
- El aviso de deshacer es `role="status"` (el de error, `role="alert"`), recibe el foco al aparecer y el botón se llama "Deshacer".
- Contadores: "3 correos".
- Muestras de color y de ícono (Nueva categoría y Editar): son opciones de radio con el nombre de lo que muestran. Colores: "Oliva", "Óxido", "Azul desteñido", "Verde azulado", "Vino", "Ciruela", "Mostaza", "Rosa viejo", "Pizarra", "Verde botella", "Índigo desteñido", "Bronce". Íconos: "Canasta", "Cubiertos", "Bus", "Casa", "Corazón", "Boleta", "Bolsa de compras", "Helado", "Figuras", "Maletín", "Apretón de manos", "Monedas".
- Gráfico: la lista se llama "Gasto por categoría en septiembre" en las dos vistas. El dibujo de la dona es decorativo (`aria-hidden`): la información está en la lista. Los botones "Barras" y "Dona" forman un grupo llamado "Ver como" y usan `aria-pressed`.
- Desglose del saldo: `<details>`/`<summary>` nativo, "Ver cómo se calcula".
- Días en Movimientos: la lista de días se llama "Movimientos de septiembre, por día".
- Íconos decorativos: ocultos (`aria-hidden`).
