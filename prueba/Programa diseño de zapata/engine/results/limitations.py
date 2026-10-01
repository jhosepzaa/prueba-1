"""REGISTRO FORMAL DE LIMITACIONES DEL MOTOR.

Requisito explícito del usuario:
    "No quiero que estos pendientes sean ocultados ni que el programa presente
     como 'cumple normativamente' algo que depende de una funcionalidad aún no
     implementada."

Este módulo es el ÚNICO lugar donde se declaran las limitaciones conocidas. Cada
una lleva un predicado que decide si es RELEVANTE para el cálculo concreto que se
está ejecutando, y las relevantes emiten automáticamente una entrada en el
CalculationTrace. Así una limitación no puede quedar silenciada por olvido: el
motor la arrastra hasta el resultado final.

REGLA DE ORO
------------
Si una limitación es relevante y su ausencia PODRÍA hacer que un diseño
inseguro parezca aceptable, emite WARNING. Nunca se permite que el estado global
sea PASS mientras exista una verificación pendiente que pudiera gobernar.

Si la limitación solo puede hacer el resultado MÁS conservador (p. ej. no aplicar
una reducción permitida), es informativa: no puede producir un falso PASS.

ESTADO TRAS CERRAR L1, L3 y L4
------------------------------
Las tres limitaciones que podían producir un falso PASS quedaron IMPLEMENTADAS y
son ahora verificaciones reales del motor (punzonamiento con transferencia de
momento, estabilidad, desarrollo del refuerzo). Las que restan
(`seismic_reduction_80pct`, `min_depth_interpretation`, `circular_columns`) tienen
can_cause_false_pass=False: solo pueden volver el resultado más conservador.

Por lo tanto PASS ES ALCANZABLE, pero NO automáticamente: depende de que cada
verificación real se ejecute completa y cumpla. En particular, si el usuario no
declara mu y los factores de seguridad, la estabilidad queda NO VERIFICADO y el
estado global no puede ser PASS.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from engine.results.status import CheckStatus

if TYPE_CHECKING:
    from engine.domain.loads import LoadCaseSet
    from engine.domain.soil import SoilProfile


class LimitationKind(str, Enum):
    IMPLEMENTED = "IMPLEMENTADO"
    NOT_IMPLEMENTED = "NO IMPLEMENTADO"
    INTERPRETATION_ADOPTED = "INTERPRETACIÓN ADOPTADA"
    OUT_OF_SCOPE = "FUERA DE ALCANCE"


class EngineLimitation(BaseModel):
    id: str
    title: str
    kind: LimitationKind
    code_reference: str
    description: str
    impact: str = Field(..., description="Qué significa para la validez del resultado")
    # Si otro módulo ya se encarga de degradar el estado por esta limitación, se
    # nombra aquí para no emitir una advertencia duplicada en el trace.
    enforced_by: str | None = None
    # Si es False, la limitación solo puede volver el resultado más conservador,
    # de modo que no puede producir un falso PASS.
    can_cause_false_pass: bool = True


LIMITATION_REGISTRY: list[EngineLimitation] = [
    EngineLimitation(
        id="punching_moment_transfer",
        title="Transferencia de momento en punzonamiento",
        kind=LimitationKind.IMPLEMENTED,
        code_reference="E.060 §11.12.7 (ec. 11-45, 11-46) y ec. 13-1 para γf",
        description=(
            "IMPLEMENTADO en engine/foundation/punching_moment_transfer.py: γf (ec. 13-1), "
            "γv = 1 − γf (ec. 11-45), Jc del perímetro crítico y esfuerzo combinado "
            "vu = Vu/(bo·d) + γv·Mu·c/Jc, contrastado contra φ·Vc/(bo·d) (ec. 11-46)."
        ),
        impact=(
            "Con momento no balanceado, el criterio de §11.12.7 SUSTITUYE al de la resultante "
            "sola. Residual declarado: la expresión de Jc es una derivación geométrica estándar, "
            "no una ecuación numerada de E.060."
        ),
        enforced_by="punching",
        can_cause_false_pass=False,
    ),
    EngineLimitation(
        id="horizontal_forces",
        title="Fuerzas horizontales: deslizamiento y volcamiento",
        kind=LimitationKind.IMPLEMENTED,
        code_reference="E.050 art. 17.1 (cargas de servicio); E.020 arts. 20.1, 21 y 22; E.030 art. 64.2",
        description=(
            "IMPLEMENTADO en engine/soil/stability.py: resultante horizontal, fricción disponible, "
            "FS al deslizamiento, momento volcador/estabilizador y FS al volcamiento en ambos ejes, "
            "para las TRES tipologías. "
            "FS EXIGIDOS: los adopta el programa (D10-2b) y son 1,50 al volteo —también con sismo— "
            "y 1,50 al deslizamiento. NO son los valores de la norma: E.020 art. 21 pide 1,50 al "
            "volteo (coincide), E.030 art. 64.2 pide 1,20 al volteo sísmico y E.020 art. 22.1 pide "
            "1,25 al deslizamiento; en esos dos el criterio adoptado es MÁS ESTRICTO. Un FS "
            "declarado por el proyectista sustituye siempre al adoptado. "
            "μ sigue siendo dato del proyectista (E.020 art. 22.2). La fuerza estabilizante es solo "
            "la carga muerta (E.020 art. 20.1), que exige el modo de cargas por casos. "
            "El momento volcador incluye el término P·offset de la columna descentrada y se toma "
            "como envolvente de las lecturas con carga total y con solo la estabilizante "
            "(FORMULACION_VOLTEO)."
        ),
        impact=(
            "Sin μ el deslizamiento queda NO VERIFICADO. Con combinaciones directas un cumplimiento "
            "de estabilidad queda NO VERIFICADO (la carga total es cota superior de la estabilizante); "
            "un incumplimiento sí es válido. Nunca PASS sin demostrarlo."
        ),
        enforced_by="stability",
        can_cause_false_pass=False,
    ),
    EngineLimitation(
        id="development_length",
        title="Longitud de desarrollo y anclaje del refuerzo",
        kind=LimitationKind.IMPLEMENTED,
        code_reference="E.060 §15.6 → Cap. 12; §12.2.2 Tabla 12.1, §12.2.3 ec. 12-1, §12.5 ganchos",
        description=(
            "IMPLEMENTADO en engine/reinforcement/development_check.py: ld por Tabla 12.1 o por "
            "ec. 12-1 según se cumplan las condiciones simplificadas, con factores ψt, ψe, ψs, λ "
            "y mínimo de 300 mm; longitud disponible = voladizo − recubrimiento; ganchos §12.5 "
            "SOLO si el usuario los declara."
        ),
        impact=(
            "Si ld requerida > disponible, la alternativa es FAIL con el déficit exacto en mm. "
            "Los ganchos nunca se asumen."
        ),
        enforced_by="development",
        can_cause_false_pass=False,
    ),
    EngineLimitation(
        id="seismic_reduction_80pct",
        title="Reducción sísmica al 80% para esfuerzos en el suelo",
        kind=LimitationKind.NOT_IMPLEMENTED,
        code_reference="E.060 §15.2.5 (disposición opcional: 'podrán reducirse al 80%'); E.030 art. 29 y 62.2",
        description=(
            "IMPLEMENTADA con el modo de cargas por casos, sobre la componente CS declarada a nivel "
            "de resistencia (opción del usuario, apagada por defecto), en las TRES tipologías: "
            "zapata aislada (Fase 10B), presiones de suelo de cada zapata de la conectada (D10C-2) "
            "y presiones de suelo de la combinada (docs/reduccion_sismica_combinada.md). Una sola "
            "implementación: `depth_solver.soil_actions`. NO se aplica con combinaciones directas "
            "—no se conoce la componente sísmica—, ni a la estabilidad (E.030 art. 64.2 lo prohíbe "
            "expresamente), ni al despegue del sistema conectado, ni al diseño factorizado. El "
            "rótulo NO IMPLEMENTADO se conserva porque la limitación que se declara es justamente "
            "ese resto, el de los casos en que la reducción permitida no puede aplicarse."
        ),
        impact=(
            "Donde no se aplica, se procede SIN la reducción permitida: resultado más conservador "
            "que el mínimo normativo; no puede producir un diseño inseguro."
        ),
        can_cause_false_pass=False,
    ),
    EngineLimitation(
        id="min_depth_interpretation",
        title="Interpretación de §15.7 (peralte mínimo)",
        kind=LimitationKind.INTERPRETATION_ADOPTED,
        code_reference="E.060 §15.7",
        description=(
            "'Altura medida sobre el refuerzo inferior' se interpreta como el peralte efectivo d "
            "(d >= 300 mm). Es una lectura razonada y documentada, NO una certeza normativa. "
            "Parametrizada en E060ConcreteCode(min_depth_interpretation=...)."
        ),
        impact=(
            "Es la lectura MÁS EXIGENTE de las posibles: exige h total ~0.38 m en vez de 0.30 m. "
            "Puede rechazar zapatas que otra interpretación aceptaría, nunca al revés. Rige en las "
            "TRES tipologías: §15.7 habla de «las zapatas» sin distinguir y §15.10.1 remite a los "
            "requisitos de esta Norma para las que soportan más de una columna (auditoría de "
            "paridad, 2026-09-19)."
        ),
        enforced_by="min_depth",
        can_cause_false_pass=False,
    ),
    EngineLimitation(
        id="connected_uniform_pressure_premise",
        title="Presión uniforme bajo la zapata de lindero de una zapata conectada",
        kind=LimitationKind.NOT_IMPLEMENTED,
        code_reference=(
            "E.060 §15.2.6 (exige evaluar el comportamiento de las vigas de conexión según su "
            "rigidez y la del conjunto suelo-cimentación, SIN prescribir método ni umbral); "
            "§21.12.3.2 fija una dimensión transversal mínima de la viga, no una comprobación "
            "de rigidez del conjunto; §15.10.3 cubre zapatas combinadas y losas, no la conectada"
        ),
        description=(
            "El modelo ARTICULADO supone que la viga de conexión impide el giro de la "
            "zapata de lindero, de modo que su presión de contacto resulta uniforme. La "
            "PREGUNTA sí es normativa —E.060 §15.2.6 manda evaluar la rigidez de las vigas de "
            "conexión y la del conjunto suelo-cimentación—, pero NO existe en las fuentes del "
            "proyecto un criterio con que responderla, y el motor no lo inventa: la premisa se "
            "declara y la verificación queda NO VERIFICADO. La "
            "regla h ≈ L/7 de los apuntes es práctica profesional, no norma, y no puede "
            "producir PASS ni FAIL."
        ),
        impact=(
            "Si la viga no fuera lo bastante rígida, la presión dejaría de ser uniforme y "
            "el qmax real superaría al calculado: PUEDE PRODUCIR UN FALSO PASS. Por eso "
            "la entrada mantiene el estado del sistema fuera de PASS mientras siga sin "
            "resolverse."
        ),
        enforced_by="uniform_pressure_premise",
        can_cause_false_pass=True,
    ),
    EngineLimitation(
        id="connected_uplift_partial_contact",
        title="Contacto unilateral (despegue) en el modelo de cuerpo rígido",
        kind=LimitationKind.NOT_IMPLEMENTED,
        code_reference=(
            "E.060 §15.2.3 — «En el cálculo de las presiones de contacto entre las zapatas "
            "y el suelo solo se aceptará que ocurran compresiones sobre el suelo.»"
        ),
        description=(
            "El modelo de cuerpo rígido distribuye la presión linealmente sobre las dos "
            "huellas. Si el resultado sale negativo en algún punto, parte del apoyo se "
            "levanta y ese campo deja de describir el problema. El motor DETECTA esa "
            "condición y se DETIENE; no redistribuye sobre el área realmente comprimida, "
            "que es un modelo distinto y no está implementado."
        ),
        impact=(
            "No puede producir un falso PASS: el cálculo se interrumpe con un mensaje "
            "explícito en vez de entregar resultados que el propio modelo ya sabe "
            "inválidos. Lo que sí impide es resolver esas geometrías."
        ),
        enforced_by="rigid_pressure",
        can_cause_false_pass=False,
    ),
    EngineLimitation(
        id="connected_beam_bearing_on_soil",
        title="Reacción del terreno bajo la viga de conexión",
        kind=LimitationKind.NOT_IMPLEMENTED,
        code_reference="Sin respaldo normativo: es una decisión de modelación (TBD-C4)",
        description=(
            "Cuando el usuario declara que la viga APOYA sobre el terreno, el motor no "
            "modela esa reacción. La alternativa se declara de forma explícita y "
            "obligatoria, nunca por defecto."
        ),
        impact=(
            "Ignorar el apoyo SOBRESTIMA la transferencia. Como la carga corregida de la "
            "zapata interior es P_int menos la transferencia, la deja menos cargada de lo "
            "que estaría en realidad: la zapata exterior queda del lado seguro, la "
            "interior NO. Puede producir un falso PASS de la zapata interior, y por eso "
            "declarar APOYA_EN_SUELO produce NO VERIFICADO."
        ),
        enforced_by="beam_support_mode",
        can_cause_false_pass=True,
    ),
    EngineLimitation(
        id="connected_footing_stability_composition",
        title="Estabilidad de las zapatas de la conectada con solo carga muerta",
        kind=LimitationKind.NOT_IMPLEMENTED,
        code_reference="E.020 art. 20.1",
        description=(
            "Las zapatas de la conectada se verifican con cargas CORREGIDAS por el reparto. Fase "
            "10C: en el modo por casos la carga corregida conserva su composición por "
            "superposición, y la estabilidad cuenta solo la carga muerta (E.020 art. 20.1). En el "
            "modo directo no hay composición y no se infiere."
        ),
        impact=(
            "Solo en el modo directo: un cumplimiento de estabilidad de esas zapatas queda NO "
            "VERIFICADO; un incumplimiento sí es válido. No puede producir un falso PASS."
        ),
        enforced_by="stability",
        can_cause_false_pass=False,
    ),
    EngineLimitation(
        id="connected_beam_fill_over_span",
        title="Relleno sobre la viga de conexión en el vano libre",
        kind=LimitationKind.NOT_IMPLEMENTED,
        code_reference="Sin respaldo normativo: es una carga derivada de la geometría declarada",
        description=(
            "Con peso propio de viga EXPLICITO, el motor calcula el peso de la viga por "
            "geometría física (Fase 9a) pero NO incluye el relleno que queda sobre ella en el "
            "vano libre cuando su cara superior está por debajo del nivel de desplante. Es "
            "un pendiente declarado, no un peso propio de la viga."
        ),
        impact=(
            "Omitir esa carga subestima las cargas corregidas de las dos zapatas y los "
            "esfuerzos de la viga. Puede producir un falso PASS, y por eso la entrada "
            "`beam_self_weight_mode` queda NO VERIFICADA cuando la geometría declarada deja "
            "relleno sobre la viga."
        ),
        enforced_by="beam_self_weight_mode",
        can_cause_false_pass=True,
    ),
    EngineLimitation(
        id="connected_beam_weight_factoring",
        title="Factor de carga muerta del peso propio de la viga en modo directo",
        kind=LimitationKind.NOT_IMPLEMENTED,
        code_reference=(
            "E.060 §9.2 (el factor de CM cambia entre combinaciones); E.020 art. 2 (el peso "
            "propio es carga muerta)"
        ),
        description=(
            "Con peso propio de viga EXPLICITO y combinaciones FACTORIZADAS escritas a mano "
            "(modo directo), el motor no puede inferir con qué factor de carga muerta se "
            "formaron y no aplica ninguno al peso de la viga. Es TBD-C13. El proyectista "
            "puede declararlo en `beam.self_weight_dead_load_factor`, o usar el modo de "
            "cargas por casos, donde el factor sale de la composición."
        ),
        impact=(
            "Sin factor, el peso de la viga queda subestimado frente a un factor 1,4 y "
            "sobrestimado frente a 0,9 —esto último es lo desfavorable para despegue y "
            "volcamiento—. Puede producir un falso PASS en las verificaciones factorizadas "
            "de las dos zapatas y de la viga, y por eso la entrada `beam_self_weight_mode` "
            "queda NO VERIFICADA mientras el dato no se declare."
        ),
        enforced_by="beam_self_weight_mode",
        can_cause_false_pass=True,
    ),
    EngineLimitation(
        id="circular_columns",
        title="Columnas circulares o de polígono regular",
        kind=LimitationKind.OUT_OF_SCOPE,
        code_reference="E.060 §15.3 (permite tratarlas como cuadradas de área equivalente)",
        description="El modelo Column solo admite secciones rectangular o cuadrada.",
        impact=(
            "No puede producir un falso PASS: una columna circular es rechazada por validación "
            "de entrada antes de calcular nada."
        ),
        can_cause_false_pass=False,
    ),
]


# `enforced_by` nombra un GRUPO de verificaciones, no siempre un id de traza. La estabilidad
# se emite desglosada en tres entradas y el desarrollo, una por dirección. Sin esta tabla, la
# neutralización sería NOMINAL: el catálogo diría estar cubierto por una verificación que no
# existe con ese nombre. Lo detectó `tests/test_auditoria_integridad_final.py`.
# Un id terminado en «_» es un PREFIJO: la presión rígida de la conectada emite una entrada
# por combinación (`rigid_pressure_S1`, `rigid_pressure_U1`). Es la misma convención que usa
# `combined_discards.CATEGORY_BY_CHECK`.
ENFORCED_BY_CHECKS: dict[str, tuple[str, ...]] = {
    "stability": ("sliding", "overturning_x", "overturning_y"),
    "development": ("development_x", "development_y"),
    "punching": ("punching",),
    "min_depth": ("min_depth",),
    "uniform_pressure_premise": ("uniform_pressure_premise",),
    "rigid_pressure": ("rigid_pressure_",),
    "beam_support_mode": ("beam_support_mode",),
    "beam_self_weight_mode": ("beam_self_weight_mode",),
}


def enforcing_checks(limitation: "EngineLimitation") -> tuple[str, ...]:
    """Ids —o prefijos— de traza que hacen visible esta limitación. Vacío si no declara
    ninguna."""
    if not limitation.enforced_by:
        return ()
    return ENFORCED_BY_CHECKS.get(limitation.enforced_by, (limitation.enforced_by,))


def check_matches(patron: str, check_id: str) -> bool:
    """¿Corresponde `check_id` al patrón? Exacto, o por prefijo si termina en «_»."""
    return check_id.startswith(patron) if patron.endswith("_") else check_id == patron


def limitation_by_id(limitation_id: str) -> EngineLimitation:
    for limitation in LIMITATION_REGISTRY:
        if limitation.id == limitation_id:
            return limitation
    raise KeyError(f'Limitación "{limitation_id}" no está en el registro.')


class ApplicableLimitation(BaseModel):
    limitation: EngineLimitation
    reason_relevant: str
    status: CheckStatus


def collect_applicable_limitations(
    load_case_set: "LoadCaseSet", soil: "SoilProfile"
) -> list[ApplicableLimitation]:
    """Decide qué limitaciones son relevantes para ESTE cálculo concreto."""
    applicable: list[ApplicableLimitation] = []

    # --- Reducción sísmica 80%: informativa, solo si hay combinaciones sísmicas ---
    seismic = [c for c in load_case_set.service if c.includes_seismic_loads and c.composition is None]
    if seismic and soil.allow_seismic_reduction_80pct:
        names = ", ".join(c.name for c in seismic)
        applicable.append(
            ApplicableLimitation(
                limitation=limitation_by_id("seismic_reduction_80pct"),
                reason_relevant=(
                    f"Se solicitó la reducción del 80% y las combinaciones [{names}] son sísmicas, "
                    f"pero no puede aplicarse sin descomponer CM/CV/CS. Se procede sin ella "
                    f"(lado conservador)."
                ),
                status=CheckStatus.INFO,
            )
        )

    return applicable
