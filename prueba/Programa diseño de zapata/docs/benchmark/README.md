# Material de benchmark — NO es fuente normativa

Esta carpeta guarda documentos de referencia **didáctica** entregados por el usuario. Su
estatus está fijado en `CLAUDE.md` §1:

> Los apuntes de Aragón son **benchmark, no autoridad normativa**. Una discrepancia con
> ellos se documenta; nunca se fuerza el motor para coincidir.

La distinción no es formal. Las fuentes normativas del proyecto son **solo** las de
`docs/normativa/fuentes/` (E.020, E.030, E.050 y E.060). De un documento de esta carpeta
**no** se toma un artículo, un coeficiente, un factor de seguridad ni un criterio para
decidir cómo calcula el motor. Sirve para dos cosas:

1. **contrastar** resultados del motor contra un procedimiento publicado (los benchmarks
   de la Fase 6, `tests/validation/`);
2. **documentar** de dónde vienen convenciones que el proyecto decidió no adoptar —por
   ejemplo el brazo medido desde el lindero de la zapata conectada.

## Documentos

| Archivo | Contenido | Estatus |
|---|---|---|
| `Apuntes CR2-135-169.pdf` | Concreto Armado 2, prof. John P. Aragón Brousset. Cap. 4: muros de sostenimiento (gravedad y en voladizo) y muros de corte. Entregado el 2026-09-18 | benchmark |

sha256 de `Apuntes CR2-135-169.pdf`: `176020920db52633…` (verificado byte a byte contra el
archivo original entregado).

Los apuntes CR2-93-134, usados como benchmark de la zapata conectada (Aragón P1 y P2), están
extraídos en `docs/normativa/aragon_cr2_extracto.txt`. Es material de esta misma naturaleza,
guardado allí por razones históricas.

## Extractos de texto (`texto/`)

`pdftotext -enc UTF-8 -raw`. Auxiliares: ante cualquier duda, el PDF manda.

## Qué dicen los apuntes CR2-135-169 sobre factores de seguridad

Relevante porque se propuso usarlos para cerrar **D10-2b** (factor de seguridad al volteo
con sismo). Lo que dicen, literalmente, en el procedimiento de diseño de muros de
sostenimiento (§4.7.c, repetido para muros de gravedad y en voladizo):

- «Verificación de la estabilidad al deslizamiento: Factor de Seguridad >= 1.5.»
- «Verificación de la estabilidad al volteo: Factor de Seguridad >= 1.5.»

Los ejemplos resueltos aplican esos valores a **empuje de suelo estático** (Rankine, activo
y pasivo). **No hay ningún caso con combinación sísmica** en todo el capítulo.

Por qué esto **no** cierra D10-2b: ver `docs/d10_2b_fs_volteo_sismico.md`.
