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

Unitarias de reglas y transiciones; E2E borrador→corrección→aprobación→cambio→invalidación; evaluación de falsos cumplimientos.

## Fuera de alcance

Decisión autónoma de participar, porcentajes arbitrarios de viabilidad o evidencia inventada.

## Modelo sugerido para programar

GPT-5.6 Terra · High. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Implementa comparación explicable y revisión humana, con estados tipados y aprobación versionada. Demuestra que evidencia insuficiente requiere revisión y que cualquier cambio invalida aprobación. No implementes envíos todavía.
```
