# [MVP-09] Registrar perfil y evidencias empresariales de EAG

## Objetivo

Proveer una fuente empresarial versionada para comparaciones posteriores.

## Dependencias

- MVP-04
- MVP-07

Las dependencias requieren su resultado técnico aceptado. En MVP-02 se puede avanzar con el borrador del caso y datos públicos mientras EAG valida la muestra; eso no sustituye la aceptación empresarial.

## Trabajo incluido

- Modelar experiencia, contratos/certificados, personal, equipos, datos financieros y legales con vigencias.
- Crear formularios y API con validación de campos y evidencias privadas.
- Registrar versión, fecha, autor, historial y estado pendiente/verificado según revisión humana.
- Documentar diferencia entre retención de perfil maestro y documentos de oportunidad.

## Criterios de aceptación

- [ ] Administrador gestiona perfil; analista accede según matriz acordada; pruebas validan permisos en backend.
- [ ] Datos numéricos/fechas se validan sin confundir desconocido con cero.
- [ ] Cada capacidad usada como evidencia tiene documento/localizador o se marca pendiente.
- [ ] Editar crea versión e historial sin modificar silenciosamente análisis anteriores.
- [ ] Se usan fixtures sintéticas; ningún dato real de EAG se siembra en Git.

## Verificación

Pruebas CRUD, validaciones, permisos, vigencias y conservación de versiones.

## Fuera de alcance

Asumir que documentos cargados certifican automáticamente capacidad o cumplimiento.

## Modelo sugerido para programar

GPT-5.6 Luna · Medium. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Implementa perfil empresarial con evidencias, vigencias y versiones usando almacenamiento y permisos existentes. Usa datos sintéticos y distingue información pendiente de verificada. No desarrolles aún el comparador.
```
