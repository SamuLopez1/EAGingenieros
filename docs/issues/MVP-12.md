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

En la ficha abre «Comparar con EAG», revisa y aprueba la versión. Con aprobación
vigente, el analista y el administrador pueden previsualizar y descargar el PDF.
El administrador puede elegir un destinatario de la lista autorizada y consultar
la auditoría de cada intento. El PDF identifica oportunidad, versión, perfil,
aprobador y fecha e incluye las limitaciones y evidencias de la matriz.

- `GET /api/v1/opportunities/{opportunity_id}/reports/{revision}` sirve el PDF
  autenticado. Usa `?download=true` para descargarlo. Se verifica vigencia en cada
  petición, incluso usando la URL directamente.
- El subrecurso `/mail` permite al administrador consultar y enviar. El correo
  contiene un enlace al portal autenticado, con oportunidad y revisión, sin
  adjuntos ni credenciales. El destinatario debe tener acceso vigente a EAG.
- La clave de entrega permanece estable por organización, oportunidad, revisión
  y destinatario. Se registra una reserva antes de llamar al proveedor. Hay
  hasta tres intentos manuales en 15 minutos. Una respuesta incierta fuera de
  ese plazo requiere conciliación. Los cambios de credencial o de ruta del
  portal bloquean el reintento. «Aceptado» indica respuesta del proveedor.
- Se guarda el destinatario y la auditoría en la tabla privada. El informe se
  regenera a petición desde las evidencias vigentes, sin almacenar bytes del PDF.

Desde `apps/api`, aplica `python -m alembic upgrade head` y ejecuta
`python -m pytest tests/test_reports.py`. Usa
`EAG_TEST_POSTGRES=1 python -m pytest tests/test_postgres_sync_integration.py -k report`
para verificar la migración en PostgreSQL local. El transporte HTTP de prueba
reproduce una respuesta perdida después de aceptar el mensaje. El smoke en Chrome
usa Vite, API, PostgreSQL y worker reales, con identidad, antivirus y correo simulados.

```text
python scripts/mvp06_preview.py --dossier --extraction --comparison --report --browser-cli RUTA_A_PLAYWRIGHT_CLI
```

### Prueba real autorizada

En un entorno de prueba, prepara un informe sintético y obtén autorización para
el buzón de destino y para el remitente verificado. Configura en el backend
`EAG_REPORT_RESEND_API_KEY`, `EAG_REPORT_MAIL_SENDER`,
`EAG_REPORT_MAIL_RECIPIENTS` con solo el buzón aprobado y
`EAG_REPORT_PORTAL_URL` con la URL HTTPS del portal. Usa una cuenta administradora
para enviar y una cuenta EAG autorizada para abrir el enlace. Confirma una sola
copia en la bandeja tras repetir la misma solicitud. Comprueba que el enlace
pide sesión y que deja de servir el PDF al invalidar la aprobación.

El resultado de la bandeja debe registrarse aparte con fecha y estado, sin
direcciones ni contenido sensible en Git. Hasta contar con buzón y configuración
autorizados queda pendiente la prueba de entrega real.
[Referencia de idempotencia de Resend](https://resend.com/docs/dashboard/emails/idempotency-keys).

## Fuera de alcance

WhatsApp/Telegram, envío automático indiscriminado o adjuntar expedientes completos por defecto.

## Modelo sugerido para programar

GPT-5.6 Luna · Medium. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Genera PDF a partir de análisis aprobado y añade envío controlado por correo. Verifica permisos, vigencia, deduplicación y render visual. Usa una bandeja de prueba y no envíes información real sin autorización.
```
