# Fuentes normativas del proyecto

**Regla de uso** (instrucción del usuario, 2026-09-13): la información normativa se toma
**solo** de los documentos de `fuentes/`. Si hace falta información que no está en ellos,
se pide al usuario **antes** de suponer nada. No se citan artículos, factores ni
ecuaciones desde memoria ni desde otros documentos del proyecto (manual, apuntes,
auditorías), que son material propio, no fuente.

## Documentos disponibles (`fuentes/`)

Copias íntegras de los archivos entregados por el usuario (comparadas byte a byte con el
original). Se conservan los nombres originales porque el registro
`referencias_e060_e050.md` los cita así.

| Archivo | Contenido real (verificado leyendo la portada) | Edición | sha256 (16) |
|---|---|---|---|
| `Norma E.020 Cargas.pdf` | **E.020 Cargas**, RNE | SENCICO, 1.ª ed. digital, diciembre 2020 | `5ed1079db0f93310` |
| `E.030 Diseño sismorresistente (2026).pdf` | **E.030 Diseño Sismorresistente**, RM 183-2026-VIVIENDA (separata de El Peruano) | 3 de mayo de 2026, **vigente** | `5800f5a314d28d78` |
| `e060 actualizada.pdf` | ⚠️ **NO es E.060.** Contiene **E.030 Diseño Sismorresistente, versión 2025**, firmada el 30.10.2025 | 2025, solo para contraste de versiones | `d16e5923e33ac7c2` |
| `Norma E.050 Suelos y cimentaciones (1).pdf` | **E.050 Suelos y Cimentaciones**, RNE | SENCICO, 1.ª ed. digital, diciembre 2020 | `883616ad21798f5e` |
| `e.060-concreto-armado-sencico.pdf` | **E.060 Concreto Armado**. Portada: «**PROPUESTA DE NORMA E.060 CONCRETO ARMADO 2019**». Capítulos 1–22; 199 páginas con texto | Propuesta 2019. **Fuente E.060 designada por el usuario** (2026-09-14) | `bc4adcb2fc7199ef` |

### Verificación de «e060 actualizada.pdf» (2026-09-14)

El usuario indicó usarlo como E.060 actualizada. Se revisó el documento completo:

- **84 páginas, todas con capa de texto** (ninguna escaneada). El recuento se hizo página
  por página con `pdftotext`.
- **Portada:** «NORMA TÉCNICA E.030 DISEÑO SISMORRESISTENTE 2025», firmada el 30.10.2025.
- **Índice:** capítulos I (Disposiciones generales) a IX (Instrumentación), arts. 1 a 73.
  Es la estructura de E.030.
- **Última página:** Anexo III, contenido mínimo de estudios de microzonificación.
- **Sin contenido de E.060.** Sobre el texto completo del archivo:
  - «resistencia requerida», «1,4 CM», «punzonamiento», «cuantía» y «recubrimiento»: 0
    apariciones;
  - «carga muerta»: 0 apariciones;
  - «E.060»: citada una sola vez, como norma de referencia.

Conclusión: **no se usa como E.060.** Queda como E.030 (2025), solo para contraste de
versiones.

## E.060 (entregada el 2026-09-14)

La fuente E.060 es `e.060-concreto-armado-sencico.pdf`, designada por el usuario. Su
portada la identifica como **propuesta de 2019**.

Las citas de E.060 que ya están en el motor se verificaron en fases anteriores contra
**otra edición**, que no está en esta carpeta. El primer contraste encontró **diferencias
que cambian resultados**: recubrimiento contra el suelo 75 mm frente a 70, tope de
§21.12.3.2 450 mm frente a 400, y alcance de la exención de §10.5.3. Ver
`contraste_e060_motor.md`. Hasta que se decida, el motor no se modifica.

## Extractos de texto (`texto/`)

- `texto/*.txt`: `pdftotext -enc UTF-8 -raw`. **Usar estos.** Conservan cada número de
  artículo junto a su texto.
- `texto/maquetado/*.txt`: `-layout`. En la E.060 los números de sección del margen
  **quedan desalineados** de su párrafo; no usarlos para asociar número y contenido.

Son **auxiliares**:

- la fuente es siempre el PDF;
- tablas, fórmulas, subíndices y separatas a varias columnas pueden salir desordenados o con
  caracteres erróneos;
- antes de citar un artículo, confirmar el texto en el PDF (lectura por páginas);
- si se sustituye un PDF, regenerar su extracto.

## Mapa inicial para los pendientes abiertos

Estado al 2026-09-14:
- Las disposiciones de cargas, combinaciones y estabilidad están **leídas y transcritas**
  en `transcripcion_cargas.md`.
- La E.060 completa, en lo que cita el motor, está **reverificada** en
  `contraste_e060_motor.md`.

| Pendiente | Documento | Dónde buscar |
|---|---|---|
| Contrato de cargas: definiciones de carga muerta y viva (DL-2, DL-4) | E.020 | Art. 2 (definiciones), cap. 2 (carga muerta, arts. 3–5), cap. 3 (carga viva) |
| Presiones de tierra como carga | E.020 | Art. 13 |
| Combinaciones para esfuerzos admisibles (servicio) | E.020 | Art. 19 |
| Estabilidad: volteo y deslizamiento (combinada) | E.020 | Cap. 6, arts. 20–22 |
| Combinaciones factorizadas (§9.2), con variantes por nivel de la acción | E.060 (propuesta 2019) | §9.2, ec. 9-1 a 9-5, 9-2a, 9-3b, 9-4a |
| Zapatas: cargas, peralte, combinadas | E.060 (propuesta 2019) | §15.2, §15.4, §15.7, §15.10 |
| Vigas de cimentación | E.060 (propuesta 2019) | §21.12.3 |
| Reducción sísmica 0,8 en esfuerzos admisibles | E.030 (2026) | Art. 29; art. 62.2 |
| FS de volteo | E.030 (2026) | Art. 64 |
| Elementos de conexión | E.030 (2026) | Art. 65 |
| Cargas de servicio para el FS del suelo | E.050 | Art. 17.1 |
