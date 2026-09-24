# ADR-006: Tokens de sesión en `sessionStorage`

**Estado:** Aceptada, con endurecimiento pendiente
**Fecha:** 2026-09-23

## Contexto

El navegador necesita conservar el token de acceso y el de refresco. Con la
autenticación propia ([ADR-001](001-base-de-datos-propia.md)) la API los devuelve
en el cuerpo de la respuesta, así que el cliente tiene que guardarlos en alguna
parte.

Las opciones reales son tres:

| Opción | Ventaja | Coste |
| --- | --- | --- |
| `localStorage` | La sesión persiste entre reinicios del navegador | Ventana de exposición indefinida |
| `sessionStorage` | No sobrevive al cierre de la pestaña | Hay que volver a entrar al cerrar el navegador |
| Cookie `httpOnly` | Ningún script puede leer el token | Exige cambiar la API para emitirla |

El riesgo de XSS no es teórico aquí: **la interfaz muestra texto que viene de los
pliegos** —título, entidad, referencia— y ese contenido es no confiable por
definición. React lo escapa al renderizarlo, pero la defensa no debe depender de
un único mecanismo.

## Decisión

**`sessionStorage`**, no `localStorage`. La ventana de exposición de un token
robado es una sesión de trabajo, no un plazo indefinido.

Se asume el coste: hay que volver a iniciar sesión al cerrar el navegador.

## Consecuencias

**A favor**

- El token de refresco no queda en disco. Un equipo compartido no conserva la
  sesión de quien lo usó antes.
- La degradación es segura: si `sessionStorage` no está disponible —pruebas,
  renderizado en servidor— el sistema cae a memoria en lugar de fallar. La sesión
  funciona, solo que no persiste.

**En contra, y lo que queda pendiente**

- **El endurecimiento completo no está hecho.** La solución correcta es que el
  servidor entregue el token de refresco en una cookie `httpOnly`, que ningún
  script puede leer. Eso exige cambiar la API, que hoy devuelve los tokens en el
  cuerpo, y añadir protección CSRF. **Queda declarado como pendiente, no como
  resuelto.**
- **`sessionStorage` también es legible por un script.** Reduce la ventana, no
  elimina la vía. Mitiga que el token de refresco rote con detección de
  reutilización: reutilizar uno ya usado revoca la familia completa, así que un
  robo se detecta en el siguiente uso legítimo.

## Nota sobre el manejo de errores de sesión

El cliente HTTP refresca el token **una sola vez y de forma compartida**: sin
esa coordinación, cinco peticiones que reciben 401 a la vez dispararían cinco
refrescos, y como el servidor rota el token y detecta la reutilización, cerrarían
la sesión del usuario —justo lo contrario de lo que se pretende—.
