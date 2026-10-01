"""Auditoría de paridad entre tipologías (2026-09-19).

QUÉ VIGILA ESTE ARCHIVO
=======================
Que una exigencia que la norma impone a «las zapatas» sin distinguir tipología se
verifique en las TRES. La zapata aislada, la combinada y la conectada tienen motores
propios y es fácil que una gane una verificación y las otras no se enteren: ya pasó con la
estabilidad de la combinada (D4 → pendiente 7), con el incremento del 30 % de §15.2.4 y
con la formulación del volcamiento (`FORMULACION_VOLTEO`).

HALLAZGO QUE LO ORIGINA — §15.7 EN LA COMBINADA
===============================================
La combinada no verificaba el peralte mínimo de E.060 §15.7. El artículo dice, literal:

    «La altura de las zapatas, medida sobre el refuerzo inferior no debe ser menor de
     300 mm para zapatas apoyadas sobre el suelo […]»

No distingue tipología, y §15.10.1 manda diseñar las zapatas que soportan más de una
columna «de acuerdo con los requisitos de diseño apropiados de esta Norma». El hueco
producía CONFORME en una zapata combinada de 0,20 m de canto con cargas bajas, que la
aislada habría descartado. No hubo decisión nueva que tomar: se aplicó el mismo criterio y
la misma implementación, `E060ConcreteCode.min_depth_rule`.

Detalle en `docs/auditoria_paridad_tipologias.md`.
"""

import dataclasses

import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode, MinDepthInterpretation
from engine.domain.combined_layout import CombinedFootingLayout
from engine.optimization.combined_discards import category_of
from engine.results.status import CheckStatus
from tests.freeze.cases import (
    CASES,
    COMBINED_CASES,
    CONNECTED_CASES,
    _col_comb,
    _soil,
)
from tests.freeze.test_freeze_connected import _solve as _solve_conectada
from tests.freeze.test_freeze_isolated import _evaluate, _solve_combined

# Verificaciones que la norma impone a «las zapatas» sin distinguir tipología. No es la
# lista de todo lo que cada motor comprueba —el punzonamiento, la flexión y el cortante
# tienen ids propios de cada tipología—, sino la de lo que NINGUNA puede dejar de mirar.
COMUNES_A_LAS_TRES = {
    "contact_pressure": "Presión de contacto sobre el suelo (E.050 art. 28; E.060 §15.2)",
    "foundation_depth": "Profundidad mínima de cimentación (E.050 art. 26.2)",
    "min_depth": "Peralte mínimo de la zapata (E.060 §15.7)",
    # H6, cerrada el 2026-09-20: el art. 23.3 dice «Las zapatas y plateas», sin distinguir
    # tipología, y hasta entonces solo la combinada lo verificaba.
    "shape_ratio": "Proporción en planta, L <= 10·B (E.050 art. 23.3)",
    # H7, cerrada el 2026-09-20: ninguna tipología comprobaba que la cimentación siguiera
    # siendo superficial, que es la condición bajo la que vale todo el capítulo.
    "shallow_foundation": "Cimentación superficial, Df/B <= 5 (E.050 art. 23.1)",
}


def _ids(entradas) -> set[str]:
    return {e.id for e in entradas}


@pytest.fixture(scope="module")
def ids_por_tipologia() -> dict[str, set[str]]:
    """Los ids de traza que cada tipología emite, recogidos de sus casos congelados."""
    salida = {"aislada": set(), "combinada": set(), "conectada": set()}
    for c in CASES:
        salida["aislada"] |= _ids(_evaluate(c).trace.entries)
    for c in COMBINED_CASES:
        salida["combinada"] |= _ids(_solve_combined(c).trace.entries)
    for c in CONNECTED_CASES:
        if c.expects_rejection:
            continue
        salida["conectada"] |= _ids(_solve_conectada(c).trace.entries)
    return salida


@pytest.mark.parametrize("check_id", sorted(COMUNES_A_LAS_TRES))
def test_las_tres_tipologias_verifican_lo_que_la_norma_no_distingue(check_id, ids_por_tipologia):
    faltan = [t for t, ids in ids_por_tipologia.items() if check_id not in ids]
    assert not faltan, (
        f"«{check_id}» ({COMUNES_A_LAS_TRES[check_id]}) no se verifica en {faltan}. "
        f"Si la omisión es deliberada, tiene que estar decidida y documentada, no ser un "
        f"olvido: ver docs/auditoria_paridad_tipologias.md."
    )


# =========================================================================
# §15.7 en la zapata combinada
# =========================================================================


def _combinada_ligera(h_m: float, B_m: float = 8.0, L_m: float = 3.60):
    """Zapata combinada con cargas BAJAS: ninguna verificación de resistencia la descarta,
    de modo que lo único que puede descartarla es un criterio prescriptivo."""
    base = COMBINED_CASES[0]
    layout = CombinedFootingLayout(
        B_m=B_m, L_m=L_m,
        columns=[_col_comb("C1", 1.0, B_m, 120.0), _col_comb("C2", 7.0, B_m, 120.0)],
    )
    return dataclasses.replace(base, layout=layout, h_m=h_m, soil=_soil(400.0, Df_m=1.50))


def test_una_combinada_por_debajo_del_minimo_se_descarta():
    """Antes de la auditoría, esta zapata de 0,20 m salía CONFORME."""
    r = _solve_combined(_combinada_ligera(0.20))
    assert r.overall_status is CheckStatus.FAIL
    entrada = r.trace.by_id("min_depth")
    assert entrada.status is CheckStatus.FAIL
    assert "§15.7" in entrada.code_reference
    motivos = [m for m in r.discard_reasons if "15.7" in m]
    assert len(motivos) == 1, r.discard_reasons
    # Y el descarte se clasifica: no cae en «otra verificación».
    registro = next(d for d in r.discard_records if d.check_id == "min_depth")
    codigo, etiqueta = category_of(registro.check_id)
    assert codigo == "PERALTE_MINIMO"
    assert "15.7" in etiqueta


def test_una_combinada_holgada_cumple_y_no_estorba():
    r = _solve_combined(_combinada_ligera(0.40))
    assert r.trace.by_id("min_depth").status is CheckStatus.PASS
    assert r.overall_status is CheckStatus.PASS
    assert not r.discard_reasons


def test_la_combinada_mide_sobre_el_refuerzo_INFERIOR_igual_que_la_aislada():
    """§15.7 dice «medida sobre el refuerzo inferior». La magnitud gobernante debe ser el
    peralte efectivo de la cara INFERIOR, no el total ni el de la cara superior.

    Se reconstruye a mano desde el recubrimiento y el diámetro supuesto, sin llamar al
    código que se prueba."""
    codigo = E060ConcreteCode()
    assert codigo.min_depth_interpretation is MinDepthInterpretation.EFFECTIVE_DEPTH

    caso = _combinada_ligera(0.55)
    r = _solve_combined(caso)
    recubrimiento_inferior = codigo.cover_footing_mm()[0] / 1000.0
    # Diámetro supuesto por defecto del solver de la combinada (`assumed_bar_diameter_mm`).
    # Se escribe aquí a propósito: si el solver cambiara su valor sin decirlo, este test
    # debe romper, no seguirle la pista.
    db = 0.016
    d_esperada = caso.h_m - recubrimiento_inferior - db / 2.0

    assert r.trace.by_id("min_depth").result_value == pytest.approx(d_esperada, rel=1e-9)
    assert r.trace.by_id("min_depth").result_value < caso.h_m, (
        "Si coincidiera con h, se estaría midiendo el peralte TOTAL"
    )


def test_el_umbral_es_el_mismo_en_las_tres_tipologias():
    """Un umbral distinto por tipología sería una divergencia silenciosa: el artículo es
    uno solo. Se comprueba contra el valor del código, no contra una constante copiada."""
    umbral = E060ConcreteCode().min_depth_threshold_m()
    assert umbral == pytest.approx(0.300)

    # Justo por encima y justo por debajo del umbral, en la combinada.
    codigo = E060ConcreteCode()
    recubrimiento = codigo.cover_footing_mm()[0] / 1000.0
    h_justo = umbral + recubrimiento + 0.008  # d = 0,300 exactos
    assert _solve_combined(_combinada_ligera(h_justo + 0.001)).trace.by_id(
        "min_depth"
    ).status is CheckStatus.PASS
    assert _solve_combined(_combinada_ligera(h_justo - 0.010)).trace.by_id(
        "min_depth"
    ).status is CheckStatus.FAIL


def test_los_casos_congelados_de_la_combinada_no_cambian_de_estado_por_esto():
    """La verificación se añadió para cerrar un hueco, no para mover resultados: los cuatro
    casos congelados tienen canto de sobra y siguen cumpliendo."""
    for caso in COMBINED_CASES:
        r = _solve_combined(caso)
        assert r.trace.by_id("min_depth").status is CheckStatus.PASS, caso.name


# =========================================================================
# El registro de limitaciones no puede contradecir al motor
# =========================================================================


def test_el_registro_no_presenta_los_FS_de_la_norma_como_los_del_motor():
    """D10-2b: el programa exige 1,50 al volteo —también sísmico— y al deslizamiento, y eso
    NO es lo que pide la norma en dos de los tres casos.

    La limitación `horizontal_forces` se quedó describiendo los valores normativos como si
    fueran los del motor —«FS por defecto de E.020 art. 21 (1,5), art. 22.1 (1,25) y E.030
    art. 64.2 (1,2)»— después de que D10-2b los sustituyera. Es exactamente lo que
    `CLAUDE.md` prohíbe: presentar un criterio del programa como exigencia normativa, o al
    revés. Los números se comparan contra las constantes del motor, no contra una copia."""
    from engine.results.limitations import limitation_by_id
    from engine.soil.stability import (
        E020_FS_SLIDING,
        E030_FS_OVERTURNING_SEISMIC,
        PROGRAM_FS_OVERTURNING,
        PROGRAM_FS_SLIDING,
    )

    texto = limitation_by_id("horizontal_forces").description
    assert "D10-2b" in texto
    for valor in (PROGRAM_FS_OVERTURNING, PROGRAM_FS_SLIDING):
        assert f"{valor:.2f}".replace(".", ",") in texto, valor
    # Los valores de la norma siguen citándose, pero identificados como suyos.
    for valor, articulo in ((E030_FS_OVERTURNING_SEISMIC, "E.030 art. 64.2"),
                            (E020_FS_SLIDING, "E.020 art. 22.1")):
        assert f"{valor:.2f}".replace(".", ",") in texto, valor
        assert articulo in texto
    assert "MÁS ESTRICTO" in texto.upper()


def test_el_registro_no_niega_una_reduccion_que_el_motor_si_aplica():
    """`seismic_reduction_80pct` decía «ni en la combinada» después de que la combinada
    empezara a aplicarla (`docs/reduccion_sismica_combinada.md`).

    Se comprueba contra el motor: si la combinada la aplica, la descripción no puede
    negarlo. Que la aplique bien es asunto de `tests/test_combined_seismic_reduction.py`."""
    import inspect

    from engine.foundation import combined_solver
    from engine.results.limitations import limitation_by_id

    aplica_en_combinada = "soil_actions" in inspect.getsource(combined_solver)
    texto = limitation_by_id("seismic_reduction_80pct").description
    if aplica_en_combinada:
        assert "ni en la combinada" not in texto, (
            "El registro niega una reducción que el solver de la combinada sí aplica."
        )
        assert "combinada" in texto


# =========================================================================
# Toda entrada de traza declara en qué se apoya
# =========================================================================


def test_ninguna_entrada_de_traza_se_queda_sin_hipotesis():
    """Una entrada sin hipótesis se lee como «esto está verificado, sin más».

    Casi nunca es cierto: toda verificación descansa en algo —una lectura del artículo, un
    alcance que no cubre, un dato que el motor no posee— y si eso no llega a la traza, el
    usuario no puede juzgar el resultado. La auditoría de trazas (2026-09-19) encontró 74
    entradas así repartidas en cinco verificaciones; la más repetida era
    `foundation_depth`, que decía «Df = 1,50 ≥ 0,80 → PASS» sin mencionar que E.050 art.
    26.2 pone la estratigrafía, los cambios de volumen y las condiciones de uso en manos
    del profesional responsable, y que el motor no los mira.

    `hypotheses` es PROSA y no está congelada (`PROSE_FIELDS`), de modo que este test es la
    única red que tiene."""
    from tests.freeze.cases import BEAM_CASES
    from tests.freeze.test_freeze_isolated import _solve_beam

    huerfanas: list[tuple[str, str]] = []

    def revisar(etiqueta: str, trace) -> None:
        for e in trace.entries:
            if not e.hypotheses:
                huerfanas.append((etiqueta, e.id))

    for c in CASES:
        revisar(f"aislada/{c.name}", _evaluate(c).trace)
    for c in COMBINED_CASES:
        revisar(f"combinada/{c.name}", _solve_combined(c).trace)
    for c in CONNECTED_CASES:
        if not c.expects_rejection:
            revisar(f"conectada/{c.name}", _solve_conectada(c).trace)
    for c in BEAM_CASES:
        revisar(f"viga/{c.name}", _solve_beam(c)[1])

    ids = sorted({i for _, i in huerfanas})
    assert not huerfanas, (
        f"{len(huerfanas)} entradas de traza sin ninguna hipótesis declarada, en las "
        f"verificaciones {ids}."
    )


def test_la_profundidad_de_cimentacion_declara_lo_que_no_comprueba():
    """El alcance del art. 26.2 se declara en UNA sola fuente y llega a las tres
    tipologías: cada solver lo armaba por su cuenta y los tres lo omitían."""
    from engine.soil.foundation_depth import SCOPE_NOTES

    assert SCOPE_NOTES, "El alcance debe estar declarado, no vacío"
    for construir, casos, etiqueta in (
        (lambda c: _evaluate(c).trace, CASES, "aislada"),
        (lambda c: _solve_combined(c).trace, COMBINED_CASES, "combinada"),
        (lambda c: _solve_conectada(c).trace, [c for c in CONNECTED_CASES
                                               if not c.expects_rejection], "conectada"),
    ):
        entrada = construir(casos[0]).by_id("foundation_depth")
        texto = " ".join(entrada.hypotheses)
        for nota in SCOPE_NOTES:
            assert nota in texto, f"{etiqueta}: falta el alcance del art. 26.2"


# =========================================================================
# H2 — cortante unidireccional transversal de la zapata combinada
# =========================================================================
#
# Criterio aprobado por el usuario (2026-09-19): sección crítica a d de la cara de la
# columna, ancho resistente igual al ancho TOTAL de la zapata en ese plano (E.060
# §11.12.1.1), Vu integrando la presión de contacto sobre el área que queda fuera de la
# sección crítica, y Vu <= φVc.


def test_la_combinada_verifica_el_cortante_en_las_DOS_direcciones():
    """El hallazgo H2: la combinada verificaba solo el longitudinal.

    §15.5.1 remite al §11.12 y §11.12.1.1 no distingue dirección: «Cada sección crítica
    que debe investigarse se extiende en un plano a través del ancho total del
    elemento». La aislada lo hace en las dos (`shear_x`, `shear_y`) y la conectada lo
    hereda."""
    for caso in COMBINED_CASES:
        ids = {e.id for e in _solve_combined(caso).trace.entries}
        assert {"shear_longitudinal", "shear_transversal"} <= ids, caso.name


def test_el_cortante_transversal_se_reconstruye_a_mano():
    """K1: dos columnas iguales, centradas en la dirección transversal.

    Sin excentricidad transversal la presión es uniforme, de modo que el cálculo se puede
    escribir entero sin llamar al motor:

        dim_transversal = L = 3,60 m      longitud total = B = 8,00 m
        Pu_total = 2 × 1260 = 2520 kN     q' = 2520/3,60 = 700,0 kN/m
        voladizo = 3,60/2 − 0,50/2 = 1,550 m ;  d = 0,717 m
        Vu = q'·(voladizo − d) = 700,0 × 0,833 = 583,100 kN

    El ancho resistente NO es el de la franja transversal —que es un criterio de reparto
    del acero— sino la longitud completa de la zapata en ese plano."""
    caso = next(c for c in COMBINED_CASES if c.name == "K1_dos_columnas_simetricas")
    r = _solve_combined(caso)
    lay = caso.layout

    dim_transversal = lay.transverse_width_m
    Pu = sum(k.P_kN for col in lay.columns for k in col.loads.factored)
    q_por_metro = Pu / dim_transversal
    voladizo = dim_transversal / 2.0 - lay.columns[0].placement.column.by_m / 2.0
    d = r.bottom_face.d_m
    vu_a_mano = q_por_metro * (voladizo - d)

    entrada = r.trace.by_id("shear_transversal")
    assert entrada.result_value == pytest.approx(vu_a_mano, rel=1e-12)
    assert entrada.result_value == pytest.approx(583.100, rel=1e-5)
    assert "11.12.1.1" in entrada.code_reference


def test_el_ancho_resistente_es_la_longitud_completa_de_la_zapata():
    """§11.12.1.1: «un plano a través del ancho total». Se comprueba contra φVc, que es
    proporcional a b_w: con el ancho de franja saldría mucho menor."""
    from engine.codes.peru.e060_concrete import E060ConcreteCode
    from engine.foundation.shear_oneway import check_shear_oneway

    caso = next(c for c in COMBINED_CASES if c.name == "K1_dos_columnas_simetricas")
    r = _solve_combined(caso)
    entrada = r.trace.by_id("shear_transversal")

    esperado = check_shear_oneway(
        entrada.result_value, caso.concrete.fc_MPa,
        bw_m=caso.layout.longitudinal_length_m, d_m=r.bottom_face.d_m,
        code=E060ConcreteCode(),
    )
    assert entrada.status is esperado.status
    assert f"{caso.layout.longitudinal_length_m:.3f}" in entrada.equation_substituted


def test_gobierna_la_columna_con_el_voladizo_transversal_mayor():
    """Con varias columnas el plano crítico que manda es el que deja más área fuera.

    Se desplaza una columna en la dirección transversal: su voladizo del lado opuesto
    crece, y con él Vu."""
    import dataclasses

    from engine.domain.column_placement import ColumnPlacement

    caso = next(c for c in COMBINED_CASES if c.name == "K1_dos_columnas_simetricas")
    base = _solve_combined(caso).trace.by_id("shear_transversal").result_value

    lay = caso.layout
    movida = lay.model_copy(update={
        "columns": [
            lay.columns[0].model_copy(update={
                "placement": ColumnPlacement(
                    column=lay.columns[0].placement.column,
                    offset_x_m=lay.columns[0].offset_x_m, offset_y_m=0.40,
                )
            }),
            lay.columns[1],
        ]
    })
    con_offset = _solve_combined(dataclasses.replace(caso, layout=movida))
    assert con_offset.trace.by_id("shear_transversal").result_value > base


def test_el_descarte_por_cortante_transversal_se_clasifica():
    """Una zapata estrecha en la dirección transversal: el voladizo crece y el cortante
    acaba gobernando. Se comprueba que el motivo llega con su categoría propia y no cae
    en «otra verificación»."""
    import dataclasses

    from engine.domain.combined_layout import CombinedFootingLayout

    caso = COMBINED_CASES[0]
    lay = CombinedFootingLayout(
        B_m=8.0, L_m=6.0,
        columns=[_col_comb("C1", 1.0, 8.0, 2400.0), _col_comb("C2", 7.0, 8.0, 2400.0)],
    )
    r = _solve_combined(dataclasses.replace(caso, layout=lay, h_m=0.55, soil=_soil(400.0, Df_m=1.50)))

    entrada = r.trace.by_id("shear_transversal")
    if entrada.status is not CheckStatus.FAIL:
        pytest.skip(f"El escenario no llegó a fallar: Vu = {entrada.result_value:.1f} kN")
    registro = next(d for d in r.discard_records if d.check_id == "shear_transversal")
    codigo, etiqueta = category_of(registro.check_id)
    assert codigo == "CORTANTE_TRANSVERSAL"
    assert "11.12.1.1" in etiqueta


def test_el_cortante_transversal_usa_la_presion_de_la_resultante_no_la_de_franja():
    """La presión es la del campo real bajo el plano crítico, no
    `P_columna/(ancho_franja·dim)`, que es un criterio de reparto del acero tomado de los
    apuntes. Se comprueba en la prosa de la entrada, que es donde el criterio se declara."""
    r = _solve_combined(COMBINED_CASES[0])
    texto = " ".join(r.trace.by_id("shear_transversal").hypotheses)
    assert "ancho total" in texto
    assert "P_i·offset_i" in texto
    assert "franja" in texto, "Debe decir expresamente que NO usa la presión de franja"
