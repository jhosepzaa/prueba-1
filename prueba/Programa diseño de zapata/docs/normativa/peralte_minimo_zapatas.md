# E.060 §15.7 — Peralte mínimo de zapatas

## Cita textual exacta (verificada en el PDF)

> **15.7 PERALTE MÍNIMO DE LAS ZAPATAS**
> "La altura de las zapatas, medida sobre el refuerzo inferior no debe ser menor de
> 300 mm para zapatas apoyadas sobre el suelo, ni menor de 400 mm en el caso de
> zapatas apoyadas sobre pilotes."

Fuente: `Norma E.060 Concreto armado.pdf`, capítulo 15, artículo 15.7. No hay
figura, nota al pie ni remisión en el entorno del texto que aclare explícitamente
la magnitud geométrica referida.

## Interpretación adoptada

**La disposición se aplica al PERALTE EFECTIVO `d`: se exige `d >= 300 mm`.**

Estado: **interpretación de ingeniería, razonada y documentada — NO es una
certeza normativa.** Adoptada por decisión explícita del usuario tras la
presentación del análisis. Configurable (ver más abajo).

### Fundamento de la interpretación

1. **Lectura literal del texto en español.** La frase "medida **sobre** el
   refuerzo inferior" delimita el origen de la medición: desde el refuerzo
   inferior hacia arriba. Eso excluye el recubrimiento que queda por *debajo* de
   las barras. La magnitud desde el refuerzo inferior hasta la cara superior del
   concreto es precisamente el peralte efectivo `d`.

   Argumento de refuerzo: si la disposición se refiriera a `h_total`, la cláusula
   "medida sobre el refuerzo inferior" sería redundante y no aportaría nada. Una
   norma no incluye cláusulas delimitadoras vacías de contenido.

2. **Consistencia con la práctica constructiva peruana.** Combinada con el
   recubrimiento de 70 mm que la propia E.060 §7.7(a) exige para concreto vaciado
   contra el suelo, esta interpretación implica un peralte total mínimo práctico
   de h ≈ 0,38–0,40 m. Esto es coherente con que en la práctica local no se
   construyen zapatas aisladas de menos de 0,40–0,50 m. La interpretación
   alternativa (`h_total >= 300 mm`) admitiría zapatas de 0,30 m, un espesor que
   la práctica no emplea.

3. **Criterio conservador ante ambigüedad.** Frente a una ambigüedad genuina en
   una disposición de seguridad estructural, la lectura más exigente es la
   defendible.

### Matiz técnico reconocido

`d` se mide hasta el **centroide** del refuerzo inferior, mientras que "sobre el
refuerzo" podría leerse como hasta la **cara superior** de las barras. La
diferencia es db/2 (≈ 8 mm para una barra de 5/8"), despreciable en la práctica,
y usar `d` queda del lado seguro.

## Implementación

`engine/codes/peru/e060_concrete.py` NO codifica esta interpretación como una
constante rígida. Se implementa como parámetro configurable:

```python
class MinDepthInterpretation(str, Enum):
    EFFECTIVE_DEPTH = "EFFECTIVE_DEPTH"  # d >= 300 mm  (POR DEFECTO)
    TOTAL_DEPTH     = "TOTAL_DEPTH"      # h_total >= 300 mm
```

`E060ConcreteCode(min_depth_interpretation=...)` permite cambiarla sin tocar el
resto del motor si en el futuro se confirma la otra lectura.

En ambos modos, el `CalculationTrace` deja constancia explícita de qué
interpretación se usó, para que quede registrado en el reporte de cálculo.

Zapatas sobre pilotes (400 mm) siguen fuera del alcance del MVP.

## Qué cerraría definitivamente este punto

Confirmación contra un comentario oficial de SENCICO, la versión comentada del
RNE, o bibliografía peruana de referencia (p. ej. Blanco Blasco, Ottazzi) que
cite este artículo con su interpretación aceptada en la práctica local.
