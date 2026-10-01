from engine.domain.search_parameters import GeometrySearchParameters
from engine.foundation.geometry_generator import generate_geometry_candidates


def test_generates_expected_grid_within_ratio():
    params = GeometrySearchParameters(
        B_min_m=1.0, B_max_m=1.2, B_step_m=0.1,
        L_min_m=1.0, L_max_m=1.2, L_step_m=0.1,
        max_LB_ratio=1.15,
    )
    candidates = list(generate_geometry_candidates(params))
    # B,L en {1.0,1.1,1.2} -> 9 combinaciones, excluyendo las que violan ratio 1.15
    for c in candidates:
        ratio = max(c.B_m, c.L_m) / min(c.B_m, c.L_m)
        assert ratio <= 1.15 + 1e-9
    assert any(c.B_m == 1.0 and c.L_m == 1.0 for c in candidates)
    # 1.0 vs 1.2 -> ratio 1.2 > 1.15 -> debe excluirse
    assert not any(c.B_m == 1.0 and c.L_m == 1.2 for c in candidates)
