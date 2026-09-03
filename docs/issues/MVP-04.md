# [MVP-04] Implementar autenticación, roles y aislamiento de datos

## Objetivo

Proteger el acceso antes de incorporar información empresarial.

## Dependencias

- MVP-03

Las dependencias requieren su resultado técnico aceptado. En MVP-02 se puede avanzar con el borrador del caso y datos públicos mientras EAG valida la muestra; eso no sustituye la aceptación empresarial.

## Trabajo incluido

- Integrar autenticación por invitación, roles administrador/analista y pertenencia a EAG.
- Validar sesión/JWT en backend, permisos en API y almacenamiento; no confiar en controles de UI.
- Añadir migraciones, auditoría inicial de accesos/cambios y estrategia RLS cuando aplique.
- Documentar configuración segura y recuperación/revocación de acceso.

## Criterios de aceptación

- [ ] Acceso anónimo a rutas protegidas devuelve 401; rol sin permiso devuelve 403.
- [ ] No existe registro público ni escalada de rol desde cliente.
- [ ] Pruebas cubren token inválido/expirado, revocación según proveedor y acceso a recursos de otra organización/usuario sin permiso.
- [ ] Claves privilegiadas nunca aparecen en navegador o logs; validación de issuer/audience/firma según configuración.
- [ ] Se documenta matriz de permisos y se comprueba login/logout con el proveedor configurado; mocks se identifican.

## Verificación

Pruebas de permisos en API y datos; E2E autenticación si el entorno real está configurado. No cerrar con solo UI de login.

## Fuera de alcance

Datos reales de EAG, módulos de análisis y secretos embebidos.

## Modelo sugerido para programar

GPT-5.6 Terra · High. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Implementa autenticación por invitación y dos roles, verificando permisos en servidor y datos. Prioriza pruebas negativas de acceso y escalada de privilegios. No marques listo el proveedor real si solo se probaron mocks.
```
