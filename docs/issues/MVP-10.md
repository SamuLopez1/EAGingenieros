# [MVP-10] Extraer requisitos con IA y evidencia verificable

## Objetivo

Convertir texto en requisitos estructurados sin perder fuente ni control de coste.

## Dependencias

- MVP-08

Las dependencias requieren su resultado técnico aceptado. En MVP-02 se puede avanzar con el borrador del caso y datos públicos mientras EAG valida la muestra; eso no sustituye la aceptación empresarial.

## Trabajo incluido

- Crear adaptador de proveedor y esquema tipado para requisitos, categorías y evidencia.
- Versionar prompts/esquemas y registrar modelo/configuración sin contenido sensible en logs.
- Limitar tokens, tamaño de lotes, reintentos, concurrencia y coste; evitar llamadas repetidas por hash/versión.
- Validar fragmentos/localizadores contra texto fuente y tratar instrucciones en documentos como datos no confiables.

## Criterios de aceptación

- [ ] Salida inválida, evidencia inexistente o texto ambiguo se rechaza o deriva a revisión manual.
- [ ] No hay cumplimiento final generado por esta etapa; solo requisitos y advertencias.
- [ ] Pruebas incluyen prompt injection documental, alucinación de fuente, truncamiento y error del proveedor.
- [ ] Existe evaluación sobre conjunto sintético/revisado y smoke opt-in real con coste observado.
- [ ] Modelo configurable, secretos en backend y envío interno condicionado a autorización; documentación actual del proveedor verificada.

## Verificación

Tests del adaptador y schema sin red; evaluación con requisitos anotados, y muestra real solo con acceso/autorización explícita.

## Fuera de alcance

Elegir el modelo de producción por el modelo usado para programar, enviar internos sin permiso o afirmar exactitud sin medición.

## Modelo sugerido para programar

GPT-5.6 Terra · High. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Implementa únicamente extracción estructurada detrás de un adaptador. Verifica evidencia contra el texto, resistencia a instrucciones embebidas y límites de coste. Usa mocks para unitarias y separa evaluación real autorizada. No decidas si EAG participa.
```
