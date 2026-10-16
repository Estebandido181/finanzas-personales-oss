/**
 * Todos los textos de la base del frontend (ítem 12), en un solo lugar.
 * Siguen frontend/diseno/TEXTOS.md: de tú, frases cortas, cada botón dice lo
 * que hace y cada pantalla vacía dice qué pasa y qué hacer. `disenador-ui`
 * los revisa aquí en la revisión visual.
 */

export const TEXTOS = {
  app: {
    nombre: "Finanzas personales",
    marca: "Finanzas",
    cargando: "Cargando…",
    saltarAlContenido: "Saltar al contenido",
    secciones: "Secciones",
  },
  entrar: {
    titulo: "Finanzas personales",
    ayuda: "Tus cuentas del mes, al día y sin anotar nada a mano.",
    campo: "Contraseña",
    boton: "Entrar",
    botonEnCurso: "Entrando…",
  },
  errores: {
    contrasenaIncorrecta: "Contraseña incorrecta. Revísala y vuelve a intentarlo.",
    demasiadosIntentos: "Demasiados intentos fallidos. Espera unos minutos y vuelve a intentarlo.",
    sesionCerrada: "Tu sesión se cerró. Entra de nuevo para seguir.",
    sinConexion: "No hay conexión con la app. Revisa tu internet y vuelve a intentarlo.",
    /** Respaldo, solo si no hay un texto más preciso para el caso. */
    fallaDelServidor: "La app no pudo completar la acción. Vuelve a intentarlo en unos minutos.",
    entrarFallo: "No se pudo entrar. Vuelve a intentarlo en unos minutos.",
    cerrarSesionFallo: "No se pudo cerrar la sesión. Vuelve a intentarlo en unos minutos.",
    contrasenaVacia: "Escribe tu contraseña.",
    volverAIntentar: "Volver a intentar",
  },
  apariencia: {
    titulo: "Apariencia",
    ayuda: "«Sistema» sigue el modo claro u oscuro de tu celular.",
    sistema: "Sistema",
    claro: "Claro",
    oscuro: "Oscuro",
  },
  cerrarSesion: {
    boton: "Cerrar sesión",
    botonEnCurso: "Cerrando sesión…",
  },
  mas: {
    titulo: "Más",
  },
  /** Inicio (ítem 13): TEXTOS.md, "Inicio (reporte del mes)" y "Caso del ítem 13". */
  inicio: {
    cambiarDeMes: "Cambiar de mes",
    sincronizarAhora: "Sincronizar ahora",
    sincronizando: "Sincronizando…",
    sincronizacionEnCurso: "Ya hay una sincronización en curso. Espera a que termine.",
    categorizarAhora: "Categorizar ahora",
    /**
     * Aviso de pendientes. Ítem 15: los ingresos sin categoría también son
     * pendientes, pero su monto va aparte, nunca sumado al de los gastos.
     */
    pendientes: {
      suman: "Suman",
      gastosSuman: "Los gastos suman",
      enElGrafico: "Mientras no tengan categoría, aparecen como «Sin categorizar» en el gráfico.",
      aparteIngresos: "Aparte, los ingresos suman",
      soloIngresos: "Los ingresos suman",
    },
    ayudaGasto: "Compras y transferencias. Los ingresos y los ajustes de saldo no cuentan como gasto.",
    saldoActual: "Saldo actual",
    enQueSeFue: "¿En qué se fue?",
    verMovimientos: "Ver movimientos",
    verComo: "Ver como",
    barras: "Barras",
    dona: "Dona",
    totalGastado: "Total gastado",
    ultimosMovimientos: "Últimos movimientos",
    verTodos: "Ver todos los movimientos",
    errorSincronizacion: {
      titulo: "No se pudo sincronizar con Gmail",
      queHacer: "Qué hacer:",
      reautorizar:
        "vuelve a autorizar Gmail con el paso 8 de la guía de despliegue («Gmail») y después toca «Sincronizar ahora», arriba.",
      botonGuia: "Ver cómo autorizar Gmail",
      /** Sin causa clara (error_inesperado). */
      sinCausa:
        "Vuelve a intentarlo en unos minutos; si se repite, revisa el registro del servidor (guía de despliegue, «Solución de problemas»).",
    },
    sinSaldo: {
      titulo: "Empieza por tu saldo",
      texto:
        "Escribe el saldo de tu cuenta y la fecha desde la que la app lleva las cuentas. Solo se leen los avisos desde esa fecha.",
      boton: "Configurar saldo",
    },
  },
  /** Movimientos (ítem 14): TEXTOS.md, "Movimientos" y "Estados vacíos". */
  movimientos: {
    titulo: "Movimientos",
    filtros: "Filtros",
    mostrar: "Mostrar",
    todos: "Todos",
    gastos: "Gastos",
    ingresos: "Ingresos",
    categoria: "Categoría",
    todasLasCategorias: "Todas las categorías",
    categoriasDeGasto: "Categorías de gasto",
    categoriasDeIngreso: "Categorías de ingreso",
    gastado: "Gastado:",
    sinCategorizar: "Sin categorizar",
    categorizar: "Categorizar",
    cambiar: "Cambiar",
    cancelar: "Cancelar",
    elegir: "¿En qué categoría va? Toca una:",
    aMano: "a mano",
    porRegla: "por regla:",
    /** La regla que lo categorizó ya se borró (el movimiento conserva su categoría). */
    porReglaBorrada: "por una regla que ya se borró",
    /** Categorizado antes de que la app guardara cómo (migración del ítem 14). */
    desconocido: "no se sabe si fue a mano o por regla",
    /** Ítem 17: el botón de la regla por texto y monto, junto a las otras dos (prototipo). */
    lasDosCosasJuntas: "Las dos cosas juntas",
    verTodos: "Ver todos los movimientos",
    /** Bajo el título, en vez del selector de mes: la bandeja es una sola, de todos los meses. */
    bandejaTodosLosMeses: "Sin categorizar · todos los meses",
    /** La lista de días de la bandeja, para lectores de pantalla. */
    listaBandeja: "Movimientos sin categorizar, por día",
    yaNoExiste: "Ese movimiento ya no existe. Recarga la página.",
    /** Ítem 38: movimientos iguales, categorizados juntos con un toque (y su regla). */
    grupos: {
      titulo: "Movimientos que se repiten",
      ayuda:
        "Son iguales entre sí. Categorízalos juntos con un toque y la app guarda la regla para los siguientes.",
      lista: "Grupos de movimientos iguales",
      yaNoHay: "Esos movimientos ya no estaban sin categorizar. No se cambió nada.",
    },
  },
  /** Categorías y reglas (ítem 15): TEXTOS.md, "Categorías y reglas" y "Confirmaciones". */
  categorias: {
    titulo: "Categorías y reglas",
    nueva: "Nueva categoría",
    deGasto: "Categorías de gasto",
    deIngreso: "Categorías de ingreso",
    editar: "Editar",
    reglas: "Reglas",
    ayudaReglas:
      "Una regla categoriza sola los movimientos nuevos que cumplen todas sus condiciones. Si dos reglas coinciden, gana la más específica. Se crean al categorizar un movimiento.",
    vaA: ", va a",
    borrar: "Borrar",
    borrarRegla: "Borrar regla",
    sinReglas: {
      titulo: "Todavía no hay reglas",
      texto:
        "Se crean al categorizar un movimiento: después de elegir la categoría, toca una de las reglas que te propone la app.",
      boton: "Ir a Movimientos",
    },
    // Formulario (Nueva categoría y Editar).
    clase: "Categoría de",
    /** Al editar (la clase no cambia): solo lectura. */
    claseGasto: "Categoría de gasto",
    claseIngreso: "Categoría de ingreso",
    gasto: "Gasto",
    ingreso: "Ingreso",
    nombre: "Nombre",
    color: "Color",
    icono: "Ícono",
    crear: "Crear categoría",
    creando: "Creando…",
    guardar: "Guardar cambios",
    guardando: "Guardando…",
    borrarCategoria: "Borrar categoría",
    borrando: "Borrando…",
    cancelar: "Cancelar",
    sinCambios: "No cambiaste nada.",
    // Borrar.
    pasarA: "Pasar movimientos y reglas a",
    reglaBorrada: "Regla borrada. Los movimientos que ya categorizó conservan su categoría.",
    reglaRestaurada: "Regla restaurada.",
    yaNoExiste: "Esa categoría ya no existe. Recarga la página.",
    reglaYaNoExiste: "Esa regla ya no existe. Recarga la página.",
  },
  /** Correos no reconocidos (ítem 19): TEXTOS.md, "No reconocidos" y "Estados vacíos". */
  noReconocidos: {
    titulo: "Correos no reconocidos",
    ayuda:
      "Avisos de Bancolombia que la app no supo leer o que no pasaron la verificación de autenticidad. No crean movimientos. Después de corregir el lector, vuelve a procesarlos.",
    volverAProcesar: "Volver a procesar todos",
    procesando: "Procesando…",
    vacioTitulo: "No hay correos sin reconocer",
    vacioTexto:
      "Todos los avisos de Bancolombia que llegaron se leyeron bien. Si un día aparece uno aquí, es porque su formato cambió o no pasó la verificación de autenticidad.",
    volverAlInicio: "Volver al inicio",
    /** Inventado (revisar con disenador-ui): no hay texto en TEXTOS.md para esta falla. */
    errorTitulo: "No se pudieron volver a procesar los correos",
  },
  /** Saldo, ingresos y ajustes (ítem 16): TEXTOS.md, "Saldo", "Ayudas cortas" y "Errores". */
  saldo: {
    titulo: "Saldo",
    saldoActual: "Saldo actual",
    verComoSeCalcula: "Ver cómo se calcula",
    saldoInicial: "Saldo inicial",
    ingresos: "Ingresos",
    gastos: "Gastos",
    ajustes: "Ajustes",
    registrar: {
      titulo: "Registrar un ingreso",
      ayuda:
        "Para dinero que entra sin aviso de Bancolombia, como efectivo. Los ingresos con aviso entran solos: no los registres aquí.",
      monto: "Monto en pesos",
      ayudaMonto: "Punto para los miles y coma para los centavos.",
      ejemploMonto: "150.000",
      fecha: "Fecha y hora",
      descripcion: "Descripción",
      opcional: "(opcional)",
      ejemploDescripcion: "Por ejemplo: efectivo de una venta",
      boton: "Registrar ingreso",
      /** Inventado (revisar con disenador-ui): TEXTOS.md pide cambiar el texto mientras dura. */
      enCurso: "Registrando…",
    },
    ajustar: {
      titulo: "Ajustar el saldo",
      ayuda:
        "Escribe el saldo que ves en Bancolombia. La diferencia se guarda como un ajuste (cuota de manejo, 4x1000 y otros cobros sin aviso) y no cuenta como gasto.",
      antes:
        "Sincroniza antes de ajustar: si el banco ya descontó una compra que la app todavía no trajo, se restaría dos veces.",
      campo: "Saldo real en Bancolombia",
      boton: "Ajustar saldo",
      /** Inventado (revisar con disenador-ui). */
      enCurso: "Ajustando…",
      /** Inventado (revisar con disenador-ui): el aviso grande con la causa vive en Inicio. */
      sincronizacionFallida: "No se pudo sincronizar con Gmail. En Inicio verás qué pasó y qué hacer.",
    },
    totalAjustes: "Total de ajustes del mes",
    notaBorrar:
      "Solo se puede borrar un ingreso registrado a mano y posterior al último ajuste. Los ajustes y lo que llega de Gmail no se borran.",
    borrar: "Borrar ingreso",
    borrando: "Borrando…",
    /** Inventado (revisión del ítem 16): falta el token de un solo uso del formulario. */
    sinToken: "El formulario ya no es válido. Se volvió a cargar: inténtalo de nuevo.",
    /** Sin saldo configurado: el estado vacío de Inicio y la ayuda de "Configurar saldo inicial". */
    sinConfigurar: {
      titulo: "Empieza por tu saldo",
      texto:
        "El saldo inicial es el que tenías al comenzar el día de la fecha de inicio (a las 00:00): los movimientos de ese día sí cuentan. Una vez haya movimientos ya no se puede cambiar.",
      boton: "Configurar saldo",
    },
    /** Configurar saldo (ítem 16): TEXTOS.md, "Configurar saldo"; errores de campo en saldo/datos.ts. */
    configurar: {
      titulo: "Configurar saldo",
      ayuda:
        "Escribe el saldo de tu cuenta y la fecha desde la que la app empieza a llevar las cuentas. Solo se leen los avisos de Bancolombia desde esa fecha.",
      puntoDePartida: "Tu punto de partida",
      monto: "Saldo inicial en pesos",
      ejemploMonto: "1.250.000",
      ayudaMonto:
        "El que tenías al comenzar el día de la fecha de inicio (a las 00:00). Punto para los miles y coma para los centavos.",
      fecha: "Fecha de inicio",
      ayudaFecha: "Los movimientos de ese día sí cuentan. La fecha de inicio no se puede cambiar cuando ya hay movimientos.",
      boton: "Guardar saldo inicial",
      enCurso: "Guardando…",
      saldoInicial: "Saldo inicial",
      fijoTitulo: "El saldo inicial ya no se puede cambiar",
      ajustar: "Ajustar el saldo",
    },
  },
  /** Deshacer en vez de confirmar (ítem 38): TEXTOS.md, "Deshacer". */
  deshacer: {
    boton: "Deshacer",
    deshaciendo: "Deshaciendo…",
    /** 410 sin un `detalle` de la API (la API manda este mismo texto). */
    yaNoSePuede: "Ya no se puede deshacer: pasó el tiempo o ya se deshizo.",
    /** 409 sin un `detalle` de la API (la API manda el motivo). */
    algoCambio: "No se puede deshacer: algo cambió mientras tanto.",
  },
  noEncontrada: {
    titulo: "Esta página no existe",
    texto: "Revisa la dirección o vuelve al inicio.",
    boton: "Volver al inicio",
  },
} as const;

/**
 * Paso 8 de la guía de despliegue («Gmail»). La guía vive en el repositorio,
 * no en la app (decisión del dueño para el ítem 13).
 */
export const GUIA_AUTORIZAR_GMAIL =
  "https://github.com/Estebandido181/finanzas-personales-oss/blob/main/docs/GMAIL.md";

/** "Gmail rechazó el permiso…" con o sin la fecha de la última correcta. */
export function textoPermisoRechazado(desde: string | null): string {
  const inicio = "Gmail rechazó el permiso de lectura de la app: se venció o se revocó.";
  return desde
    ? `${inicio} Desde el ${desde} no entran movimientos nuevos, así que el reporte puede estar incompleto.`
    : `${inicio} Mientras no se arregle, no entran movimientos nuevos y el reporte puede estar incompleto.`;
}

/** Mes sin movimientos (TEXTOS.md, "Estados vacíos"). En un mes pasado no se invita a sincronizar. */
export function textosMesVacio(nombreMes: string, esMesActual: boolean) {
  return {
    titulo: `Sin movimientos en ${nombreMes}`,
    texto: esMesActual
      ? "Todavía no hay compras, transferencias ni ingresos este mes. Si acabas de pagar algo, sincroniza para traerlo."
      : `No hubo compras, transferencias ni ingresos en ${nombreMes}.`,
  };
}

/** "Sin categorizar (2)" (segmento de Movimientos). */
export function segmentoSinCategorizar(cantidad: number): string {
  // Con 0 no se muestra "(0)" (decisión de disenador-ui).
  if (cantidad === 0) return TEXTOS.movimientos.sinCategorizar;
  return `${TEXTOS.movimientos.sinCategorizar} (${cantidad})`;
}

/** "Movimientos de septiembre, por día" (la lista de días, para lectores de pantalla). */
export function listaDias(nombreMes: string): string {
  return `Movimientos de ${nombreMes}, por día`;
}

/** "3 correos", "1 correo": para lectores de pantalla (TEXTOS.md, "Contadores"). */
export function correos(cantidad: number): string {
  return cantidad === 1 ? "1 correo" : `${cantidad} correos`;
}

/** "Editar Mercado" (título del diálogo; el botón "Editar" se lee igual). */
export function tituloEditar(nombre: string): string {
  return `Editar ${nombre}`;
}

/** "Borrar la categoría Antojos" (título del diálogo de borrar). */
export function tituloBorrarCategoria(nombre: string): string {
  return `Borrar la categoría ${nombre}`;
}

/** "Categoría Mascotas creada." */
export function categoriaCreada(nombre: string): string {
  return `Categoría ${nombre} creada.`;
}

/** "Cambios guardados en Mascotas." */
export function cambiosGuardados(nombre: string): string {
  return `Cambios guardados en ${nombre}.`;
}

/** "Ingreso restaurado. El saldo volvió a $4.739.150." (el saldo lo manda la API). */
export function ingresoRestaurado(saldoPesos: string | null): string {
  return saldoPesos === null ? "Ingreso restaurado." : `Ingreso restaurado. El saldo volvió a ${saldoPesos}.`;
}

/** "Categoría Préstamos restaurada." */
export function categoriaRestaurada(nombre: string): string {
  return `Categoría ${nombre} restaurada.`;
}

/** "20 movimientos categorizados en Transporte." (singular: "1 movimiento categorizado"). */
export function grupoCategorizado(cantidad: number, categoria: string): string {
  return cantidad === 1
    ? `1 movimiento categorizado en ${categoria}.`
    : `${cantidad} movimientos categorizados en ${categoria}.`;
}

/** "20 veces" (cuántos movimientos tiene un grupo). */
export function vecesDelGrupo(cantidad: number): string {
  return cantidad === 1 ? "1 vez" : `${cantidad} veces`;
}

/** "Categorizar las 20" (el botón de un grupo). */
export function botonCategorizarGrupo(cantidad: number): string {
  return cantidad === 1 ? "Categorizar" : `Categorizar las ${cantidad}`;
}

/** "¿En qué categoría van las 20? Toca una:" */
export function preguntaGrupo(cantidad: number): string {
  return cantidad === 1 ? "¿En qué categoría va? Toca una:" : `¿En qué categoría van las ${cantidad}? Toca una:`;
}
