# Sistema de diseño

Documentación de diseño para la interfaz del producto. El archivo
[`DESIGN.md`](DESIGN.md) es el contrato: cualquier agente o persona que construya
UI debe leerlo antes de escribir estilos.

- [`DESIGN.md`](DESIGN.md) — tokens, componentes y reglas
- [`referencia.html`](referencia.html) — referencia visual navegable
- [`referencia-visual.png`](referencia-visual.png) — captura completa

## Procedencia y decisión

La base proviene de [`stripe/DESIGN.md`](https://github.com/VoltAgent/awesome-design-md/tree/main/design-md/stripe)
del repositorio **VoltAgent/awesome-design-md** (74 sistemas analizados).

Se evaluaron los candidatos con más peso documental contra lo que este producto
realmente necesita: un analista leyendo pliegos durante horas, evidencia
trazable, y cuatro estados de veredicto.

| Candidato | Por qué no | Por qué sí |
| --- | --- | --- |
| **Linear** | Su documento prohíbe explícitamente el modo claro: *"Don't ship a light-mode marketing page"*. Es dark-first por identidad, y su negro `#010102` es fatiga garantizada en jornadas largas. | La mejor densidad técnica de la colección: escalera de superficies y hairlines. |
| **Airtable** | Su carácter viene de tarjetas a sangre en coral y verde oscuro: lenguaje de marketing, no de herramienta de trabajo. | Sobriedad editorial, tipografía en pesos modestos. |
| **PostHog** | Marimoñas ilustradas y canvas crema. Incompatible con decisiones sobre contratación pública. | — |
| **Stripe** ✅ | — | Polaridad dual (claro para trabajar, oscuro para el panel), cifras tabulares nativas, y **un solo acento cromático** deja libres los colores semánticos. |

### Por qué Stripe

1. **Continuidad.** El `stripe/DESIGN.md` de este repositorio es el mismo sistema
   que ya usa la página de historias de usuario. Un analista que lee el plan y
   luego usa la herramienta ve el mismo producto.
2. **Modo claro correcto por defecto** para lectura prolongada.
3. **`tnum` es un requisito, no un detalle:** fechas, valores y plazos.
4. **Un solo acento cromático** es la condición para que los colores de estado
   signifiquen algo sin ambigüedad.

De **Linear** se toma prestado lo que Stripe no documenta: la escala de hairlines
y las reglas de densidad, que es lo que necesita una tabla de requisitos.

## Qué se extendió

El sistema base documenta superficies de marketing y **no define paleta
semántica** — su propia sección `Semantic` lo dice. Eso es precisamente lo que
este producto necesita, así que se añadió:

- **Cuatro estados de veredicto** (`cumple`, `cumple_parcialmente`, `no_cumple`,
  `revision_manual`) con la regla de que *la ausencia de evidencia no es
  incumplimiento*: `revision_manual` es gris, nunca rojo.
- **Tres niveles de evidencia** (cita textual, interpretación del sistema,
  decisión humana), distinguibles sin depender del color.
- **Componentes de producto**: tabla densa, fila de requisito, chip de estado,
  localizador de evidencia, indicador de confianza, banner de aprobación y
  verificación de preparación del expediente.
- **Roles tipográficos** para cita (serif), localizador (mono), etiqueta de
  categoría y encabezado de tabla.

## Accesibilidad verificada

Los cuatro colores de estado se comprobaron contra su propio fondo al 12 %, que
es el emparejamiento real en la interfaz. Los primeros valores elegidos quedaban
**por debajo del umbral AA de 4.5:1** (entre 4.08 y 4.48). Se oscureció cada tono
manteniendo su familia:

| Estado | Sobre su fondo | Sobre blanco |
| --- | --- | --- |
| `cumple` | 5.86:1 | 7.03:1 |
| `cumple_parcialmente` | 4.98:1 | 5.89:1 |
| `no_cumple` | 5.60:1 | 6.79:1 |
| `revision_manual` | 5.08:1 | 6.00:1 |

Ningún estado depende solo del color: todos llevan etiqueta de texto. Alrededor
del 8 % de los hombres tiene alguna deficiencia de visión cromática, y esta
interfaz se usa para decidir si se participa en una licitación.

## Cómo usarlo

Copiar `DESIGN.md` a la raíz del proyecto de interfaz, o indicar al agente que lo
lea antes de generar estilos. El archivo es Markdown con frontmatter YAML: los
tokens son legibles por máquina y las reglas por personas.
