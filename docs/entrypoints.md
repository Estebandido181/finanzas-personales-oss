# Rutas y entrypoints de la reorganización

La reorganización cambia responsabilidades internas conservando el contrato
HTTP, los comandos y las ubicaciones de producción. El esquema vigente es 0012;
esta reorganización no añade una migración 0013.

| Uso | Entrypoint conservado | Implementación/composición |
| --- | --- | --- |
| App | `finanzas.web.app:crear_app` y `:app` perezosa | `backend/finanzas/bootstrap/app.py` |
| API/OpenAPI | `python -m finanzas.api.exportar_openapi` | `backend/finanzas/api/`; salida `openapi/openapi.json` |
| Sincronización | `python -m finanzas.sincronizacion` | Comando en `operacion/sincronizar.py`; casos/registro en `modulos/sincronizacion/`, lectores/Gmail en adaptadores |
| OAuth Gmail | `python -m finanzas.gmail autorizar` | `operacion/autorizar_gmail.py` y adaptador OAuth; `operaciones/autorizar_gmail.py` conserva la compatibilidad |
| Migración | `python -m finanzas.migrar` | Catálogo y respaldo en `operacion/`; Alembic en `migraciones/` |
| Conciliación en seco | `python -m finanzas.conciliacion_en_seco` | Lector normalizado y motor de Importaciones |
| Prueba de correo en seco | `python -m finanzas.prueba_en_seco` | Solo conteos/avisos anonimizados según opciones vigentes |
| Respaldo diario | `python3 deploy/respaldo.py` | Biblioteca estándar, independiente del entorno virtual |
| Frontend | `npm run build`, desde `frontend/` | App/funcionalidades/compartido; salida `dist/`, base `/app` |
| Tipos frontend | `npm run tipos` | Lee OpenAPI; conserva `src/api/esquema.d.ts` |
| Navegador de pruebas | `npm run e2e` | `scripts/servidor_e2e.py`, datos ficticios y puerto reservado |

Las rutas de la base, credenciales, token OAuth y respaldos de la VM siguen
siendo las de `deploy/GUIA.md`. Las units de systemd mantienen sus comandos.
La app y Sincronización usan la comprobación compuesta de revisión; abrir una
conexión no aplica migraciones. Preparar/inicializar son operaciones explícitas
de pruebas/desarrollo. Las revisiones aplicadas conservan contenido, identificadores e historia. Su ruta física pasa a `backend/finanzas/migraciones/` al trasladar el paquete, sin crear una revisión nueva.


## Snapshot independiente

Las fachadas operativas se mantienen para no romper comandos existentes. Esta
distribución excluye las configuraciones privadas de agentes y los relevos
históricos. Las reglas públicas de contribución están en CONTRIBUTING.md.
Consulta [arquitectura.md](arquitectura.md) para las responsabilidades actuales.
