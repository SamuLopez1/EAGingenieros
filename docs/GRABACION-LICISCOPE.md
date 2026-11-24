# Liciscope · Guion de grabación

Liciscope es la empresa ficticia de la demostración. El catálogo local
se alimenta de los procesos de SECOP II con estado **Publicado** y fecha
de recepción futura al momento de la consulta. Conserva la ficha pública
preparada para el video y cero oportunidades sintéticas. El perfil, sus
soportes, las cuentas y la entrega de correo son de prueba. El histórico de
todos los estados y años se puede consultar en la fuente oficial.
[Catálogo histórico de SECOP II](https://www.datos.gov.co/d/p6dx-8zbt)

| Dato | Valor |
| --- | --- |
| Proceso de oferta | [CO1.REQ.11405993 en datos abiertos](https://www.datos.gov.co/resource/p6dx-8zbt.json?id_del_proceso=CO1.REQ.11405993) |
| Referencia / aviso | [CM-06-IN-006-2026 · CO1.NTC.11260034](https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.11260034) |
| Documento | [Pliego definitivo oficial · archivo 894696463](https://community.secop.gov.co/Public/Archive/RetrieveFile/Index?DocUniqueIdentifier=&DocumentId=894696463&InCommunity=False&InPaymentGateway=False) |
| Verificación | PDF de 64 páginas. El pliego identifica la referencia. SHA-256 a6f01faa1a4ebba3777299c47919811bba1a52c9e78878fa870ed3e79745b2d0. |
| Ficha local | 1, en la base desechable del ensayo. |

## Preparar la sesión

Desde la raíz, prepara el entorno Python con las dependencias fijadas de
apps/api y ejecuta npm ci --prefix apps/web. Usa Docker con PostgreSQL
postgres:17.6-bookworm y el contenedor oficial de ClamAV. El ejecutor local
debe poder obtener la fila pública de datos.gov.co y el PDF de
community.secop.gov.co. El siguiente comando de Docker es para la primera
vez. Reutiliza el contenedor si ya está activo.

~~~powershell
docker pull clamav/clamav@sha256:64e30c0bf976198024deb3dc6d5cfe2485fb969c0f73549ba0fdb364b9469614
docker run -d --name liciscope-clamd -p 127.0.0.1:13310:3310 -e CLAMAV_NO_FRESHCLAMD=true clamav/clamav@sha256:64e30c0bf976198024deb3dc6d5cfe2485fb969c0f73549ba0fdb364b9469614
docker logs --tail 5 liciscope-clamd
python scripts/mvp06_preview.py --recording --duration 3600
~~~

Espera LICISCOPE_SECOP, LICISCOPE_OK y QA_READY. Abre [Liciscope local](http://127.0.0.1:15178)
en una ventana privada nueva. El servidor local genera el secreto de descarga,
inicia el worker, carga clamd y prepara el caso. El arranque comprueba el hash,
la cita, el PDF privado y el correo simulado. Deja la comparación en borrador
y el buzón vacío para el recorrido. Ctrl+C desde la terminal de arranque cierra
el ensayo y retira su base PostgreSQL desechable. Si se inició en segundo
plano, desde la raíz ejecuta New-Item -ItemType File output/liciscope.stop
y espera a que se libere el puerto 15178. Para repetir desde cero, inicia
de nuevo el mismo comando. Para conservar una sesión anterior en el puerto
15178, inicia otra con --recording-port 15179. Su marcador de cierre es
output/liciscope-15179.stop.

Usa la cuenta administradora de fixture definida en scripts/mvp06_preview.py.
Hay también una cuenta de analista para comprobar permisos de consulta.
Rellena los campos con la grabación pausada. Oculta la barra de autocompletado,
las herramientas de desarrollo y la configuración del backend. Nunca uses
una cuenta empresarial en este entorno.

## Perfil privado de demostración

El arranque incluye nueve registros ficticios y evidencia rotulada. Desde
**Perfil empresarial** se puede mostrar la experiencia en adecuaciones
escolares, la capacidad de interventoría, los equipos y la disponibilidad:

| Cargo ficticio | Dedicación | Periodo de ejemplo | Revisión del dato |
| --- | --- | --- | --- |
| Director de interventoría | 50 % | 01/12/2026 a 31/03/2027 | Verificado en la fixture |
| Residente de interventoría | 100 % | 01/12/2026 a 31/03/2027 | Verificado en la fixture |
| Especialista ambiental | 25 % | 01/12/2026 a 31/03/2027 | Por confirmar |

Cada soporte adicional tiene un localizador en el PDF sintético de ocho
páginas. Los estados verificados se refieren a los registros de la
demostración. El Formato 3 sigue en revisión manual y el capital de trabajo
es un supuesto pendiente. Guardar una versión del perfil invalida la
aprobación previa del expediente. Actualiza la comparación antes de emitir
el PDF de la nueva revisión.

## Guion de 2 minutos y 35 segundos

| Tiempo | Acción y explicación |
| --- | --- |
| 0:00–0:20 | Mostrar el login de Liciscope. Iniciar sesión con los campos ya preparados fuera de cámara. Explicar que el catálogo viene de SECOP II. |
| 0:20–0:45 | Mostrar el total del catálogo y **Sincronizar ahora**. A continuación filtrar por CM-06-IN-006-2026, abrir su ficha y mostrar el ID y el pliego oficial disponible en **Expediente**. |
| 0:45–1:15 | Mostrar la extracción y pulsar **Generar resumen y requisitos**. Señalar el objeto en página 1 y el requisito del Formato 3 de experiencia en página 19. Pulsa **Ver documento** en la cita de la página 19. El visor abre el PDF privado en esa página y permite abrirlo en otra pestaña. |
| 1:15–1:50 | Pulsar **Comparar con Liciscope**. Mostrar «Revisión manual» para el requisito del Formato 3. Explicar que el soporte de la empresa está rotulado como sintético y queda pendiente de verificación. |
| 1:50–2:10 | Completar la justificación de aprobación académica y pulsar **Aprobar comparación**. Abrir vista previa o descargar el PDF privado. Mostrar Liciscope, la revisión y una cita. La aprobación del informe conserva el resultado de revisión manual. |
| 2:10–2:35 | Elegir el destinatario de prueba y pulsar **Enviar enlace privado**. Pulsar **Comprobar o reintentar envío** si aparece. Abrir **Buzón simulado**. Mostrar el único mensaje y que el enlace conduce al portal, que exige login en una ventana privada nueva. |

## Verificar la conexión con SECOP II

- **Sincronizar ahora** consulta todas las páginas del corte, muestra nuevas,
  actualizadas y sin cambios, y refresca el listado. Solo el administrador
  dispara una carga manual.
- El servidor vuelve a consultar la fuente automáticamente cada tres minutos
  mientras esté funcionando. Para una demostración más rápida usa
  --recording-refresh 60. El catálogo visible consulta la copia local cada
  20 segundos. Un proceso nuevo aparece tras la siguiente carga exitosa,
  cuando ya está visible en datos abiertos y cumple el corte. Una demora
  entre la publicación y la disponibilidad en el dataset depende de SECOP II.
- La carga conserva lo previamente importado y usa el ID de SECOP como clave.
  Al repetir el mismo corte, los IDs existentes mantienen su ficha y su
  expediente. Si se agota el límite de páginas o la fuente falla, la
  ejecución se marca como fallida y conserva lo ya cargado.
- Para verificar altas con reloj controlado y sin publicar casos de prueba
  en SECOP, ejecutar desde apps/api el test siguiente. Cambia la respuesta
  de la fuente simulada entre dos cargas y verifica el alta y la idempotencia.

~~~powershell
python -m pytest -q tests/test_liciscope_catalog.py
~~~

En el ensayo en 15179 se comprobaron 2.893 fichas reales y cero
sintéticas. El arranque incorporó 2.892 nuevas a la base local después
de preparar la ficha 1. El botón y una ejecución automática consultaron
el corte real y devolvieron 2.893 registros sin cambios. Chrome confirmó
la paginación y la búsqueda de la ficha preparada. El alta de un ID nuevo
entre consultas se ensayó offline. Durante la prueba de red no apareció
una publicación nueva de la fuente.

## Evidencia y modalidad de correo

Chrome verificó desde sesión limpia el login, perfil, catálogo, ficha 1,
resumen, matriz, aprobación, descarga y buzón. Al abrir el enlace sin sesión,
el portal volvió al login. La comprobación reproducible del navegador está
en scripts/liciscope_browser_check.js para Playwright CLI.

- El ensayo local importa mediante la ruta oficial del expediente y analiza
  el archivo con clamd. El worker y las citas se comprueban en la ficha 1.
  La revisión de la matriz registra revisión manual. El PDF aprobado responde
  200 con sesión y 401 sin sesión. Una nueva versión del perfil invalida la
  aprobación y el PDF anterior responde 409.
- La bandeja simula que el proveedor aceptó el mensaje y se perdió la primera
  respuesta. El reintento y la repetición producen **un solo mensaje**.
  El buzón está disponible solo en este entorno de grabación. Su enlace va al
  portal en loopback, donde siguen activos el login y la autorización de PDF.
- La recepción real queda pendiente de un remitente verificado, el proveedor,
  un único buzón autorizado y un portal HTTPS. Para esa modalidad se aplica
  la configuración y el procedimiento del
  [PR #36](https://github.com/SamuLopez1/EAGingenieros/pull/36).
