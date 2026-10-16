"""Administración de categorías sobre participantes de una única transacción."""
from finanzas.modulos.categorias.contratos import (
    CategoriaBorrada, CategoriaNoEncontrada, CopiaCategoria, ErrorCategorizacion,
    RestauracionNoPermitida, UnidadAdministracionCategorias,
)
from finanzas.modulos.categorias.politica import (
    borrado_reversible, comprobar_unicidad, limpiar_nombre, texto_clase, validar_color_e_icono,
)


class AdministrarCategorias:
    def __init__(self, unidad: UnidadAdministracionCategorias):
        self._unidad = unidad

    def _comprobar_unica(self, nombre, clase, color, icono, excepto=None):
        comprobar_unicidad(self._unidad.categorias.otras(excepto), nombre, clase, color, icono)

    def crear(self, nombre: str, clase: str, color: str, icono: str) -> int:
        if clase not in ("gasto", "ingreso"):
            raise ErrorCategorizacion("La clase debe ser gasto o ingreso.")
        limpio = limpiar_nombre(nombre)
        validar_color_e_icono(color, icono)
        with self._unidad.escritura(inmediata=True):
            self._comprobar_unica(limpio, clase, color, icono)
            return self._unidad.categorias.insertar(limpio, clase, color, icono)

    def editar(self, categoria_id: int, nombre: str | None = None,
               color: str | None = None, icono: str | None = None) -> None:
        if nombre is None and color is None and icono is None:
            raise ErrorCategorizacion("No hay nada que cambiar.")
        limpio = None if nombre is None else limpiar_nombre(nombre)
        with self._unidad.escritura(inmediata=True):
            actual = self._unidad.categorias.buscar(categoria_id)
            if actual is None:
                raise CategoriaNoEncontrada("La categoría no existe.")
            nuevo_nombre = actual.nombre if limpio is None else limpio
            nuevo_color = actual.color if color is None else color
            nuevo_icono = actual.icono if icono is None else icono
            validar_color_e_icono(nuevo_color, nuevo_icono)
            self._comprobar_unica(nuevo_nombre, actual.clase, nuevo_color, nuevo_icono, categoria_id)
            self._unidad.categorias.actualizar(categoria_id, nuevo_nombre, nuevo_color, nuevo_icono)

    def borrar(self, categoria_id: int, destino_id: int | None) -> CategoriaBorrada:
        categorias, movimientos = self._unidad.categorias, self._unidad.movimientos
        with self._unidad.escritura(inmediata=True):
            categoria = categorias.buscar(categoria_id)
            if categoria is None:
                raise CategoriaNoEncontrada("La categoría no existe.")
            clase = categoria.clase
            if categorias.contar_clase(clase) <= 1:
                raise ErrorCategorizacion(f"No se puede borrar la última categoría de {texto_clase(clase)}: crea otra antes.")
            cantidad_movimientos = movimientos.contar_en_categoria(categoria_id)
            cantidad_reglas = categorias.contar_reglas(categoria_id)
            if destino_id is None:
                if cantidad_movimientos or cantidad_reglas:
                    raise ErrorCategorizacion("Elige a qué categoría pasan sus movimientos y reglas.")
            else:
                if destino_id == categoria_id:
                    raise ErrorCategorizacion("Elige otra categoría para pasar sus movimientos y reglas.")
                destino = categorias.buscar(destino_id)
                if destino is None:
                    raise ErrorCategorizacion("La categoría a la que pasan no existe.")
                if destino.clase != clase:
                    raise ErrorCategorizacion(
                        f"Los movimientos y reglas de una categoría de {texto_clase(clase)} solo "
                        f"pueden pasar a otra categoría de {texto_clase(clase)}."
                    )
                movimientos.reasignar_categoria(categoria_id, destino_id)
                categorias.mover_reglas(categoria_id, destino_id)
            categorias.borrar(categoria_id)
        copia = None
        if borrado_reversible(cantidad_movimientos, cantidad_reglas):
            copia = CopiaCategoria(categoria.id, categoria.nombre, clase, categoria.color, categoria.icono)
        return CategoriaBorrada(cantidad_movimientos, cantidad_reglas, destino_id, copia)

    def restaurar(self, copia: CopiaCategoria) -> int:
        with self._unidad.escritura(inmediata=True):
            try:
                self._comprobar_unica(copia.nombre, copia.clase, copia.color, copia.icono)
            except ErrorCategorizacion as error:
                motivo = str(error)
                raise RestauracionNoPermitida(f"No se puede deshacer: {motivo[:1].lower()}{motivo[1:]}") from None
            return self._unidad.categorias.insertar(copia.nombre, copia.clase, copia.color, copia.icono, copia.id)
