# [MVP-12] Generar informe PDF aprobado y enviar correo controlado

## Objetivo

Entregar un informe trazable sin enviar borradores ni duplicar correos.

## Dependencias

- MVP-11

Las dependencias requieren su resultado técnico aceptado. En MVP-02 se puede avanzar con el borrador del caso y datos públicos mientras EAG valida la muestra; eso no sustituye la aceptación empresarial.

## Trabajo incluido

- Crear PDF con identificación de oportunidad, requisitos, evidencia, limitaciones y aprobación.
- Implementar vista previa y envío a destinatarios configurados/autorizados.
- Asegurar idempotencia del envío, reintentos limitados y auditoría.
- Proteger descarga y evitar contenido sensible en logs o enlaces públicos.

## Criterios de aceptación

- [ ] Backend bloquea PDF final/envío sin aprobación vigente, incluso invocando endpoint directamente.
- [ ] Informe identifica versión, aprobador y fecha; no incluye afirmaciones sin evidencia.
- [ ] Reintento del mismo envío no duplica correos; destino y estado quedan auditados.
- [ ] PDF se renderiza y revisa visualmente con tablas largas y caracteres españoles.
- [ ] Pruebas usan sandbox/mock de correo; envío real solo a destinatarios de prueba autorizados.

## Verificación

Tests de aprobación/permisos/idempotencia, render PDF y E2E con bandeja de prueba.

## Fuera de alcance

WhatsApp/Telegram, envío automático indiscriminado o adjuntar expedientes completos por defecto.

## Modelo sugerido para programar

GPT-5.6 Luna · Medium. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Genera PDF a partir de análisis aprobado y añade envío controlado por correo. Verifica permisos, vigencia, deduplicación y render visual. Usa una bandeja de prueba y no envíes información real sin autorización.
```
