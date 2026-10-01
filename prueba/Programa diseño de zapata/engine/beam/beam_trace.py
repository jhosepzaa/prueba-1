"""Trazabilidad del motor de vigas — Fase 3.

Convierte un `ConnectingBeamResult` en la MISMA estructura `CalculationTrace` que
usa la zapata aislada. No recalcula nada: solo lee lo que el motor ya resolvió y lo
expone con ecuación simbólica, ecuación sustituida, resultado, unidad, hipótesis,
artículo y estado.

POR QUÉ VIVE APARTE DEL MOTOR
=============================
`connecting_beam.py` no debe saber nada de informes ni de interfaces. Este módulo es
la frontera: el motor produce números y estados, y aquí se les da forma de traza. Si
mañana el informe cambia, el motor no se toca.

REGLA DE ESTADOS
================
Cada entrada lleva su propio estado. Ninguna entrada se promueve a PASS por el hecho
de que otra se haya implementado. Lo que no se comprueba entra como NO VERIFICADO con
el texto de lo que falta, no se omite.
"""

from __future__ import annotations

from engine.beam.connecting_beam import ConnectingBeamResult
from engine.results.calculation_trace import CalculationTrace, CalculationTraceEntry
from engine.results.status import CheckStatus

M2_TO_CM2 = 1e4


def _entry(**kwargs) -> CalculationTraceEntry:
    kwargs.setdefault("code_name", "E.060")
    return CalculationTraceEntry(**kwargs)


def build_beam_trace(r: ConnectingBeamResult) -> CalculationTrace:
    """Traza completa de flexión, cortante, acero y estribos."""
    trace = CalculationTrace()

    # --- 1. Dimensión transversal mínima, §21.12.3.2 ---------------------------
    trace.add(
        _entry(
            id="beam_dimension",
            description=(
                "Dimensión transversal mínima de la viga de conexión: la menor de las dos "
                "dimensiones debe alcanzar la luz libre entre columnas dividida entre 20, "
                "sin necesidad de pasar de 450 mm."
            ),
            equation_symbolic="b_min >= min(ln/20, 450 mm)",
            equation_substituted=r.dimensional.equation_substituted,
            result_value=r.dimensional.min_dimension_required_m * 1000.0,
            result_unit="mm",
            hypotheses=[
                "La luz libre ln se mide entre caras de columna, que es la definición de "
                "§21.12.3.2. La sección de la viga es DATO del proyectista y no se optimiza: "
                "el motor comprueba el mínimo, no lo dimensiona.",
            ] + (
                ["El tope de 450 mm de §21.12.3.2 gobierna sobre ln/20."]
                if r.dimensional.capped_at_400mm
                else []
            ),
            code_reference=r.dimensional.code_reference,
            status=CheckStatus.PASS if r.dimensional.ok else CheckStatus.FAIL,
        )
    )

    # --- 2. Flexión: acero requerido por análisis en cada cara ------------------
    for etiqueta, Mu, As_dis, minimo in (
        ("negativo", r.Mu_negative_kNm, r.As_negative_m2, r.min_steel_negative),
        ("positivo", r.Mu_positive_kNm, r.As_positive_m2, r.min_steel_positive),
    ):
        hipotesis = [
            "φ = 0,90 por §9.3.2, flexión sin carga axial.",
            "Bloque rectangular equivalente de 0,85·f'c según §10.2.7.",
        ]
        hipotesis.append(
            "§10.5.3 (E.060, propuesta 2019) exime del mínimo solo a losas macizas y "
            "nervadas: en una viga rige siempre el mayor de §10.5.1 y §10.5.2."
        )
        trace.add(
            _entry(
                id=f"beam_flexure_{etiqueta}",
                description=(
                    f"Acero de flexión para el momento {etiqueta} de diseño, antes de "
                    f"aplicar el mínimo."
                ),
                equation_symbolic="As = Mu / (φ·fy·(d − a/2)), con a = As·fy/(0,85·f'c·b)",
                equation_substituted=(
                    f"Mu = {Mu:.2f} kN·m sobre b = {r.b_m:.3f} m y d = {r.d_m:.3f} m "
                    f"-> As de diseño = {As_dis * M2_TO_CM2:.2f} cm²"
                ),
                result_value=As_dis * M2_TO_CM2,
                result_unit="cm²",
                hypotheses=hipotesis,
                code_reference="§10.2, §9.3.2",
                status=CheckStatus.PASS,
            )
        )

        # --- 3. Acero mínimo de VIGAS, §10.5 -----------------------------------
        trace.add(
            _entry(
                id=f"beam_min_steel_{etiqueta}",
                description=(
                    f"Acero mínimo de la cara con momento {etiqueta}. §10.5.1 exige "
                    f"Mn >= 1,2·Mcr y §10.5.2 la ec. 10-3; son SIMULTÁNEAS y gobierna la "
                    f"mayor. Una viga NO está entre las excepciones de §10.5.1, que solo "
                    f"exime a zapatas y losas macizas."
                ),
                equation_symbolic=(
                    "As_min = max(As para Mn >= 1,2·Mcr ; (0,22·sqrt(f'c)/fy)·bw·d)"
                ),
                equation_substituted=minimo.equation_substituted,
                result_value=minimo.As_min_governing_m2 * M2_TO_CM2,
                result_unit="cm²",
                hypotheses=[
                    f"Mcr = {minimo.Mcr_kNm:.2f} kN·m con fr = 0,62·sqrt(f'c) = "
                    f"{minimo.fr_MPa:.3f} MPa sobre la sección bruta.",
                    f"Gobierna: {minimo.governed_by}.",
                ],
                code_reference="§10.5.1, §10.5.2 ec. 10-3, §10.5.3",
                status=CheckStatus.PASS,
            )
        )

    # --- 4. Cortante que aporta el concreto, §11.3.1.1 -------------------------
    s = r.shear
    trace.add(
        _entry(
            id="beam_shear_concrete",
            description="Resistencia al cortante que aporta el concreto.",
            equation_symbolic="Vc = 0,17·sqrt(f'c)·bw·d   (ec. 11-3)",
            equation_substituted=s.equation_substituted,
            result_value=s.phi_Vc_kN,
            result_unit="kN",
            hypotheses=[f"φ = {s.phi:.2f} por §9.3.2, cortante y torsión."],
            code_reference=s.code_reference,
            status=CheckStatus.PASS if s.status_ok else CheckStatus.FAIL,
        )
    )

    # --- 5. Acero de cortante, ec. 11-15 y su cota de §11.5.7.9 ----------------
    if s.Vs_exceeds_limit:
        estado_vs = CheckStatus.FAIL
    elif s.stirrups_required:
        estado_vs = CheckStatus.PASS
    else:
        estado_vs = CheckStatus.INFO
    trace.add(
        _entry(
            id="beam_shear_steel",
            description=(
                "Cortante que deben tomar los estribos y su cota superior: si Vs supera "
                "2,2·sqrt(f'c)·bw·d la sección es insuficiente y ningún estribo lo corrige."
            ),
            equation_symbolic="Vs = Vu/φ − Vc   (ec. 11-15);  Vs <= 2,2·sqrt(f'c)·bw·d",
            equation_substituted=(
                f"Vs requerido = {s.Vu_kN:.2f}/{s.phi:.2f} − {s.Vc_kN:.2f} = "
                f"{s.Vs_required_kN:.2f} kN  frente a  Vs_max = {s.Vs_max_kN:.2f} kN"
            ),
            result_value=s.Vs_required_kN,
            result_unit="kN",
            hypotheses=[
                "Vs se obtiene de la ec. 11-15 con el Vu de la sección crítica y el Vc ya "
                "calculado: no se redistribuye cortante entre secciones.",
            ] + (
                ["El concreto por sí solo resiste el cortante: no se exigen estribos por "
                 "resistencia."]
                if not s.stirrups_required
                else []
            ),
            code_reference="§11.5.7.2 ec. 11-15, §11.5.7.9",
            status=estado_vs,
        )
    )

    # --- 6. Refuerzo mínimo por cortante, §11.5.6 ------------------------------
    trace.add(
        _entry(
            id="beam_shear_av_min",
            description=(
                "Refuerzo transversal mínimo: se exige donde Vu supera 0,5·φVc, salvo las "
                "excepciones de §11.5.6.1. Una viga de conexión no es losa ni zapata, de "
                "modo que la exención (a) no la alcanza."
            ),
            equation_symbolic="Av_min/s = 0,062·sqrt(f'c)·bw/fyt >= 0,35·bw/fyt   (ec. 11-13)",
            equation_substituted=(
                f"Av_min/s = {s.Av_min_over_s_m * 1e4:.4f} cm²/m frente al "
                f"(Av/s) que exige Vs = {s.Av_over_s_required_m * 1e4:.4f} cm²/m; "
                f"gobierna {s.Av_over_s_governing_m * 1e4:.4f} cm²/m"
            ),
            result_value=s.Av_over_s_governing_m * 1e4,
            result_unit="cm²/m",
            hypotheses=[
                "La viga de conexión se trata como VIGA, no como losa ni zapata: la exención "
                "de §11.5.6.1(a) no la alcanza. Es una decisión de clasificación del elemento, "
                "declarada, no una lectura literal del artículo.",
            ] + (
                [f"Exención aplicada: {s.av_min_exemption}"] if s.av_min_exemption else []
            ),
            code_reference="§11.5.6.1, §11.5.6.2 ec. 11-13",
            status=CheckStatus.PASS,
        )
    )

    # --- 7. Estribos: separación adoptada --------------------------------------
    if s.layout is not None:
        trace.add(
            _entry(
                id="beam_stirrup_spacing",
                description=(
                    "Separación de estribos por resistencia, antes de aplicar el "
                    "confinamiento de §21.12.3.2."
                ),
                equation_symbolic="s <= min(d/2, 600 mm), reducido a la mitad si Vs > 0,33·sqrt(f'c)·bw·d",
                equation_substituted=(
                    f"{s.layout.n_legs} ramas de Ø{s.layout.bar_diameter_mm:.2f} mm a "
                    f"s = {s.layout.spacing_m * 100:.1f} cm, con el límite de "
                    f"{s.layout.spacing_limit_m * 100:.1f} cm ({s.layout.spacing_limit_reference})"
                ),
                result_value=s.layout.spacing_m * 100.0,
                result_unit="cm",
                hypotheses=[
                    "Separación por RESISTENCIA (§11.5.5). El confinamiento de §21.12.3.2 se "
                    "aplica después y puede reducirla: esta entrada no es la separación final.",
                ],
                code_reference="§11.5.5.1, §11.5.5.3",
                status=CheckStatus.PASS if s.layout.spacing_ok else CheckStatus.FAIL,
            )
        )

    # --- 8. Confinamiento §21.12.3.2 ------------------------------------------
    c = r.confinement
    trace.add(
        _entry(
            id="beam_confinement",
            description=(
                "Estribos CERRADOS de confinamiento en toda la longitud de la viga. Es una "
                "exigencia propia de §21.12.3.2 y rige aunque el cortante no pida estribos."
            ),
            equation_symbolic="s <= min(12·db_longitudinal, 300 mm)",
            equation_substituted=(
                f"límite = {c.spacing_limit_m * 100:.1f} cm (gobierna «{c.governed_by}»); "
                f"adoptado s = "
                + (
                    f"{c.spacing_provided_m * 100:.1f} cm"
                    if c.spacing_provided_m is not None
                    else "sin definir"
                )
            ),
            result_value=c.spacing_limit_m * 100.0,
            result_unit="cm",
            hypotheses=[
                "Los estribos son CERRADOS: §21.12.3.2 no admite estribos abiertos aquí."
            ],
            code_reference=c.code_reference,
            status=(
                CheckStatus.NOT_VERIFIED
                if c.ok is None
                else (CheckStatus.PASS if c.ok else CheckStatus.FAIL)
            ),
        )
    )

    # --- 9. E.030 art. 65.1: fuerza axial --------------------------------------
    trace.add(
        CalculationTraceEntry(
            id="beam_axial_trigger",
            description=(
                "Condición de disparo del requisito de fuerza axial en vigas de conexión."
            ),
            equation_symbolic="N >= 0,10 · SumaPu de la zapata conectada",
            equation_substituted=(
                f"N = {r.axial_N_kN:.2f} kN"
                if r.axial_required
                else "No se dispara: N = 0"
            ),
            result_value=r.axial_N_kN,
            result_unit="kN",
            hypotheses=[r.axial_trigger_note],
            code_name="E.030",
            code_reference="art. 65.1",
            status=CheckStatus.PASS if r.axial_required else CheckStatus.INFO,
        )
    )

    # --- 10. Interacción P−M ---------------------------------------------------
    for etiqueta, chk in (
        ("negativo", r.axial_flexure_negative),
        ("positivo", r.axial_flexure_positive),
    ):
        if chk is None:
            continue
        trace.add(
            _entry(
                id=f"beam_axial_flexure_{etiqueta}",
                description=(
                    f"Interacción axial-flexión con el momento {etiqueta}. La comprobación "
                    f"NO es «φMn >= Mu» con el Mn de flexión pura: se busca la capacidad a "
                    f"momento CON EL MISMO Pu sobre el diagrama de interacción. Se evaluaron "
                    f"los dos sentidos —tracción y compresión— porque E.030 art. 65.1 no fija "
                    f"el signo, y se reporta el más desfavorable."
                ),
                equation_symbolic=(
                    "Equilibrio de la sección con εcu = 0,003 y bloque de 0,85·f'c; "
                    "Pn_max = 0,80·[0,85·f'c·(Ag − Ast) + fy·Ast] (ec. 10-2)"
                ),
                equation_substituted=chk.equation_substituted,
                result_value=chk.demand_ratio,
                result_unit="Mu/φMn",
                hypotheses=[
                    "Sección rectangular con dos capas de refuerzo; no se modelan secciones T "
                    "ni refuerzo repartido en el alma.",
                    "Acero elastoplástico perfecto con Es = 200 000 MPa (§8.5.5).",
                    "El acero dentro del bloque de compresión descuenta el concreto que "
                    "desplaza.",
                    chk.message,
                ],
                code_reference=chk.code_reference,
                status=CheckStatus.PASS if chk.status_ok else CheckStatus.FAIL,
            )
        )

    # --- 11. §21.12.3.3 y lo que queda sin comprobar ---------------------------
    lat = r.lateral_requirements
    if lat is not None:
        if not lat.applies:
            estado = CheckStatus.INFO
        elif lat.not_implemented:
            estado = CheckStatus.NOT_VERIFIED
        else:
            estado = CheckStatus.PASS
        trace.add(
            _entry(
                id="beam_lateral_system",
                description=(
                    "§21.12.3.3: las vigas de cimentación sometidas a flexión por columnas "
                    "del sistema resistente a fuerzas laterales deben cumplir además §21.4 o "
                    "§21.5, según el sistema. §21.2 determina a cuál de los dos remite."
                ),
                equation_symbolic="§21.12.3.3 -> §21.4 (muros estructurales) | §21.5 (pórticos y duales)",
                equation_substituted=(
                    f"{lat.section or 'no resuelto'}"
                    + (f" — {lat.system_label}" if lat.system_label else "")
                ),
                result_value=(
                    lat.positive_moment_ratio_at_joint
                    if lat.positive_moment_ratio_at_joint is not None
                    else 0.0
                ),
                result_unit="M+ / M− exigido en la cara del nudo",
                hypotheses=[lat.reason] + list(lat.not_implemented),
                code_reference="§21.12.3.3 vía §21.2",
                status=estado,
            )
        )

    return trace
