# Contexto del MVP

## Problema y usuarios

EAG Ingenieros S.A.S. desarrolla consultoría, diseño, construcción e interventoría. El MVP apoya al área Comercial y Contratación al buscar oportunidades y contrastar sus requisitos con información empresarial. El análisis manual consume tiempo aun en oportunidades que finalmente no son viables; no contamos todavía con una línea base medida y validada.

Usuario principal: analista de licitaciones. Gerencia toma la decisión empresarial; las áreas técnica, financiera, talento humano y documental aportan evidencia. Roles iniciales de la aplicación: administrador y analista. Una organización: EAG.

## Flujo mínimo

Consultar SECOP II → filtrar → consultar oportunidad → reunir documentos → extraer requisitos → comparar con perfil de EAG → corregir/revisar → aprobar borrador → generar PDF y enviar correo a destinatarios autorizados.

No se postulan ofertas automáticamente y no se garantiza adjudicación. Una recomendación de la herramienta no sustituye la decisión humana.

## Alcance acordado

- Primera versión con SECOP II; carga manual cuando no se puedan obtener todos los documentos.
- PDF, DOCX y XLSX; OCR básico para PDF escaneado. ZIP, si se admite, con controles de descompresión.
- Evidencia por requisito: documento, localizador (página, sección o celda), fragmento y versión.
- Resultado de comparación: `cumple`, `cumple_parcialmente`, `no_cumple`, `revision_manual`.
- Reglas deterministas para fechas, cantidades e indicadores; IA para extracción e interpretación semántica. No afirmar cumplimiento sin evidencia.
- Perfil persistente de EAG: experiencia, personal, capacidades, información financiera y documentos, con permisos.
- Aprobación humana obligatoria antes del informe final y correo. Cambios posteriores invalidan la aprobación.
- Eliminación de documentos de oportunidad, texto extraído, análisis e informes a los 30 días; definir origen del plazo y tratamiento de backups antes de producción. Los registros maestros empresariales tienen otra política, aún por formalizar.
- Objetivo temporal de desarrollo: 10–12 semanas, sujeto a acceso, validación y capacidad del equipo.

## Arquitectura prevista, pendiente de validar en código

React + TypeScript + Vite + React Query + Tailwind; Python + FastAPI + Pydantic + SQLAlchemy + Alembic; PostgreSQL/Auth/Storage de Supabase. Vercel para frontend y Render para API/workers. Celery/Redis para tareas; Tesseract para OCR; ClamAV para análisis de archivos; WeasyPrint para PDF; Resend para correo; Sentry para errores sin contenido sensible.

OpenAI detrás de un adaptador sustituible; modelo configurable y respuestas estructuradas. No enviar documentos internos sin autorización empresarial específica. `store=false` no equivale por sí solo a retención cero del proveedor. No se han contratado ni configurado estos servicios.

La arquitectura es una dirección de trabajo, no una obligación de instalar todos los servicios en el primer hito. Registrar cambios relevantes en decisiones de arquitectura breves.

## Hipótesis y comprobaciones pendientes

- La cobertura de pliegos de procesos abiertos mediante los datos oficiales no está comprobada.
- Datasets candidatos: procesos `p6dx-8zbt`; documentos desde 2025 `dmgg-8hin`. Comprobar propietario, esquema, relación y disponibilidad actual. No confundir documentos de contratos con pliegos de oportunidades abiertas.
- Sincronización propuesta: diaria a las 06:00 America/Bogota, manual adicional y ventana de revisión de 7 días. Verificar fechas disponibles, actualización e idempotencia.
- Límites propuestos: 50 MB por archivo y 300 MB por oportunidad; deben validarse con muestras y presupuesto de OCR.
- Una reducción del 60% en tiempo sería una meta a negociar y medir, no un resultado demostrado ni compromiso contractual validado.
- El equipo debe obtener un caso real autorizado y criterios de aceptación del usuario. No subir ese expediente al repositorio.

## Fuera del MVP

Envío automático de propuestas, adjudicación/decisión autónoma, WhatsApp/Telegram, múltiples fuentes, facturación, aplicación móvil y personalizaciones avanzadas.

## Fuentes para la prueba de integración

- [Catálogo oficial CCE](https://operaciones.colombiacompra.gov.co/transparencia/conjuntos-de-datos-abiertos)
- [Procesos de contratación SECOP II](https://dev.socrata.com/foundry/www.datos.gov.co/p6dx-8zbt)
- [Archivos de descarga desde 2025](https://dev.socrata.com/foundry/www.datos.gov.co/dmgg-8hin)

Son puntos de partida para comprobar la integración, no evidencia de una integración ya ejecutada.
