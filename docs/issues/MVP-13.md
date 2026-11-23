# [MVP-13] Validar retención, operación, recuperación y despliegue seguro

## Objetivo

Completar las garantías operativas antes de usar documentos reales en producción.

## Dependencias

- MVP-12

Las dependencias requieren su resultado técnico aceptado. En MVP-02 se puede avanzar con el borrador del caso y datos públicos mientras EAG valida la muestra; eso no sustituye la aceptación empresarial.

## Trabajo incluido

- Formalizar inicio del plazo de 30 días e implementar purga de archivos, texto, análisis, informes y copias de trabajo.
- Definir política separada para maestros, auditoría sin contenido y backups; evitar resurrección de datos purgados tras restauración.
- Configurar staging/producción, secretos, monitorización, colas fallidas, backups y procedimiento de rollback.
- Documentar autorización empresarial y tratamiento/retención del proveedor de IA; probar restauración.

## Criterios de aceptación

- [ ] Test con reloj controlado verifica expiración y purga, preservando solo lo autorizado por política documentada.
- [ ] Logs/alertas no contienen archivos, credenciales o contenido empresarial.
- [ ] Staging exige autenticación; ninguna clave privilegiada ni bucket público se expone.
- [ ] Restauración y rollback se ensayan; el procedimiento reaplica tombstones/purgas pendientes.
- [ ] Checklist de salida identifica costes y aprobaciones pendientes; no se contratan servicios sin autorización específica.

## Verificación

El [procedimiento de operación](OPERACION-13.md) registra responsables, comandos, evidencias de caducidad, recuperación y rollback, y el estado del smoke de staging.

## Fuera de alcance

Tratar este hito como primera implementación de seguridad o declarar producción lista sin verificaciones.

## Modelo sugerido para programar

GPT-5.6 Terra · High. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Audita y completa operación, purga y recuperación sobre el MVP existente. Prueba los 30 días con reloj controlado, backups/restauración y acceso en staging. Documenta bloqueos y no declares producción lista si faltan autorización o pruebas.
```
