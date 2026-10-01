# AGENTS.md — Diseño de cimentaciones de concreto armado (RNE Perú)

> **Las reglas del proyecto viven en [`CLAUDE.md`](CLAUDE.md). Este archivo no las
> repite: las señala.**
>
> Hasta el 2026-09-25 aquí había una copia completa del reglamento, y se quedó atrás:
> fechada el 14-09, seguía afirmando que las reglas de aceptación eran «distintas por
> tipología; no alinearlas sin decisión» cuando la decisión 6 (20-09) las unificó en
> `NO_FAIL` para las tres, y le faltaban seis apartados enteros —paridad entre
> tipologías, contacto unilateral, presión de contacto, estabilidad—. Dos archivos de
> reglas que se contradicen son peores que uno solo: quien leyera este trabajaría con
> criterios derogados. Por eso ahora hay una sola fuente.
>
> **Si algo de este archivo discrepa de `CLAUDE.md`, manda `CLAUDE.md`.**

## Qué leer, y en qué orden

1. [`CLAUDE.md`](CLAUDE.md) — reglas permanentes: propósito, arquitectura, cuándo
   detenerse, estados, trazabilidad, normativa, cargas, baselines, reglas por tipología.
2. [`docs/estado_proyecto.md`](docs/estado_proyecto.md) — estado vivo: fases cerradas,
   pendientes abiertos y qué decisiones esperan al proyectista.
3. El documento de la fase concreta que se vaya a tocar, enlazado desde la tabla de fases.

## Lo que no se puede ignorar aunque no se lea nada más

Estas cuatro reglas se repiten aquí a propósito: si alguien llega a este archivo y no
abre ningún otro, tiene que salir sabiendo esto.

1. **No inventar normativa ni parámetros geotécnicos.** Ni artículos, ni coeficientes, ni
   ecuaciones, ni factores de seguridad, ni μ, ni k_s. Lo que no sea verificable contra
   las fuentes de `docs/normativa/fuentes/` se declara TBD o NO VERIFICADO. Lo que va
   entre «» tiene que ser literal: una paráfrasis entrecomillada es una cita inventada
   aunque diga lo mismo (`CLAUDE.md` §1 y §8).

2. **Hay decisiones que no se toman solas.** Si un cambio puede alterar una ecuación, una
   hipótesis física, un criterio normativo, el estado de una verificación, un resultado
   numérico o el vocabulario de estados, se para, se explica con evidencia, se muestran
   las alternativas y se pide aprobación. Un encargo «autónomo» o un «no te detengas» NO
   anula esa parada (`CLAUDE.md` §3).

3. **Los baselines no se tocan automáticamente.** `tests/freeze/baseline.json` y
   `baseline_connected.json` solo se regeneran caso por caso, con diff revisado y
   aprobación expresa. Nunca en bloque para que pase la suite, y nunca ampliando
   tolerancias (`CLAUDE.md` §11).

4. **La incertidumbre no se convierte en PASS.** Un WARNING no asciende a PASS, un NO
   VERIFICADO no se presenta como conforme, y «aceptada» no significa «cumple»
   (`CLAUDE.md` §5 y §18).

## Entorno

Windows, `py -3`, desde la raíz del proyecto. Tests: `py -3 -m pytest -q`. Interfaz:
`cd ui && npm run build` con `NODE_OPTIONS=--max-old-space-size=4096`. El detalle está en
`CLAUDE.md` §15.
