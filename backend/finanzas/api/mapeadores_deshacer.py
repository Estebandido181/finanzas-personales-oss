"""Adaptación HTTP: mapeadores_deshacer."""
from __future__ import annotations
from fastapi import Request
from finanzas.api import deshacer
from finanzas.api import modelos as m


def _deshacer(request: Request, copia: object) -> m.Deshacer:
    registro: deshacer.RegistroDeshacer = request.app.state.deshacer
    return m.Deshacer(token=deshacer.emitir(request, registro, copia), segundos=registro.segundos)
