# EAG Ingenieros · MVP de preevaluación de licitaciones

Apoyo a la identificación, revisión y preevaluación de oportunidades de SECOP II. La decisión de participar permanece en manos de EAG.

## Estado

Repositorio en preparación: contiene el plan de implementación y el backlog, **todavía no una aplicación funcional**. La integración y la cobertura documental de SECOP deben comprobarse con una prueba técnica antes de construir el resto.

## Empezar

1. Consultar [contexto y alcance](docs/CONTEXTO.md).
2. Seguir el [backlog ordenado](docs/BACKLOG.md).
3. Copiar el prompt de la issue correspondiente desde [prompts de trabajo](docs/PROMPTS.md).
4. Implementar una issue por rama y PR; probar y revisar antes de pasar a la siguiente.

Las instrucciones breves para los agentes están en [AGENTS.md](AGENTS.md). Los documentos internos, datos reales, credenciales y entregables académicos locales no forman parte del repositorio.

## Spike técnico SECOP II (MVP-02)

El spike aislado consulta únicamente los recursos públicos candidatos de SECOP II,
con límites de muestra y sin persistir documentos descargados. Requiere Python
3.11 o superior y solo usa la biblioteca estándar.

```powershell
python -m unittest discover -s tests -p "test_*.py"
python scripts/secop_spike.py --process-limit 5 --document-limit 5 --page-size 2
```

El segundo comando realiza red y debe ejecutarse de forma explícita. Exporta
metadatos públicos mínimos en `output/secop-spike/`, carpeta ignorada por Git.
Para una comprobación acotada de URLs de documentos descubiertas en la muestra,
añada `--download-documents`; los bytes se leen en memoria, están limitados a
1 MiB por defecto y no se guardan. Un token opcional se entrega únicamente como
`SOCRATA_APP_TOKEN`; nunca se escribe en archivos ni se muestra en consola.

Los resultados, límites y recomendación de la comprobación están en
[docs/SECOP_SPIKE.md](docs/SECOP_SPIKE.md).

## Dirección técnica acordada

Python/FastAPI, React/TypeScript, PostgreSQL y servicios administrados. SECOP II desde la primera versión; carga manual de respaldo, OCR básico y revisión humana antes del informe final. Los proveedores y detalles operativos se concretarán en las issues de arquitectura e infraestructura; no hay recursos de pago provisionados.
