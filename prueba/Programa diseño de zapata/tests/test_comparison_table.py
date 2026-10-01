import pytest

from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.search_parameters import GeometrySearchParameters
from engine.optimization.alternative_generator import generate_alternatives
from engine.optimization.comparison_table import SORT_KEYS, build_comparison_table, render_table_text
from tests.golden_cases.common import (
    CODE,
    COLUMN_40x40,
    CONCRETE_21,
    CONTACT_MODEL,
    DEPTH_PARAMS_DEFAULT,
    SOIL_150_BRUTA,
    STEEL_420,
)

LOADS = LoadCaseSet(
    service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=400.0)],
    factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=560.0)],
)
GEOM = GeometrySearchParameters(
    B_min_m=1.4, B_max_m=2.6, B_step_m=0.2, L_min_m=1.4, L_max_m=2.6, L_step_m=0.2, max_LB_ratio=1.5
)


def _alternatives():
    return generate_alternatives(
        column=COLUMN_40x40, soil=SOIL_150_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE, contact_model=CONTACT_MODEL,
        geometry_params=GEOM, depth_params=DEPTH_PARAMS_DEFAULT,
    )


def test_table_has_one_row_per_valid_alternative():
    alt_set = _alternatives()
    rows = build_comparison_table(alt_set)
    assert len(rows) == len(alt_set.valid)


def test_unsorted_table_preserves_generation_order():
    # La generación NO ordena por calidad (separación dimensionamiento/optimización).
    alt_set = _alternatives()
    rows = build_comparison_table(alt_set)
    assert [r.id for r in rows] == [a.id for a in alt_set.valid]


@pytest.mark.parametrize("sort_key", sorted(SORT_KEYS))
def test_every_sort_key_produces_monotonic_order(sort_key):
    rows = build_comparison_table(_alternatives(), sort_by=sort_key)
    values = [SORT_KEYS[sort_key](r) for r in rows]
    assert values == sorted(values)


def test_descending_sort_orders_values_from_high_to_low():
    # Se comparan VALORES, no ids: el sort es estable, así que ante empates el
    # orden de generación se conserva en ambos sentidos y los ids no se
    # reflejan simétricamente. Esa estabilidad es la conducta deseada.
    desc = build_comparison_table(_alternatives(), sort_by="volumen_concreto", descending=True)
    values = [r.concrete_volume_m3 for r in desc]
    assert values == sorted(values, reverse=True)

    asc = build_comparison_table(_alternatives(), sort_by="volumen_concreto")
    assert [r.concrete_volume_m3 for r in asc] == sorted(values)


def test_unknown_sort_key_is_rejected():
    with pytest.raises(ValueError, match="no reconocido"):
        build_comparison_table(_alternatives(), sort_by="menor_costo")


def test_render_respects_limit():
    rows = build_comparison_table(_alternatives(), sort_by="volumen_concreto")
    text = render_table_text(rows, limit=3)
    body_lines = [ln for ln in text.splitlines() if ln.startswith("ALT-")]
    assert len(body_lines) == 3
    if len(rows) > 3:
        assert "alternativas más" in text
