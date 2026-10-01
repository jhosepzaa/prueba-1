"""Generación de alternativas de zapata combinada — Fase 2.

CÓMO SE PARAMETRIZA LA BÚSQUEDA — Y POR QUÉ NO CON DESPLAZAMIENTOS
==================================================================
`ColumnPlacement` sitúa la columna por su desplazamiento respecto del CENTRO de la
zapata. Es lo correcto para verificar una geometría dada, pero no sirve para
BARRER geometrías: al variar la longitud, un desplazamiento constante deja de
describir la misma estructura. Es la limitación que la Fase 1B dejó declarada.

Aquí se parametriza por lo que de verdad está fijo en el problema real:

  - la SEPARACIÓN entre ejes de columna, que la impone la estructura;
  - la distancia del EXTREMO de la zapata al eje de la primera columna, que la
    impone el lindero (para una columna de límite de propiedad vale la mitad de su
    ancho, porque la cara queda al ras).

Con esos dos datos fijos, barrer la longitud desplaza el otro extremo y con él el
voladizo libre — que es exactamente el grado de libertad que tiene el proyectista.
Los desplazamientos respecto del centro se recalculan para cada longitud.

CRITERIO DE ACEPTACIÓN — NO_FAIL (decisión 6)
=============================================
Se acepta toda geometría cuyo estado no sea FAIL: es la máquina de estados del proyecto
(`CheckStatus.discards`) y la misma regla que ya usan la zapata aislada y la conectada.
Hasta esta decisión la combinada exigía PASS o INFO, de modo que un WARNING o un NO
VERIFICADO contaban como descarte. Esa asimetría —`ACEPTACION_COMBINADA` en el catálogo de
tipologías— tenía una consecuencia que no era de presentación: desde D4, con fuerzas
horizontales la estabilidad de la combinada queda NO VERIFICADA en TODOS los peraltes, así
que el barrido descartaba la tipología entera en cuanto había sismo o viento.

ACEPTAR NO ES APROBAR. Igual que en la conectada, el conjunto separa lo que sobrevive al
barrido de lo que puede informarse como conforme: `accepted_and_compliant` son las
alternativas PASS o INFO, y `not_verified` / `accepted_with_findings` las que el motor
conserva pero no puede declarar conformes. La nota de búsqueda lo dice cuando ocurre.

NADA DE ESTE MÓDULO ES NORMATIVO. Es estrategia de búsqueda.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from engine.codes.base import IConcreteCode
from engine.domain.column import Column
from engine.domain.column_placement import ColumnPlacement
from engine.domain.combined_layout import ColumnOnFooting, CombinedFootingLayout
from engine.domain.loads import LoadCaseSet
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.site_limits import SiteLimits
from engine.domain.soil import SoilProfile
from engine.foundation.combined_solver import CombinedFootingResult, solve_combined_footing
from engine.optimization.combined_discards import CombinedDiscardSummary
from engine.optimization.combined_metrics import compute_combined_metrics
from engine.optimization.metrics import AlternativeMetrics
from engine.optimization.scoring import ScoreWeights
from engine.reinforcement.face_reinforcement import TopCoverDeclaration
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import ContactPressureModel

# Tope de geometrías por barrido, igual criterio que en el motor de zapata aislada:
# evita que una entrada mal acotada dispare un cálculo interminable.
MAX_COMBINED_GEOMETRIES = 3000


class ColumnSpec(BaseModel):
    """Una columna del conjunto, situada por su distancia a la PRIMERA columna."""

    label: str = Field(..., min_length=1)
    column: Column
    distance_from_first_m: float = Field(
        ..., ge=0.0, description="Distancia entre ejes desde la primera columna [m]"
    )
    loads: LoadCaseSet
    transverse_offset_m: float = Field(
        default=0.0,
        description="Desplazamiento respecto del eje transversal de la zapata [m]",
    )


class CombinedSearchParameters(BaseModel):
    """Rango de geometrías a explorar."""

    length_min_m: float = Field(..., gt=0)
    length_max_m: float = Field(..., gt=0)
    length_step_m: float = Field(default=0.10, gt=0)

    width_min_m: float = Field(..., gt=0)
    width_max_m: float = Field(..., gt=0)
    width_step_m: float = Field(default=0.10, gt=0)

    h_min_m: float = Field(..., gt=0)
    h_max_m: float = Field(..., gt=0)
    h_step_m: float = Field(default=0.05, gt=0)

    first_column_edge_distance_m: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Distancia del extremo de la zapata al eje de la primera columna. Para una "
            "columna de límite de propiedad es la mitad de su ancho: la cara queda al ras. "
            "None (2026-09-28) = la decide el programa para cada longitud: centra la "
            "resultante de la combinación permanente y respeta los linderos."
        ),
    )
    site_limits: SiteLimits | None = Field(
        default=None,
        description="Linderos del terreno. None = sin límites (comportamiento anterior).",
    )
    longitudinal_direction: str = Field(
        default="X", description='"X" o "Y": dirección en la que se alinean las columnas'
    )

    @model_validator(mode="after")
    def _rangos_coherentes(self) -> "CombinedSearchParameters":
        for lo, hi, nombre in (
            (self.length_min_m, self.length_max_m, "longitud"),
            (self.width_min_m, self.width_max_m, "ancho"),
            (self.h_min_m, self.h_max_m, "peralte"),
        ):
            if lo > hi:
                raise ValueError(f"Rango de {nombre} invertido: {lo} > {hi}.")
        if self.longitudinal_direction not in ("X", "Y"):
            raise ValueError('longitudinal_direction debe ser "X" o "Y".')
        return self


class CombinedAlternative(BaseModel):
    id: str
    length_m: float
    width_m: float
    h_m: float
    result: CombinedFootingResult
    # 2026-09-28: DÓNDE quedó la zapata. Con la posición automática y los linderos cambia
    # de una planta a otra; la escena y la memoria reconstruyen el layout con estos dos.
    first_column_edge_distance_m: float = 0.0
    transverse_shift_m: float = 0.0
    # Mismo tipo que la zapata aislada: es lo que permite reutilizar `scoring`,
    # `pareto` y `ranker` sin tocarlos.
    metrics: AlternativeMetrics

    @property
    def concrete_volume_m3(self) -> float:
        return self.metrics.concrete_volume_m3


class CombinedAlternativeSet(BaseModel):
    valid: list[CombinedAlternative] = []
    discarded_count: int = 0
    evaluated_count: int = 0
    truncated: bool = False
    search_note: str = ""
    # --- Fase 2: motivos de descarte normalizados (no cambian ningún criterio) ---
    unresolved_count: int = Field(
        default=0,
        description=(
            "Geometrías evaluadas que el solver no pudo resolver (p. ej. peralte que no admite "
            "los recubrimientos). evaluated_count = aceptadas + discarded_count + unresolved_count."
        ),
    )
    discard_summary: CombinedDiscardSummary = Field(default_factory=CombinedDiscardSummary)

    # --- Decisión 6: las particiones de lo ACEPTADO, explícitas -------------------
    # Son propiedades y no campos nuevos: `valid` es contrato existente (API, informes y
    # tests) y no se renombra. `accepted` es su nombre honesto —«sobrevive al barrido»—,
    # que es lo que el vocabulario del proyecto pide (CLAUDE.md §5).

    @property
    def accepted(self) -> list[CombinedAlternative]:
        """Alternativas que ninguna verificación IMPLEMENTADA descarta. No son conformes
        por el hecho de estar aquí: consúltese el estado de cada una."""
        return self.valid

    @property
    def not_verified(self) -> list[CombinedAlternative]:
        """Aceptadas sobre las que el motor NO puede pronunciarse. Hoy la única causa en la
        combinada es la estabilidad no implementada con fuerzas horizontales (D4)."""
        return [a for a in self.valid if a.result.overall_status is CheckStatus.NOT_VERIFIED]

    @property
    def accepted_with_findings(self) -> list[CombinedAlternative]:
        """Aceptadas en las que algo de lo implementado salió con reserva (WARNING). No es
        lo mismo «no puedo pronunciarme» que «me pronuncio, y con reservas»."""
        return [a for a in self.valid if a.result.overall_status is CheckStatus.WARNING]

    @property
    def accepted_and_compliant(self) -> list[CombinedAlternative]:
        """Las únicas presentables como conformes: PASS o INFO.

        La combinada no lleva `open_tbds` por alternativa —a diferencia de la conectada—,
        de modo que el pendiente abierto que la afecta se manifiesta como estado NO
        VERIFICADO de la propia alternativa, y el estado basta como criterio."""
        return [a for a in self.valid
                if a.result.overall_status in (CheckStatus.PASS, CheckStatus.INFO)]

    def status_summary(self) -> dict[str, int]:
        """Cuántas aceptadas hay en cada estado: lo que el informe debe mostrar en vez de
        un recuento pelado de «alternativas encontradas»."""
        conteo: dict[str, int] = {}
        for a in self.valid:
            clave = a.result.overall_status.value
            conteo[clave] = conteo.get(clave, 0) + 1
        return conteo


def _frange(lo: float, hi: float, step: float) -> list[float]:
    valores, x = [], lo
    while x <= hi + 1e-9:
        valores.append(round(x, 6))
        x += step
    return valores


# =========================================================================
# Colocación de la zapata dentro de los linderos (2026-09-28)
# =========================================================================
#
# HEURÍSTICA DE BÚSQUEDA, no criterio de diseño. Para cada longitud (y cada ancho) se
# prueba UNA posición: la que centra la resultante de la combinación permanente —el mismo
# criterio de predimensionamiento que `length_to_center_resultant`—, recortada para que la
# zapata cubra todas las columnas y no salga del terreno. Una columna al lindero queda así
# al ras. La posición elegida se verifica después con los mismos criterios que cualquier
# otra; centrar no es una exigencia normativa (E.060 §15.2 pide ausencia de tracciones y
# presión admisible, y eso se comprueba para TODAS las combinaciones).

_TOL_M = 1e-9


def _semi_dimensiones(spec: ColumnSpec, direccion: str) -> tuple[float, float]:
    """(media dimensión longitudinal, media dimensión lateral) de la columna."""
    if direccion == "X":
        return spec.column.bx_m / 2.0, spec.column.by_m / 2.0
    return spec.column.by_m / 2.0, spec.column.bx_m / 2.0


def _combinacion_permanente(specs: list[ColumnSpec]) -> int:
    """Índice de la primera combinación de servicio sin sismo ni viento; si no la hay, 0.

    Centrar es un criterio de estado PERMANENTE: el sismo se invierte, y centrar para un
    sentido descentra el otro. Es el mismo criterio que usa la ayuda de predimensionamiento
    de la API."""
    for i, combo in enumerate(specs[0].loads.service):
        if not combo.includes_seismic_loads and not combo.includes_wind_loads:
            return i
    return 0


def longitudinal_window(
    specs: list[ColumnSpec], length_m: float, direccion: str, limites: SiteLimits | None
) -> tuple[float, float]:
    """Intervalo [s_min, s_max] de la posición del extremo inicial de la zapata, medida
    desde el eje de la PRIMERA columna (negativa si la zapata sobresale hacia atrás), que
    cubre todas las columnas y respeta los linderos longitudinales. Vacío si s_min > s_max."""
    s_max = min(sp.distance_from_first_m - _semi_dimensiones(sp, direccion)[0] for sp in specs)
    s_min = max(sp.distance_from_first_m + _semi_dimensiones(sp, direccion)[0] for sp in specs) - length_m
    if limites is not None and limites.start_clearance_m is not None:
        primera = specs[0]
        s_min = max(s_min, -(_semi_dimensiones(primera, direccion)[0] + limites.start_clearance_m))
    if limites is not None and limites.end_clearance_m is not None:
        ultima = max(specs, key=lambda sp: sp.distance_from_first_m)
        fin = ultima.distance_from_first_m + _semi_dimensiones(ultima, direccion)[0] + limites.end_clearance_m
        s_max = min(s_max, fin - length_m)
    return s_min, s_max


def auto_first_column_edge_distance(
    specs: list[ColumnSpec], length_m: float, direccion: str, limites: SiteLimits | None
) -> float | None:
    """Distancia del extremo de la zapata al eje de la primera columna, elegida por el
    programa, o None si con esta longitud la zapata no cabe en el terreno."""
    s_min, s_max = longitudinal_window(specs, length_m, direccion, limites)
    if s_min > s_max + _TOL_M:
        return None
    i = _combinacion_permanente(specs)
    P = [sp.loads.service[i].P_kN for sp in specs]
    M = [
        (sp.loads.service[i].Mx_kNm if direccion == "X" else sp.loads.service[i].My_kNm)
        for sp in specs
    ]
    P_total = sum(P)
    if P_total > 0:
        x_R = (sum(p * sp.distance_from_first_m for p, sp in zip(P, specs)) + sum(M)) / P_total
        preferida = x_R - length_m / 2.0
    else:
        preferida = s_min
    s0 = min(max(preferida, s_min), s_max)
    return max(-s0, 0.0) if -s0 > -_TOL_M else None


def transverse_window(
    specs: list[ColumnSpec], width_m: float, direccion: str, limites: SiteLimits | None
) -> tuple[float, float]:
    """Intervalo del eje lateral de la zapata respecto de la línea de referencia de las
    columnas (la de `transverse_offset_m`) que las cubre y respeta los linderos laterales."""
    caras_neg = min(sp.transverse_offset_m - _semi_dimensiones(sp, direccion)[1] for sp in specs)
    caras_pos = max(sp.transverse_offset_m + _semi_dimensiones(sp, direccion)[1] for sp in specs)
    t_min = caras_pos - width_m / 2.0
    t_max = caras_neg + width_m / 2.0
    if limites is not None and limites.side_neg_clearance_m is not None:
        t_min = max(t_min, caras_neg - limites.side_neg_clearance_m + width_m / 2.0)
    if limites is not None and limites.side_pos_clearance_m is not None:
        t_max = min(t_max, caras_pos + limites.side_pos_clearance_m - width_m / 2.0)
    return t_min, t_max


def auto_transverse_shift(
    specs: list[ColumnSpec], width_m: float, direccion: str, limites: SiteLimits | None
) -> float | None:
    """Desplazamiento lateral del eje de la zapata respecto de la línea de las columnas.

    Sin linderos laterales vale 0: la zapata queda donde la declara `transverse_offset_m`,
    exactamente como antes. Con linderos, lo más cerca de 0 que permitan. None si no cabe."""
    if limites is None or not limites.has_side_limits:
        # Sin linderos laterales no se corre nada: si una columna no cabe con este ancho,
        # lo decide `build_layout` como siempre. Correr la zapata aquí cambiaría resultados
        # de peticiones que no declaran linderos.
        return 0.0
    t_min, t_max = transverse_window(specs, width_m, direccion, limites)
    if t_min > t_max + _TOL_M:
        return None
    return min(max(0.0, t_min), t_max)


def build_layout(
    specs: list[ColumnSpec],
    length_m: float,
    width_m: float,
    first_column_edge_distance_m: float,
    longitudinal_direction: str = "X",
    transverse_shift_m: float = 0.0,
) -> CombinedFootingLayout:
    """Construye el layout para una longitud concreta.

    Los desplazamientos respecto del centro se DERIVAN de la longitud: es lo que
    permite barrer sin que la estructura cambie de forma. `transverse_shift_m` corre el
    eje lateral de la zapata respecto de la línea de las columnas (linderos laterales);
    con 0 el layout es el de siempre."""
    columnas = []
    for spec in specs:
        posicion = first_column_edge_distance_m + spec.distance_from_first_m
        offset_long = posicion - length_m / 2.0
        offset_lateral = spec.transverse_offset_m - transverse_shift_m
        if longitudinal_direction == "X":
            placement = ColumnPlacement(
                column=spec.column, offset_x_m=offset_long, offset_y_m=offset_lateral
            )
        else:
            placement = ColumnPlacement(
                column=spec.column, offset_x_m=offset_lateral, offset_y_m=offset_long
            )
        columnas.append(ColumnOnFooting(label=spec.label, placement=placement, loads=spec.loads))

    B = length_m if longitudinal_direction == "X" else width_m
    L = width_m if longitudinal_direction == "X" else length_m
    return CombinedFootingLayout(B_m=B, L_m=L, columns=columnas)


def generate_combined_alternatives(
    specs: list[ColumnSpec],
    params: CombinedSearchParameters,
    soil: SoilProfile,
    concrete: MaterialConcrete,
    steel: MaterialSteel,
    code: IConcreteCode,
    contact_model: ContactPressureModel,
    top_cover: TopCoverDeclaration,
) -> CombinedAlternativeSet:
    """Barre longitud, ancho y peralte, y devuelve las alternativas ACEPTADAS.

    Aceptada = ninguna verificación implementada la descarta (criterio NO_FAIL, decisión
    6). No significa que cumpla: el estado de cada una hay que leerlo, y las particiones
    del conjunto lo separan.

    Para cada (longitud, ancho) se toma el PRIMER peralte aceptado: es el mismo criterio
    que el solver de zapata aislada, y por la misma razón —el peralte mínimo viable es el
    de menor volumen de concreto para esa planta—."""
    resultado = CombinedAlternativeSet()
    resumen = CombinedDiscardSummary()
    validas = 0

    longitudes = _frange(params.length_min_m, params.length_max_m, params.length_step_m)
    anchos = _frange(params.width_min_m, params.width_max_m, params.width_step_m)
    peraltes = _frange(params.h_min_m, params.h_max_m, params.h_step_m)

    total = len(longitudes) * len(anchos) * len(peraltes)
    if total > MAX_COMBINED_GEOMETRIES:
        resultado.truncated = True
        resultado.search_note = (
            f"El rango solicitado genera {total} combinaciones, por encima del tope de "
            f"{MAX_COMBINED_GEOMETRIES}. Se exploró solo hasta el tope: el resultado NO es "
            f"una búsqueda exhaustiva. Acote el rango o aumente los pasos."
        )

    direccion = params.longitudinal_direction
    limites = params.site_limits
    fuera_del_terreno = 0
    for length in longitudes:
        if params.first_column_edge_distance_m is None:
            borde = auto_first_column_edge_distance(specs, length, direccion, limites)
        else:
            borde = params.first_column_edge_distance_m
            s_min, s_max = longitudinal_window(specs, length, direccion, limites)
            if limites is not None and not (s_min - _TOL_M <= -borde <= s_max + _TOL_M):
                borde = None
        if borde is None:
            fuera_del_terreno += len(anchos)
            continue
        for width in anchos:
            corrimiento = auto_transverse_shift(specs, width, direccion, limites)
            if corrimiento is None:
                fuera_del_terreno += 1
                continue
            for h in peraltes:
                if resultado.evaluated_count >= MAX_COMBINED_GEOMETRIES:
                    return _con_nota_de_estados(resultado, resumen, fuera_del_terreno, params)
                try:
                    layout = build_layout(
                        specs, length, width, borde, direccion,
                        transverse_shift_m=corrimiento,
                    )
                except ValueError:
                    # Geometría imposible (una columna no cabe): no es un descarte de
                    # diseño, es una entrada sin sentido físico. Se omite en silencio.
                    continue

                resultado.evaluated_count += 1
                try:
                    r = solve_combined_footing(
                        layout, h, soil=soil, concrete=concrete, steel=steel,
                        code=code, contact_model=contact_model, top_cover=top_cover,
                    )
                except ValueError as exc:
                    resultado.unresolved_count += 1
                    resumen.add_unresolved(str(exc), length, width, h)
                    continue

                # Decisión 6: NO_FAIL. Solo el FAIL descarta; una alternativa NO VERIFICADA
                # o con observaciones se CONSERVA y se rotula con su estado.
                if not r.overall_status.discards:
                    validas += 1
                    resultado.valid.append(
                        CombinedAlternative(
                            id=f"COMB-{validas:03d}",
                            length_m=length, width_m=width, h_m=h, result=r,
                            first_column_edge_distance_m=borde, transverse_shift_m=corrimiento,
                            metrics=compute_combined_metrics(r, soil.Df_m),
                        )
                    )
                    break  # primer peralte aceptado para esta planta
                resultado.discarded_count += 1
                resumen.add(r, length, width, h)

    return _con_nota_de_estados(resultado, resumen, fuera_del_terreno, params)


def _con_nota_de_estados(
    resultado: "CombinedAlternativeSet",
    resumen: CombinedDiscardSummary,
    fuera_del_terreno: int = 0,
    params: "CombinedSearchParameters | None" = None,
) -> "CombinedAlternativeSet":
    """Añade a la nota de búsqueda cuántas ACEPTADAS no pueden declararse conformes, y
    cómo se colocó la zapata respecto de los linderos.

    Con el criterio NO_FAIL (decisión 6) esas alternativas ya no se descartan: se
    devuelven con su estado. La nota impide que aparezcan en la tabla como si cumplieran;
    es presentación, no un criterio de cálculo."""
    if params is not None and (params.first_column_edge_distance_m is None or params.site_limits):
        partes = []
        if params.first_column_edge_distance_m is None:
            partes.append(
                "Posición de la zapata elegida por el programa para cada longitud: centra la "
                "resultante de la combinación permanente y se recorta contra los linderos "
                "(heurística de búsqueda; cada posición se verifica igual que cualquier otra)."
            )
        if params.site_limits is not None:
            partes.append(params.site_limits.describe())
        if fuera_del_terreno:
            partes.append(
                f"{fuera_del_terreno} planta(s) del rango no caben en el terreno y no se evaluaron."
            )
        resultado.search_note = (resultado.search_note + " " + " ".join(partes)).strip()
    n_nv = len(resultado.not_verified)
    n_obs = len(resultado.accepted_with_findings)
    if n_nv or n_obs:
        partes = []
        if n_nv:
            partes.append(f"{n_nv} NO VERIFICADA(S)")
        if n_obs:
            partes.append(f"{n_obs} con observaciones (WARNING)")
        nota = (
            f"De las {len(resultado.valid)} alternativa(s) aceptada(s), "
            + " y ".join(partes)
            + ". Aceptada significa que ninguna verificación implementada la descarta, NO que "
            "cumpla. Revise la traza; por ejemplo, con fuerzas horizontales la estabilidad de "
            "la zapata combinada no está implementada y el resultado queda NO VERIFICADO."
        )
        resultado.search_note = (resultado.search_note + " " + nota).strip()
    resultado.discard_summary = resumen.sorted()
    return resultado


# =========================================================================
# Puntuación y ordenamiento
# =========================================================================


class ScoredCombinedAlternative(BaseModel):
    alternative: CombinedAlternative
    score: float = Field(..., description="Menor es mejor: todas las métricas son costos")
    breakdown: dict


def rank_combined_alternatives(
    alternatives: list[CombinedAlternative], weights: "ScoreWeights | None" = None
) -> list[ScoredCombinedAlternative]:
    """Ordena las alternativas con el MISMO núcleo de puntuación que la zapata
    aislada: normalización min-max y suma ponderada sobre las mismas métricas.

    Ordenar por volumen de concreto —lo que hacía antes— es un caso particular de
    esto, el de dar todo el peso a esa métrica. Reutilizar el núcleo evita que las
    dos tipologías acaben puntuando con criterios distintos sin que nadie lo note."""
    from engine.optimization.scoring import score_metric_sets

    puntuadas = score_metric_sets([a.metrics for a in alternatives], weights)
    resultado = [
        ScoredCombinedAlternative(alternative=a, score=score, breakdown=breakdown)
        for a, (score, breakdown) in zip(alternatives, puntuadas)
    ]
    # Desempate por id para que el orden sea determinista: dos alternativas con la
    # misma puntuación deben salir siempre en el mismo orden.
    return sorted(resultado, key=lambda s: (s.score, s.alternative.id))
