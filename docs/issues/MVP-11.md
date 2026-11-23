# [MVP-11] Comparar requisitos y habilitar revisión y aprobación humana

## Objetivo

Producir un borrador defendible y corregible, con control explícito de versiones.

## Dependencias

- MVP-09
- MVP-10

Las dependencias requieren su resultado técnico aceptado. En MVP-02 se puede avanzar con el borrador del caso y datos públicos mientras EAG valida la muestra; eso no sustituye la aceptación empresarial.

## Trabajo incluido

- Implementar reglas deterministas para fechas/números y evaluación semántica donde corresponda.
- Mostrar requisito, evidencia de fuente, evidencia empresarial, resultado y motivo.
- Permitir corrección justificada y aprobación humana de una versión del análisis.
- Aplicar estados y auditoría; invalidar aprobación si cambian entradas o resultados.

## Criterios de aceptación

- [ ] Resultados permitidos: cumple, cumple_parcialmente, no_cumple, revision_manual.
- [ ] Falta de evidencia nunca se convierte automáticamente en cumple.
- [ ] Pruebas cubren límites numéricos, unidades/moneda, vigencia, evidencia faltante y contradicción.
- [ ] Cambiar documento, perfil o decisión exige nuevo análisis/revisión y anula aprobación anterior.
- [ ] La aprobación guarda usuario, fecha y versiones; no equivale a postular ni adjudicar.

## Verificación

En la ficha, marca en revisión las versiones del pliego y sus adendas y extrae sus
textos. Registra en el perfil la evidencia empresarial y su localizador. Pulsa
**Comparar con EAG**. Cada fila conserva la cita y versión del expediente, muestra
las evidencias empresariales y destaca los habilitantes pendientes o incumplidos.

- El analista puede generar y corregir la matriz. Toda corrección requiere justificación.
  Registrar cumplimiento total o parcial por corrección exige seleccionar evidencia
  empresarial verificada. El administrador puede aprobar con una justificación.
- La auditoría guarda autor y rol, fecha, revisión del análisis, versión del perfil,
  versiones y huellas de los documentos, correcciones y resultados aprobados.
- Si cambia el pliego, una adenda, la selección, la extracción, el perfil o las reglas,
  el API presenta la comparación como desactualizada. Volver a una selección anterior
  no reactiva una aprobación. Una corrección posterior vuelve a abrir el borrador.
  Los cambios documentales solo afectan su ficha. El perfil maestro es común a las
  comparaciones de la organización.
- Las reglas automáticas evalúan umbrales expresados como
  `Habilitante: Experiencia vial: mínimo 12 meses.` y vigencias como
  `Habilitante: Certificado: vigente al 2026-12-31.`. El nombre del registro vincula
  el requisito con el perfil. Se convierten años y meses, y se comparan monedas
  iguales. Un faltante, una contradicción o una correspondencia ambigua exige
  revisión humana. Los criterios de puntuación requieren interpretación humana.
- Se puede aprobar un borrador con brechas visibles. Aprobar registra una revisión
  humana de la matriz. Los estados de cada requisito se conservan por separado.

Desde `apps/api`, ejecuta `python -m alembic upgrade head` y
`python -m pytest tests/test_comparison.py`. La migración de #11 une las revisiones
de #8 y #9. Para comprobarla en PostgreSQL local desechable, usa
`EAG_TEST_POSTGRES=1 python -m pytest tests/test_postgres_sync_integration.py -k comparison`.

Desde la raíz, el recorrido en Chrome usa FastAPI, Vite, PostgreSQL y el worker reales
con identidad, escáner antivirus, documentos y perfil sintéticos.

```text
python scripts/mvp06_preview.py --dossier --extraction --comparison --browser-cli RUTA_A_PLAYWRIGHT_CLI
```

La revisión operativa de permisos y el caso empresarial autorizado quedan a cargo
de EAG. La rama de comparación parte de una base técnica fija con #9 y #10 mientras
se integran ambos PR.

## Fuera de alcance

Decisión autónoma de participar, porcentajes arbitrarios de viabilidad o evidencia inventada.

## Modelo sugerido para programar

GPT-5.6 Terra · High. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Implementa comparación explicable y revisión humana, con estados tipados y aprobación versionada. Demuestra que evidencia insuficiente requiere revisión y que cualquier cambio invalida aprobación. No implementes envíos todavía.
```
