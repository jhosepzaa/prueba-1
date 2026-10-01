# Pendiente 3 — vista 3D de la combinada y del sistema conectado

Fecha: 2026-09-18. Estado: **cerrado**, sin cambios de baseline.

Cierra la última asimetría de presentación entre las tres tipologías. La zapata aislada ya
tenía visor 3D desde la Fase 1; la combinada y la conectada solo tenían planta y alzado.

---

## 1. Qué se hizo

Un visor genérico, `ui/src/components/BoxScene3D.tsx`, que dibuja **una lista de prismas y
de cotas que el motor ya situó**, y dos adaptadores que solo eligen colores y delegan:

| Componente | Consume | Dibuja |
|---|---|---|
| `CombinedScene3D` | `CombinedSceneDTO` (pendiente 1) | Huella, peralte y arranque de cada columna |
| `ConnectedScene3D` | `ConnectedSceneDTO` (Fase 4G) | Las dos zapatas, la viga y los dos arranques de columna |

**El mismo DTO que alimenta el esquema 2D.** No hay una segunda fuente de posiciones que
pueda divergir de la primera: si el 2D y el 3D discreparan, uno de los dos estaría
recalculando, que es justo lo que `scene_dto.py` prohíbe.

## 2. Lo que NO dibujan, y por qué

**El armado.** El motor resuelve posiciones de barra solo para la zapata aislada
(`FootingRebarGeometry`), que por eso conserva su visor propio, `FootingScene3D`. Para la
combinada y la conectada no las resuelve, y dibujar un armado inventado sería exactamente lo
que la regla de visualización prohíbe. Hay un test que lo fija: los tres archivos nuevos no
pueden contener `cylinderGeometry`, `BarOut` ni `bars`.

En la conectada, además, **la cota vertical de la viga respecto de las zapatas sigue siendo
una convención de dibujo**: el motor no la calcula. Lo dice `scope_note`, que viaja con la
escena y se muestra bajo el visor.

## 3. El estado viaja con el dibujo

Un dibujo limpio se lee como un diseño conforme. Por eso el visor muestra, junto al modelo:

- el `CheckStatus` **crudo**, que es el que usan los criterios;
- el **rótulo** del vocabulario único (pendiente 8);
- el aviso de «no puede presentarse como conforme» cuando la alternativa no es PASS ni INFO
  —relevante desde la decisión 6, que permite a la combinada devolver alternativas NO
  VERIFICADAS—;
- en la conectada, los TBD abiertos de la alternativa.

## 4. Efecto

**Ninguno sobre resultados.** Es presentación: no toca el motor, ni la API, ni ningún
criterio. `tests/freeze` sin cambios.

El catálogo de tipologías pasa a declarar `vista_3d: True` en las tres, y la diferencia
conocida `PRESENTACION_COMBINADA` queda cerrada: la paridad de presentación está completa.

## 5. Tests

`tests/test_vista_3d_pendiente3.py` (10 tests): los visores existen y consumen el DTO del
motor; no recalculan geometría ni ingeniería; no inventan armado; la lógica del visor está
en un solo sitio —los adaptadores no pueden contener `<Canvas`, `OrbitControls` ni
`boxGeometry`—; el estado y su aviso llegan hasta el visor; las vistas de resultados lo
**montan** de verdad; y el catálogo lo declara.

**Seis mutaciones deliberadas, seis detectadas.** Una —comentar el montaje del visor— pasó
desapercibida en el primer intento porque el nombre seguía apareciendo dentro del comentario;
el test se reforzó para exigir JSX vivo y no una simple mención.
