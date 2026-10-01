# Unidades dinámicas y consistentes en toda la aplicación (2026-09-23)

## 1. Objetivo

Que el proyectista elija, **en cada tipología**, las unidades en que escribe y en que lee
sus datos, y que esa elección sea **una preferencia de presentación**: el valor físico del
dato no cambia al cambiar de unidad.

Caso de referencia del encargo:

```
f'c = 21 MPa   →  (cambia la unidad a kg/cm²)  →  214,14 kgf/cm²
214,14 kgf/cm² →  (vuelve a MPa)               →  21 MPa
```

No 210: 210 kgf/cm² es **otro** hormigón (20,594 MPa). El programa no ajusta a valores
comerciales.

## 2. Qué había antes

- **La aislada** tenía desplegables de unidades, pero al cambiarlos **solo cambiaba el
  rótulo**: el número se quedaba igual y pasaba a interpretarse en la nueva unidad. Escribir
  21 MPa y cambiar a kgf/cm² dejaba un f'c de 21 kgf/cm² — 2,06 MPa — sin avisar.
- **La combinada y la conectada** no exponían unidades, ni materiales, ni suelo, ni las
  disposiciones de §15.2. Calculaban siempre con los valores del ejemplo (f'c 21 MPa,
  q<sub>adm</sub> 150 y 250 kPa). El motor y la API sí los aceptaban: el hueco era de
  pantalla.
- **La memoria** se emitía siempre en SI, dijera lo que dijera el usuario.

## 3. Decisiones

### D1 — La conversión sigue estando en el motor

`engine/units/unit_registry.py` era la única tabla de equivalencias y lo sigue siendo. Se le
añadieron la dirección inversa (`from_si`), la conversión entre dos unidades (`convert`) y
el redondeo de presentación. La interfaz **no declara ningún factor**.

Cuando el usuario cambia una unidad, la interfaz manda la petición entera a
`POST /api/units/rewrite` y la recibe reescrita. La aritmética ocurre en Python, cubierta
por tests. Para **presentar resultados** la interfaz sí multiplica, pero por el factor que
el propio motor le entrega en `/api/reference` (`to_si` de cada unidad): ninguna
equivalencia vive en la interfaz.

### D2 — Redondeo declarado: 6 cifras significativas

21 MPa son 214,140404725… kgf/cm². Se convierte con el factor exacto y se redondea a
**6 cifras significativas**; se muestra y se calcula ESE valor. Lo que se ve es lo que se
usa.

- Error relativo del redondeo: **≤ 5·10⁻⁶** (cinco partes por millón).
- La ida y vuelta es estable: 21 → 214,14 → 21.
- `DISPLAY_SIGNIFICANT_DIGITS` en `unit_registry.py`, con su justificación.

Se descartaron las otras dos opciones: mostrar el valor íntegro (214,14040472536258 es
ilegible) y guardar uno distinto del mostrado (una diferencia silenciosa entre lo visible y
lo calculado es justo lo que este programa evita).

### D3 — Qué magnitudes elige el usuario

Las seis del registro: fuerza, momento, presión, resistencia, longitud y peso unitario.

**No** se convierten, y se declara por qué: volúmenes (m³), áreas de acero (cm²), masas
(kg), diámetros de barra y recubrimientos (mm). Son unidades de obra, no hay desplegable que
las cambie y medir el concreto en cm³ no ayuda a nadie.

### D4 — La traza se queda en SI

La traza no es una tabla de resultados: es el registro del cálculo, con su ecuación
simbólica, su sustitución numérica y su unidad. Reescribir los números de una sustitución
daría un texto que ya no es el cálculo ejecutado, y además `tests/freeze` congela esos
valores como contrato (CLAUDE.md §11).

La memoria **lo dice** en lugar de disimularlo (`TRACE_IN_SI_NOTE`).

### D5 — Decimales: solo se ajustan en longitud

Los decimales que pide cada llamada están pensados para la unidad SI. En centímetros o
milímetros sobran cifras —2,50 m escritos «250.00 cm» fingen precisión de centésima de
milímetro—, así que se descuenta un decimal por orden de magnitud sin perder precisión
absoluta.

En las demás magnitudes no se toca: recortar un decimal en kgf/cm² convertiría un f'c
declarado de 211,5 en «212», y un dato del proyectista se escribe como lo escribió él.

## 4. Implementación por capas

| Capa | Archivo | Qué hace |
|---|---|---|
| Motor | `engine/units/unit_registry.py` | `to_si`, `from_si`, `convert`, `round_significant`, `convert_for_display`; `KIND_TABLES`, `SI_UNITS`; `available_units()` entrega ahora el factor `to_si` de cada unidad |
| Motor | `engine/reports/report_units.py` | `ReportUnits`: cómo se escribe cada número de la memoria; nota de unidades y declaración de la traza en SI |
| API | `api/unit_fields.py` | Mapa **declarativo** de qué campo de cada petición es de qué magnitud, más la lista de exentos con su motivo; `rewrite_units()` |
| API | `api/server.py` | `POST /api/units/rewrite`; `rounding_note` en `/api/reference`; las cuatro memorias reciben `ReportUnits` |
| UI | `ui/src/lib/units.ts` | Formateador de presentación: convierte con los factores del motor y rotula |
| UI | `ui/src/components/SharedInputs.tsx` | Bloques comunes: unidades, materiales y suelo, usados por las cuatro pantallas |
| UI | paneles y vistas de resultados | Selector de unidades en las cuatro tipologías; tablas y fichas rotuladas y convertidas |

### El mapa de campos y su auditoría

El conocimiento de «qué campo es una longitud» estaba disperso en cada llamada a
`length_to_m(...)` de `api/mapping.py` y `api/server.py`. Ahora está enumerado en un solo
sitio y, sobre todo, **auditado**: `tests/test_api_unit_fields.py` recorre los campos
numéricos de las cuatro peticiones y exige que cada uno esté clasificado —con magnitud o
con motivo de exención—. Un campo nuevo sin clasificar rompe el test en vez de convertirse
en silencio o quedarse sin convertir.

## 5. Defecto encontrado y corregido

`api/server.py`: el **peso unitario del concreto de la viga de conexión** se pasaba sin
convertir (`concrete_unit_weight_kNm3=request.beam.concrete_unit_weight_kNm3`), mientras que
el de `materials` sí pasaba por el registro. Un peso declarado en tonf/m³ se leía como
kN/m³ y el peso propio de la viga salía 9,8 veces menor.

Con las unidades por defecto (kN/m³) el factor es 1, de modo que **ningún caso congelado
cambia**; se comprobó con la suite completa.

## 6. Verificación

- `tests/test_unit_conversion_bidirectional.py` — ida y vuelta en todas las unidades,
  valores de ingeniería calculados a mano, cota del redondeo, catálogo con factores.
- `tests/test_api_unit_fields.py` — auditoría del mapa; **invariante del encargo**: los
  objetos que llegan al motor desde la petición original y desde la reescrita son los mismos
  dentro de 1·10⁻⁵.
- `tests/test_report_units.py` — la memoria escribe los datos convertidos, en SI sigue
  saliendo como antes, y declara que la traza va en SI.
- Suite completa: **2036 pasan**, congelamiento incluido.
- Comprobado en el navegador: 21 MPa → 214,14 kgf/cm² → 21 MPa; 0,4 m → 40 cm → 0,4 m;
  150 kPa → 1,52957 kgf/cm²; resultados y memoria rotulados y convertidos.

## 7. Lo que este trabajo NO resuelve

- Las cuatro decisiones de ingeniería abiertas de la combinada siguen abiertas
  (`docs/validacion_aragon_3_5_combinada.md`).
- La traza sigue en SI, por D4.
- No hay unidad elegible para volumen, área de acero ni masa (D3).
