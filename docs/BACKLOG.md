# Backlog del MVP

Las 14 issues principales están publicadas en [GitHub](https://github.com/SamuLopez1/EAGingenieros/issues). Este índice no representa avance: consultar el estado vivo de cada issue. Se desglosaron los diez hitos del plan en entregas revisables; si una issue no cabe en un PR manejable, acordar una subdivisión antes de implementarla. El [reenvío seguro de invitaciones #22](https://github.com/SamuLopez1/EAGingenieros/issues/22) se sigue como trabajo complementario de MVP-04, sujeto a aceptación humana del alcance.

| Issue | Entrega | Depende de | Modelo sugerido |
| --- | --- | --- | --- |
| [#1](https://github.com/SamuLopez1/EAGingenieros/issues/1) | Definir caso de uso mínimo y criterios de aceptación de EAG | — | GPT-5.6 Luna · Medium |
| [#2](https://github.com/SamuLopez1/EAGingenieros/issues/2) | Comprobar API SECOP II y disponibilidad real de documentos | [#1](https://github.com/SamuLopez1/EAGingenieros/issues/1) | GPT-5.6 Terra · Medium |
| [#3](https://github.com/SamuLopez1/EAGingenieros/issues/3) | Crear estructura base, contratos iniciales y CI | [#2](https://github.com/SamuLopez1/EAGingenieros/issues/2) | GPT-5.6 Terra · Medium |
| [#4](https://github.com/SamuLopez1/EAGingenieros/issues/4) | Implementar autenticación, roles y aislamiento de datos | [#3](https://github.com/SamuLopez1/EAGingenieros/issues/3) | GPT-5.6 Terra · High |
| [#5](https://github.com/SamuLopez1/EAGingenieros/issues/5) | Persistir oportunidades y sincronizar SECOP de forma idempotente | [#2](https://github.com/SamuLopez1/EAGingenieros/issues/2), [#4](https://github.com/SamuLopez1/EAGingenieros/issues/4) | GPT-5.6 Terra · Medium |
| [#6](https://github.com/SamuLopez1/EAGingenieros/issues/6) | Construir listado, filtros y detalle de oportunidades | [#5](https://github.com/SamuLopez1/EAGingenieros/issues/5) | GPT-5.6 Luna · Medium |
| [#7](https://github.com/SamuLopez1/EAGingenieros/issues/7) | Incorporar descarga y carga manual seguras de documentos | [#5](https://github.com/SamuLopez1/EAGingenieros/issues/5), [#6](https://github.com/SamuLopez1/EAGingenieros/issues/6) | GPT-5.6 Terra · High |
| [#8](https://github.com/SamuLopez1/EAGingenieros/issues/8) | Extraer texto de PDF, DOCX y XLSX con OCR básico | [#7](https://github.com/SamuLopez1/EAGingenieros/issues/7) | GPT-5.6 Terra · Medium |
| [#9](https://github.com/SamuLopez1/EAGingenieros/issues/9) | Registrar perfil y evidencias empresariales de EAG | [#4](https://github.com/SamuLopez1/EAGingenieros/issues/4), [#7](https://github.com/SamuLopez1/EAGingenieros/issues/7) | GPT-5.6 Luna · Medium |
| [#10](https://github.com/SamuLopez1/EAGingenieros/issues/10) | Extraer requisitos con IA y evidencia verificable | [#8](https://github.com/SamuLopez1/EAGingenieros/issues/8) | GPT-5.6 Terra · High |
| [#11](https://github.com/SamuLopez1/EAGingenieros/issues/11) | Comparar requisitos y habilitar revisión y aprobación humana | [#9](https://github.com/SamuLopez1/EAGingenieros/issues/9), [#10](https://github.com/SamuLopez1/EAGingenieros/issues/10) | GPT-5.6 Terra · High |
| [#12](https://github.com/SamuLopez1/EAGingenieros/issues/12) | Generar informe PDF aprobado y enviar correo controlado | [#11](https://github.com/SamuLopez1/EAGingenieros/issues/11) | GPT-5.6 Luna · Medium |
| [#13](https://github.com/SamuLopez1/EAGingenieros/issues/13) | Validar retención, operación, recuperación y despliegue seguro | [#12](https://github.com/SamuLopez1/EAGingenieros/issues/12) | GPT-5.6 Terra · High |
| [#14](https://github.com/SamuLopez1/EAGingenieros/issues/14) | Ejecutar piloto con EAG, medir resultados y decidir lanzamiento | [#13](https://github.com/SamuLopez1/EAGingenieros/issues/13) | GPT-5.6 Luna · Medium |

## Orden de trabajo

Empezar por #1 y #2. La prueba SECOP puede usar datos públicos con el caso de uso provisional mientras EAG valida la muestra. No afirmar que esa validación empresarial ya ocurrió. Después seguir dependencias, sin dar por listas integraciones probadas solo con mocks.

Las issues #9 y #10 alimentan #11 por rutas distintas. Esto permite reparto entre miembros del equipo, pero no implica ejecutar agentes simultáneos ni modificar la misma rama.

## Regla de entrega

Una issue → una rama → cambios acotados → pruebas → PR → revisión → merge → cierre cuando todos los criterios estén cumplidos. Para validaciones externas pendientes, documentar y mantener la issue abierta; un PR documental no demuestra aceptación de EAG.

El presupuesto de 10–12 semanas es orientativo. #1–2 cubren definición y viabilidad; #3–4 la base y acceso; #5–8 oportunidades/documentos; #9–11 perfil y análisis; #12 informes; #13–14 operación y piloto. Reestimar después del spike.

Cada [especificación local](issues/) tiene alcance, exclusiones, aceptación, pruebas y un prompt. GitHub es la fuente de estado; actualizar especificaciones si se modifica el alcance.
