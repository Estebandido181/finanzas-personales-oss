# Organización de las pruebas del backend

- `api/`: contratos HTTP, sesión, CSRF y respuestas.
- `modulos/`: comportamiento de Categorías, Importaciones, Saldo, Sesión y Sincronización.
- `flujos/`: recorridos que coordinan varios módulos, como Arranque.
- `persistencia/`: esquema, migraciones y acceso a SQLite.
- `operacion/`: despliegue, respaldo, comandos y herramientas.
- `arquitectura/`: caracterización y fronteras de la reorganización.
- `soporte/`: fixtures y constructores compartidos; ningún archivo de prueba importa otro `test_*.py`.
- `fixtures/`: datos inventados o anonimizados. El Excel se genera en memoria desde `soporte/excel_inventado.py`; no se versionan `.xlsx`.

Desde la raíz del repositorio, `python -m pytest -q` descubre todas las pruebas. Al añadir una ayuda reutilizable, ubícala en `soporte/` y conserva las pruebas en la carpeta de la capacidad que verifican.
