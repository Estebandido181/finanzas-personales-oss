"""Asignación individual y aplicación de reglas mediante participantes tipados."""
from finanzas.modulos.categorias.contratos import (
    Asignacion, CategoriaDeEntrada, ErrorCategorizacion, MovimientoNoEncontrado, ReglaGuardada, UnidadAsignacionCategorias,
)
from finanzas.modulos.categorias.politica import (
    CAMPO_POR_TIPO, CLASE_POR_TIPO, TIPOS_PENDIENTES, normalizar, CONDICIONES, CONDICION_TEXTO, CondicionesRegla, campo_para_tipo, clase_para_tipo,
    condiciones_de_regla, elegir_regla, motivo_sin_regla, ReglaEvaluable,
)

from finanzas.modulos.categorias.grupos import leer_clave_grupo, MAXIMO_IDS_GRUPO, MENSAJE_CLAVE_INVALIDA


class AsignarCategorias:
    def __init__(self, unidad: UnidadAsignacionCategorias):
        self._unidad = unidad

    def categoria_para_entrada(self, tipo: str, descripcion: str, monto_centavos: int,
                               categoria_al_leer: str | None = None) -> CategoriaDeEntrada:
        """Participante de la inserción: lee bajo la transacción de quien incorpora.

        La categoría implícita del retiro gana a las reglas. Si dejó de existir,
        se aplica la misma política de reglas que a cualquier otro aviso.
        """
        if categoria_al_leer is not None:
            clave = normalizar(categoria_al_leer)
            categoria = next((c for c in sorted(self._unidad.categorias.otras(None), key=lambda c: c.id)
                              if c.clase == "gasto" and normalizar(c.nombre) == clave), None)
            if categoria is not None:
                return CategoriaDeEntrada(categoria.id)
        regla = self.regla_que_coincide(tipo, descripcion, monto_centavos)
        return CategoriaDeEntrada() if regla is None else CategoriaDeEntrada(regla.categoria_id, "regla", regla.id)

    def regla_que_coincide(self, tipo: str, descripcion: str, monto_centavos: int | None,
                          origen: str = "gmail", referencia: str | None = None) -> ReglaGuardada | None:
        campo = campo_para_tipo(tipo)
        if campo is None:
            return None
        candidatas = self._unidad.reglas.candidatas(campo, monto_centavos)
        evaluables = [ReglaEvaluable(r.id, r.categoria_id, r.campo, r.texto, r.monto_centavos,
                                    r.modo_texto, r.origen_regla) for r in candidatas]
        ganadora = elegir_regla(evaluables, tipo, descripcion, monto_centavos, origen, referencia)
        return None if ganadora is None else next(r for r in candidatas if r.id == ganadora.id)

    def guardar_regla(self, nueva: CondicionesRegla, categoria_id: int) -> int:
        """Participante: requiere la transacción de quien coordina la asignación."""
        return self._unidad.reglas.guardar(nueva, categoria_id)

    def aplicar_a_pendientes(self, tipo: str, regla_id: int, categoria_id: int) -> int:
        """Participante: conserva las decisiones ya asignadas por el dueño."""
        registro = self._unidad.movimientos
        alcanzados = [fila.id for fila in registro.listar_pendientes(tipo)
                      if (gana := self.regla_que_coincide(fila.tipo, fila.descripcion, fila.monto_centavos,
                                                        fila.origen, fila.referencia)) is not None
                      and gana.id == regla_id]
        return sum(registro.asignar_por_regla_si_pendiente(i, categoria_id, regla_id) for i in alcanzados)

    def asignar(self, movimiento_id: int, categoria_id: int, recordar: bool,
                condiciones: str = CONDICION_TEXTO) -> Asignacion:
        if condiciones not in CONDICIONES:
            raise ErrorCategorizacion("Elige una regla por texto, por monto o por las dos cosas.")
        with self._unidad.escritura(inmediata=True):
            registro = self._unidad.movimientos
            movimiento = registro.buscar_activo(movimiento_id)
            if movimiento is None:
                raise MovimientoNoEncontrado("El movimiento no existe.")
            clase = clase_para_tipo(movimiento.tipo)
            if clase is None:
                raise ErrorCategorizacion("Solo se categorizan compras, transferencias e ingresos.")
            categoria = self._unidad.categorias.buscar(categoria_id)
            if categoria is None:
                raise ErrorCategorizacion("La categoría no existe.")
            if categoria.clase != clase:
                raise ErrorCategorizacion("Un ingreso solo acepta categorías de ingreso." if clase == "ingreso"
                                          else "Un gasto solo acepta categorías de gasto.")
            nueva = condiciones_de_regla(movimiento.tipo, movimiento.descripcion, movimiento.monto_centavos, condiciones)
            if recordar and nueva is None:
                raise ErrorCategorizacion(motivo_sin_regla(movimiento.descripcion, movimiento.monto_centavos, condiciones))
            registro.asignar_manual(movimiento_id, categoria_id)
            if not recordar:
                return Asignacion(total=1, regla_id=None)
            regla_id = self.guardar_regla(nueva, categoria_id)
            total = 1 + self.aplicar_a_pendientes(movimiento.tipo, regla_id, categoria_id)
            return Asignacion(total=total, regla_id=regla_id)

    def categorizar_grupo(self, clave: str, ids, categoria_id: int, modo_regla: str = "exacta") -> Asignacion:
        """Asigna la categoría a todos los movimientos del grupo y guarda su regla, en una sola transacción.

        * ``clave``: la del grupo (``clave_grupo``); ``ids``: los movimientos que
          la pantalla mostró en él.
        * Se categorizan los de ``ids`` que **siguen** pendientes y siguen siendo
          del grupo (mismo tipo y misma descripción normalizada). Los demás
          (categorizados mientras tanto, borrados u otro movimiento con ese id)
          no se tocan y no cuentan.
        * Quedan con origen ``manual``, como el movimiento elegido en
          ``asignar_con_detalle``: el dueño decidió sobre ellos.
        * Se guarda la regla por texto del grupo (o, si ya había una con esas
          mismas condiciones, pasa a esta categoría) y se aplica a los demás
          pendientes para los que gana, como "recordar"; esos quedan con origen
          ``regla`` y sí cuentan en ``total``.
        * Si ninguno de ``ids`` sigue pendiente en el grupo, no cambia nada
          (``total`` 0 y sin regla).

        Lanza ``ErrorCategorizacion`` sin cambiar nada si la clave no es válida,
        ``ids`` está vacía o es demasiado larga, o la categoría no existe o es de
        otra clase.
        """
        sin_descripcion = clave.startswith("sin-descripcion:")
        if not sin_descripcion:
            tipo, texto = leer_clave_grupo(clave)
        if modo_regla not in ("exacta", "contiene", "empieza_por"):
            raise ErrorCategorizacion("La forma de la regla no es válida.")
        unicos = list(dict.fromkeys(ids))
        if not unicos:
            raise ErrorCategorizacion("El grupo no tiene movimientos.")
        if len(unicos) > MAXIMO_IDS_GRUPO:
            raise ErrorCategorizacion("El grupo tiene demasiados movimientos.")
        with self._unidad.escritura(inmediata=True):
            registro = self._unidad.movimientos
            if sin_descripcion:
                if len(unicos) != 1 or clave != f"sin-descripcion:{unicos[0]}":
                    raise ErrorCategorizacion(MENSAJE_CLAVE_INVALIDA)
                pendientes_sin_texto = registro.listar_pendientes_por_ids(unicos, TIPOS_PENDIENTES)
                fila_sin_texto = pendientes_sin_texto[0] if pendientes_sin_texto else None
                if fila_sin_texto is None or normalizar(fila_sin_texto.descripcion):
                    raise ErrorCategorizacion(MENSAJE_CLAVE_INVALIDA)
                tipo, texto = fila_sin_texto.tipo, ""
            clase = CLASE_POR_TIPO[tipo]
            categoria = self._unidad.categorias.buscar(categoria_id)
            if categoria is None:
                raise ErrorCategorizacion("La categoría no existe.")
            if categoria.clase != clase:
                raise ErrorCategorizacion(
                    "Un ingreso solo acepta categorías de ingreso."
                    if clase == "ingreso"
                    else "Un gasto solo acepta categorías de gasto."
                )
            filas = registro.listar_pendientes_por_ids(unicos, TIPOS_PENDIENTES)
            miembros = [
                int(f.id) for f in filas if f.tipo == tipo and normalizar(f.descripcion) == texto
            ]
            if not miembros:
                return Asignacion(total=0, regla_id=None)
            if modo_regla != "exacta" and any(f.origen != "extracto" for f in filas if int(f.id) in miembros):
                raise ErrorCategorizacion("Contiene y empieza por solo se usan para movimientos del banco.")
            total = registro.asignar_grupo_si_pendientes(miembros, categoria_id)
            if not texto:
                return Asignacion(total=int(total), regla_id=None)
            regla = CondicionesRegla(campo=CAMPO_POR_TIPO[tipo], texto=texto, monto_centavos=None,
                                    modo_texto=modo_regla, origen_regla="extracto" if modo_regla != "exacta" else "todos",
                                    texto_visible=filas[0].descripcion if all(f.origen == "extracto" for f in filas) else None)
            regla_id = self.guardar_regla(regla, categoria_id)
            total += self.aplicar_a_pendientes(tipo, regla_id, categoria_id)
            return Asignacion(total=int(total), regla_id=regla_id)
