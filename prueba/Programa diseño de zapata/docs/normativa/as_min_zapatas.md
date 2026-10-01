# Acero mínimo de flexión en zapatas — E.060 §9.7 (vía §10.5.1 y §10.6)

Documentado antes de codificar, según lo solicitado. Todas las citas están
verificadas contra el texto extraído del PDF (`pdftotext -layout`), no de memoria.

## 1. Artículo exacto

Tres artículos encadenados, en este orden de lectura:

1. **§10.5.1** (p.77): *"En cualquier sección de un elemento estructural
   **- excepto en zapatas y losas macizas -** sometido a flexión, donde por el
   análisis se requiera refuerzo de acero en tracción, el área de acero que se
   proporcione será la necesaria para que la resistencia de diseño de la sección
   sea por lo menos 1,2 veces el momento de agrietamiento... (Mn ≥ 1,2 Mcr)"*
   → Las zapatas quedan **explícitamente excluidas** de la regla de As_min basada
   en el momento de agrietamiento (Mcr) que sí aplica a vigas y losas nervadas.

2. **§10.6** (p.77-78): *"Para losas estructurales y zapatas de espesor uniforme,
   el acero mínimo en la dirección de la luz debe ser el requerido por 9.7."*
   → Remite directamente a la cuantía de retracción y temperatura del §9.7 como el
   As_min aplicable a zapatas.

3. **§9.7** "Refuerzo por cambios volumétricos" (p.72): da la cuantía mínima
   ρ_min = As/(b·h) según el tipo de acero:

   | Tipo de barra | ρ_min |
   |---|---|
   | Barras lisas | 0,0025 |
   | Barras corrugadas con fy < 420 MPa | 0,0020 |
   | Barras corrugadas o malla electrosoldada con fy ≥ 420 MPa | 0,0018 |

   Espaciamiento máximo del refuerzo: ≤ 3h, sin exceder 400 mm.

## 2. Sección a la que se aplica

Zapatas de **espesor uniforme** (peralte constante, sin escalones ni inclinación).
Es el único caso del MVP — zapatas escalonadas/inclinadas (§15.9) quedan fuera de
alcance.

## 3. Área sobre la cual se calcula

Área **bruta** de la sección de concreto en la dirección considerada:

```
As_min = ρ_min · b · h
```

donde `b` es el ancho total de la franja perpendicular a la dirección de armado
(para armado en X: b = B; para armado en Y: b = L) y `h` es el **peralte total**
de la zapata — **no** el peralte efectivo `d`. Esto es consistente con que §9.7 es
una cuantía de retracción/temperatura (gobernada por el volumen bruto de concreto),
no una cuantía de resistencia a flexión (que usaría `d`).

## 4. Dirección en la que se aplica

**Ambas direcciones de armado de la zapata (X e Y), de forma independiente.**

El texto de §10.6 agrupa "losas estructurales y zapatas" y habla de "la dirección
de la luz" en singular, redactado pensando en losas armadas en una dirección. Una
zapata aislada trabaja en voladizo a flexión en **dos** direcciones simultáneas
respecto a la columna (X e Y), por lo que se interpreta que cada una de esas dos
direcciones es, a los efectos de §10.6, "la dirección de la luz" correspondiente.
Se aplica entonces ρ_min·B·h en la dirección corta y ρ_min·L·h en la dirección
larga, cada una calculada de forma independiente.

**Nota de interpretación (no un TBD normativo, pero sí una lectura razonada del
texto):** esta extensión de "una dirección" a "dos direcciones aplicadas cada una
independientemente" es la práctica extendida en el diseño de zapatas y es
consistente con que §15.4.4 ya reconoce expresamente que las zapatas rectangulares
se arman en dos direcciones con reglas de distribución propias. No se encontró en
el texto revisado un artículo que lo contradiga.

El párrafo final de §10.6 ("cuando el acero mínimo se distribuya en las dos caras
de la losa, la cuantía en la cara de tracción no será menor de 0,0012") **no aplica**
al caso base del MVP, porque el armado de la zapata se modela como una sola parrilla
inferior (una sola cara), no repartida entre cara superior e inferior.

## 5. Relación con el refuerzo principal de flexión

El As_min de §9.7 actúa como **piso absoluto** del acero que se coloca en cada
dirección, no como un refuerzo adicional independiente:

```
As_diseño(dirección) = max( As_requerido_por_flexión(§15.4, Mu en cara de columna),
                             As_min(§9.7) )
```

No se aplica el criterio "1/3 superior al requerido por análisis" del §10.5.3,
porque esa cláusula pertenece al bloque de §10.5 del cual las zapatas están
excluidas por §10.5.1.

## 6. Dependencia respecto de fy

ρ_min es función escalonada de `fy` y del tipo de barra (no una constante fija):

```python
def rho_min_9_7(fy_MPa: float, bar_type: Literal["corrugada", "lisa"]) -> float:
    if bar_type == "lisa":
        return 0.0025
    return 0.0018 if fy_MPa >= 420.0 else 0.0020
```

El motor debe leer `fy` del material de acero asignado a la zapata para elegir el
valor correcto — **nunca** hardcodear 0.0018 como constante global, porque deja de
ser válido si el proyecto usa acero con fy < 420 MPa.

## Estado

Sin TBD. Los tres artículos citados definen la regla completa sin ambigüedad de
lectura, a diferencia del caso de §15.7 (peralte mínimo). Lista para convertirse en
código.
