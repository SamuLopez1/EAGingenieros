# [MVP-06] Construir listado, filtros y detalle de oportunidades

## Objetivo

Entregar el primer flujo visible y útil al analista, con datos reales del backend.

## Dependencias

- MVP-05

Las dependencias requieren su resultado técnico aceptado. En MVP-02 se puede avanzar con el borrador del caso y datos públicos mientras EAG valida la muestra; eso no sustituye la aceptación empresarial.

## Trabajo incluido

- Crear listado paginado, filtros y detalle con enlace oficial y fecha de última sincronización.
- Definir filtros guardados administrables para EAG usando campos disponibles.
- Aplicar identidad visual sobria EAG, diseño responsive y navegación accesible.
- Mostrar carga, vacío, error y datos desactualizados sin inventar métricas.

## Criterios de aceptación

- [ ] Filtros, orden y paginación funcionan contra la API y se prueban con resultados conocidos.
- [ ] Detalle conserva ID y fuente de SECOP, y permite volver al listado sin perder filtros.
- [ ] No quedan datos mock en la ruta de producción.
- [ ] Campos tienen etiquetas y controles usables con teclado; se comprueba pantalla estrecha.
- [ ] Solo usuarios autorizados modifican configuración compartida de filtros.

## Verificación

Pruebas de filtros/componentes y E2E listado→detalle→volver con capturas de escritorio/móvil.

## Catálogo sobre el contrato de MVP-05

La ruta `/` abre el catálogo después de validar la sesión. Usa
`GET /api/v1/opportunities` y `GET /api/v1/opportunities/{id}` de MVP-05.
Los filtros y el orden se aplican en servidor antes de contar o paginar.
La URL conserva criterios, orden y página al abrir una ficha, usar «Volver
al listado» o usar Atrás del navegador.

- Entidad busca en la entidad contratante. Ubicación busca en
  `departamento_entidad` y `ciudad_entidad`. Estos campos representan la
  ubicación de la entidad, no el lugar de ejecución del contrato.
- El rango de cierre incluye ambos días UTC y usa `reception_at` del contrato
  de #5, que corresponde a la fecha de recepción de respuestas. Los procesos
  sin fecha siguen visibles al omitir el rango. La zona original de los
  valores sin offset continúa pendiente de confirmación.
- El estado oficial se conserva por separado. Un estado terminal reconocido
  se muestra como **Cerrado**. Una fase explícita de recepción con estado
  publicado, o un estado explícito de apertura, se muestra como **Abierto** si
  el plazo es futuro y **Vencido** si ya se cumplió. Ante información insuficiente
  se muestra **Vigencia desconocida**. La ficha muestra el enlace HTTPS
  del dominio oficial si la fuente lo aporta.
- Los miembros de EAG pueden usar filtros compartidos. Las altas, cambios y
  bajas requieren el rol administrador y se restringen a su organización.

Aplicar `python -m alembic upgrade head` desde `apps/api`. La revisión
`20261122000002` continúa la de #5 y completa ubicación y recepción de las
filas existentes desde su carga original. Ejecutar la migración conectada
a PostgreSQL antes de iniciar la API.

### Verificación reproducible

Desde `apps/api`, con el entorno de dependencias fijadas:

```powershell
python -m ruff check .
python -m mypy app
$env:EAG_TEST_POSTGRES = '1'
python -m pytest
Remove-Item Env:EAG_TEST_POSTGRES
```

Desde la raíz:

```powershell
npm run lint --prefix apps/web
npm run typecheck --prefix apps/web
npm run test --prefix apps/web
npm run build --prefix apps/web
python scripts/mvp06_preview.py --browser-cli $playwrightCli
python scripts/mvp06_preview.py --public --browser-cli $playwrightCli
```

`$playwrightCli` apunta a `playwright-cli.js`. El runner requiere Docker
con la imagen local `postgres:17.6-bookworm`, Chrome y las dependencias web.
Inicia FastAPI, Vite y PostgreSQL desechables con identidad sintética. El
recorrido offline usa cuatro casos de vigencia y captura escritorio y móvil.
El modo `--public` consulta una muestra de hasta cinco filas, sincroniza dos
por ID y comprueba cada enlace con un GET. No descarga documentos. Los datos
de la muestra se retiran con la base local y se emiten solo recuentos y
estados HTTP. Los archivos bajo `output/playwright/` quedan fuera de Git.

### Resultados del 22 de noviembre de 2026

- Ruff y mypy correctos. **168 pruebas API**, incluida la migración de una
  fila preexistente de #5 en PostgreSQL real, y **11 pruebas del spike**
  aprobaron. Lint, typecheck, **42 pruebas web** y compilación aprobaron.
- Chrome comprobó Abierto, Cerrado, Vencido y Vigencia desconocida con datos
  sintéticos en 1440×1080 y 390×844. Se crearon cuatro capturas locales y se
  comprobó que no hubiera desbordamiento horizontal de página.
- La muestra pública respondió 200 y se sincronizaron dos procesos distintos
  en PostgreSQL local. Chrome abrió ambas fichas mediante la API. Al volver
  con el enlace del catálogo y con Atrás conservó entidad, ubicación, modalidad
  y rango de cierre. Las fichas mostraron la fuente, el ID, la última carga y
  el enlace oficial correspondiente a cada fila.
- Ambos enlaces eran destinos de proceso HTTPS de `community.secop.gov.co`.
  La comprobación HTTP directa devolvió 403 para cada enlace. Chrome recibió
  302 y terminó en otras páginas del mismo portal con HTTP 200. El último
  destino no coincidió con la ficha original en ninguno de los dos casos.
  Queda pendiente confirmar el acceso al detalle remoto de cada proceso.

## Fuera de alcance

Dashboard de métricas inventadas, extracción documental y recomendaciones IA.

## Modelo sugerido para programar

GPT-5.6 Luna · Medium. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Implementa listado, filtros guardados y detalle usando exclusivamente la API existente. Usa estilo EAG y estados de carga/vacío/error. Prueba navegación, permisos y accesibilidad; evita añadir un dashboard fuera de alcance.
```
