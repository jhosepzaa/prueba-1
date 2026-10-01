"""FASE 5B — D2: causa explícita del fallo por punzonamiento.

EL DEFECTO
==========
`depth_solver` decidía el motivo de descarte con `critical_section_fits`, que significa
«la sección crítica se cierra por los cuatro lados». Ese campo es `False` en TODA
columna de borde o esquina, cuya sección de 3 o 2 lados es perfectamente utilizable
—tiene su perímetro, su α_s y su Jc—. Una zapata de lindero que fallaba por capacidad
recibía «la sección crítica no cabe».

LO QUE SE FIJA AQUÍ
===================
1. `failure_cause` distingue las tres ramas de fallo del motor: sección degenerada,
   capacidad por cortante directo, capacidad con transferencia de momento (§11.12.7).
2. `critical_section_fits=False` por sí solo NUNCA produce «degenerada».
3. Los números del punzonamiento no cambian; el conjunto de textos de descarte —que son
   las categorías por las que agrupan el informe y la API— tampoco, ni `n_descartes`.
4. Aragón P1 se explica como insuficiencia de capacidad con los valores conocidos.
5. Coherencia en aislada, combinada y conectada.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.foundation.combined_solver import solve_combined_footing
from engine.foundation.punching_shear import (
    PUNCHING_DISCARD_CAPACITY,
    PUNCHING_DISCARD_DEGENERATE,
    PunchingFailureCause,
    PunchingShearResult,
    check_punching_shear,
    punching_discard_reason,
)
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import KernCheckModel
from tests.freeze.cases import CASES, COMBINED_CASES, CONNECTED_CASES
from tests.freeze.snapshot import DIAGNOSTIC_FIELDS
from tests.freeze.test_freeze_connected import _solve as _solve_conectada
from tests.freeze.test_freeze_isolated import _evaluate

CODE = E060ConcreteCode()
KERN = KernCheckModel()
FREEZE = Path(__file__).parent / "freeze"

# Geometría base de los tests unitarios: zapata 2,0 × 2,0 m, columna 0,40 m, d = 0,40 m.
B = L = 2.0
b = 0.40
d = 0.40
AL_BORDE = B / 2 - b / 2  # desplazamiento que deja la cara de la columna en el borde

CAUSAS = PunchingFailureCause
TEXTOS_LEGADOS = {PUNCHING_DISCARD_DEGENERATE, PUNCHING_DISCARD_CAPACITY}


def _punz(P, *, Bz=B, Lz=L, ox=0.0, oy=0.0, Mx=0.0, My=0.0) -> PunchingShearResult:
    return check_punching_shear(P, Bz, Lz, b, b, d, 21.0, CODE,
                                Mux_kNm=Mx, Muy_kNm=My, offset_x_m=ox, offset_y_m=oy)


# =========================================================================
# 1. Las tres causas, por posición de columna
# =========================================================================


def test_columna_interior_que_pasa_no_tiene_causa():
    r = _punz(600)
    assert (r.column_position, r.critical_section_fits, r.critical_section_usable) == ("interior", True, True)
    assert r.status is CheckStatus.PASS
    assert r.failure_cause is None


def test_columna_interior_falla_por_cortante_directo():
    r = _punz(2600)
    assert r.column_position == "interior" and r.critical_section_fits
    assert r.status is CheckStatus.FAIL
    assert r.failure_cause is CAUSAS.CAPACIDAD_CORTANTE_DIRECTO
    assert r.Vu_kN > r.phi_Vc_kN
    assert punching_discard_reason(r) == PUNCHING_DISCARD_CAPACITY


def test_columna_interior_falla_por_transferencia_de_momento_con_ratio_directo_bajo():
    """El caso que desmiente cualquier inferencia desde `ratio`: el cortante directo
    pasa holgado (0,46) y el estado es FAIL porque §11.12.7 gobierna."""
    r = _punz(900, Mx=800)
    assert r.column_position == "interior"
    assert r.ratio < 1.0
    assert r.moment_transfer is not None and r.moment_transfer.ratio > 1.0
    assert r.status is CheckStatus.FAIL
    assert r.failure_cause is CAUSAS.CAPACIDAD_TRANSFERENCIA_MOMENTO


def test_columna_de_borde_con_fits_false_es_utilizable_y_puede_pasar():
    """Requisito 5 y 8: `critical_section_fits=False` con una sección de 3 lados que
    SÍ se verifica —y en este caso cumple—."""
    r = _punz(300, ox=AL_BORDE)
    assert r.column_position == "borde" and r.critical_section_sides == 3
    assert r.critical_section_fits is False
    assert r.critical_section_usable is True
    assert r.alpha_s == 30.0
    assert r.status is CheckStatus.PASS
    assert r.failure_cause is None


@pytest.mark.parametrize("P, M, causa", [
    (1500, 0.0, CAUSAS.CAPACIDAD_CORTANTE_DIRECTO),
    (350, 300.0, CAUSAS.CAPACIDAD_TRANSFERENCIA_MOMENTO),
])
def test_columna_de_borde_que_falla_lo_hace_por_capacidad_no_por_geometria(P, M, causa):
    r = _punz(P, ox=AL_BORDE, Mx=M)
    assert r.column_position == "borde" and r.critical_section_fits is False
    assert r.critical_section_usable
    assert r.status is CheckStatus.FAIL
    assert r.failure_cause is causa
    assert punching_discard_reason(r) == PUNCHING_DISCARD_CAPACITY, (
        "Una sección de borde utilizable que falla por capacidad no puede reportarse "
        "como «no cabe»: ese es exactamente el defecto D2."
    )


def test_columna_de_esquina_con_fits_false_es_utilizable_y_puede_pasar():
    r = _punz(150, ox=AL_BORDE, oy=AL_BORDE)
    assert r.column_position == "esquina" and r.critical_section_sides == 2
    assert r.critical_section_fits is False and r.critical_section_usable
    assert r.alpha_s == 20.0
    assert r.status is CheckStatus.PASS and r.failure_cause is None


@pytest.mark.parametrize("P, M, causa", [
    (900, 0.0, CAUSAS.CAPACIDAD_CORTANTE_DIRECTO),
    (200, 250.0, CAUSAS.CAPACIDAD_TRANSFERENCIA_MOMENTO),
])
def test_columna_de_esquina_que_falla_lo_hace_por_capacidad(P, M, causa):
    r = _punz(P, ox=AL_BORDE, oy=AL_BORDE, My=M)
    assert r.column_position == "esquina" and r.critical_section_fits is False
    assert r.status is CheckStatus.FAIL
    assert r.failure_cause is causa
    assert punching_discard_reason(r) == PUNCHING_DISCARD_CAPACITY


@pytest.mark.parametrize("Bz, Lz, oy, recortados", [
    (0.60, 2.0, 1.0 - b / 2, 3),
    (0.60, 0.60, 0.0, 4),
])
def test_seccion_degenerada_es_la_unica_causa_geometrica(Bz, Lz, oy, recortados):
    r = _punz(200, Bz=Bz, Lz=Lz, oy=oy)
    assert r.column_position == "degenerada"
    assert r.critical_section_usable is False
    assert r.status is CheckStatus.FAIL
    assert r.failure_cause is CAUSAS.SECCION_CRITICA_DEGENERADA
    assert punching_discard_reason(r) == PUNCHING_DISCARD_DEGENERATE
    assert 4 - r.critical_section_sides == recortados


def test_fits_false_por_si_solo_nunca_produce_seccion_degenerada():
    """Barrido de posiciones de columna y cargas: en TODO resultado con fits=False que
    no sea degenerado, la causa —si la hay— es de capacidad."""
    vistos = set()
    for ox in (0.0, 0.3, AL_BORDE):
        for oy in (0.0, 0.3, AL_BORDE):
            for P in (150, 400, 900, 1500, 2600):
                for M in (0.0, 300.0):
                    r = _punz(P, ox=ox, oy=oy, Mx=M)
                    if r.critical_section_fits:
                        continue
                    vistos.add(r.column_position)
                    assert r.column_position in ("borde", "esquina")
                    assert r.critical_section_usable
                    assert r.failure_cause is not CAUSAS.SECCION_CRITICA_DEGENERADA
                    if r.status is CheckStatus.FAIL:
                        assert punching_discard_reason(r) == PUNCHING_DISCARD_CAPACITY
    assert vistos == {"borde", "esquina"}, "el barrido debe cubrir las dos clases truncadas"


# =========================================================================
# 2. La causa no puede contradecir al estado
# =========================================================================


def test_un_FAIL_sin_causa_no_se_puede_construir():
    r = _punz(2600)
    with pytest.raises(ValueError, match="debe declarar su `failure_cause`"):
        PunchingShearResult(**{**r.model_dump(), "failure_cause": None})


def test_un_PASS_con_causa_no_se_puede_construir():
    r = _punz(600)
    with pytest.raises(ValueError, match="solo un FAIL tiene causa"):
        PunchingShearResult(**{**r.model_dump(),
                               "failure_cause": CAUSAS.CAPACIDAD_CORTANTE_DIRECTO})


def test_el_motivo_de_descarte_solo_devuelve_los_dos_textos_legados():
    """Los textos de descarte son las categorías por las que agrupan el informe y la
    API. Siguen siendo exactamente los dos de antes de la Fase 5B."""
    assert PUNCHING_DISCARD_CAPACITY == "Punzonamiento no cumple."
    assert PUNCHING_DISCARD_DEGENERATE == (
        "Sección crítica de punzonamiento no cabe en la zapata (d/2 excede el voladizo disponible)."
    )
    for r in (_punz(2600), _punz(900, Mx=800), _punz(200, Bz=0.60, Lz=0.60)):
        assert punching_discard_reason(r) in TEXTOS_LEGADOS
    with pytest.raises(ValueError):
        punching_discard_reason(_punz(600))


# =========================================================================
# 3. Regresión Aragón P1 (y P2)
# =========================================================================


def _conectada(nombre):
    c = next(x for x in CONNECTED_CASES if x.name == nombre)
    return _solve_conectada(c)


def test_aragon_p1_se_explica_como_capacidad_con_transferencia_de_momento():
    r = _conectada("Z11_aragon_p1_articulado")
    p = r.exterior.punching

    assert p.column_position == "borde" and p.critical_section_fits is False
    assert p.critical_section_usable
    assert p.failure_cause is CAUSAS.CAPACIDAD_TRANSFERENCIA_MOMENTO
    # Fase 10A (A1): con el recubrimiento de 75 mm de §7.7.1 a) el peralte baja 5 mm y el
    # esfuerzo máximo pasa de 1.8225 a 1.8550 MPa; φvn no depende de d en este caso.
    assert p.moment_transfer.v_max_MPa == pytest.approx(1.8550, abs=5e-4)
    assert p.moment_transfer.phi_vn_MPa == pytest.approx(1.2854, abs=5e-4)
    assert p.moment_transfer.v_max_MPa > p.moment_transfer.phi_vn_MPa

    assert PUNCHING_DISCARD_DEGENERATE not in r.exterior.discard_reasons
    assert PUNCHING_DISCARD_CAPACITY in r.exterior.discard_reasons
    assert f"[Z1] {PUNCHING_DISCARD_CAPACITY}" in r.discard_reasons
    assert not any("no cabe en la zapata" in m for m in r.discard_reasons)

    # La explicación con valores está en la traza, junto a la causa explícita.
    entrada = r.trace.by_id("punching", scope="zap_ext")
    texto = " ".join(entrada.hypotheses)
    assert "Causa del fallo: CAPACIDAD_TRANSFERENCIA_MOMENTO" in texto
    assert "1.8550" in texto and "1.2854" in texto


def test_aragon_p2_zapata_de_lindero_tampoco_se_reporta_como_no_cabe():
    r = _conectada("Z12_aragon_p2_cuerpo_rigido")
    assert r.exterior.punching.failure_cause is CAUSAS.CAPACIDAD_TRANSFERENCIA_MOMENTO
    assert r.interior.punching.failure_cause is CAUSAS.CAPACIDAD_TRANSFERENCIA_MOMENTO
    assert not any("no cabe en la zapata" in m for m in r.discard_reasons)


# =========================================================================
# 4. Coherencia en las tres tipologías
# =========================================================================


def _todos_los_punzonamientos():
    """(tipología/caso, resultado de punzonamiento, motivos del componente) de todos los
    casos congelados que el motor resuelve."""
    for c in CASES:
        r = _evaluate(c)
        yield f"aislada/{c.name}", r.punching, r.discard_reasons
    for c in COMBINED_CASES:
        r = solve_combined_footing(c.layout, c.h_m, soil=c.soil, concrete=c.concrete,
                                   steel=c.steel, code=CODE, contact_model=KERN,
                                   top_cover=c.top_cover)
        for p in r.punching:
            yield f"combinada/{c.name}", p, r.discard_reasons
    for c in CONNECTED_CASES:
        if c.expects_rejection:
            continue
        r = _solve_conectada(c)
        yield f"conectada/{c.name}/Z1", r.exterior.punching, r.exterior.discard_reasons
        yield f"conectada/{c.name}/Z2", r.interior.punching, r.interior.discard_reasons


def test_la_causa_es_coherente_en_todos_los_casos_congelados():
    """Protección dedicada de `failure_cause`, que el congelamiento genérico no recorre
    (ver DIAGNOSTIC_FIELDS)."""
    n = 0
    for nombre, p, _ in _todos_los_punzonamientos():
        n += 1
        assert (p.status is CheckStatus.FAIL) == (p.failure_cause is not None), nombre
        if p.failure_cause is CAUSAS.SECCION_CRITICA_DEGENERADA:
            assert not p.critical_section_usable, nombre
        elif p.failure_cause is not None:
            assert p.critical_section_usable, nombre
    assert n > 40


def test_aislada_y_conectada_emiten_solo_los_textos_legados():
    for nombre, p, motivos in _todos_los_punzonamientos():
        if nombre.startswith("combinada"):
            continue
        de_punz = [m for m in motivos if "unzonamiento" in m]
        assert set(de_punz) <= TEXTOS_LEGADOS, (nombre, de_punz)
        if p.status is CheckStatus.FAIL:
            assert de_punz == [punching_discard_reason(p)], nombre


def test_combinada_con_columna_de_borde_que_falla_por_momento():
    """K2 con h = 0,30 m: columna en límite de propiedad —borde, fits=False— que falla
    por §11.12.7. La combinada conserva su texto de descarte (su categoría) y gana la
    causa explícita, la misma que darían la aislada y la conectada."""
    c = next(x for x in COMBINED_CASES if x.name == "K2_columna_en_limite_de_propiedad")
    r = solve_combined_footing(c.layout, 0.30, soil=c.soil, concrete=c.concrete,
                               steel=c.steel, code=CODE, contact_model=KERN,
                               top_cover=c.top_cover)
    borde = next(p for p in r.punching if p.column_position == "borde")
    assert borde.critical_section_fits is False and borde.critical_section_usable
    assert borde.status is CheckStatus.FAIL
    assert borde.failure_cause is CAUSAS.CAPACIDAD_TRANSFERENCIA_MOMENTO

    de_punz = [m for m in r.discard_reasons if "unzonamiento" in m]
    assert de_punz and all(re.fullmatch(r"Punzonamiento en \S+ no cumple\.", m) for m in de_punz)
    entradas = [e for e in r.trace.entries if e.id.startswith("punching_") and e.status is CheckStatus.FAIL]
    assert any("Causa del fallo: CAPACIDAD_TRANSFERENCIA_MOMENTO" in " ".join(e.hypotheses)
               for e in entradas)


# =========================================================================
# 5. Invariantes: números, n_descartes y congelamiento
# =========================================================================


def test_n_descartes_coincide_con_los_baselines():
    """El congelamiento guarda `n_descartes` pero ningún test de congelamiento lo
    compara. Se comprueba aquí, contra los dos baselines congelados."""
    base = json.loads((FREEZE / "baseline.json").read_text(encoding="utf-8"))
    for c in CASES:
        assert len(_evaluate(c).discard_reasons) == base[c.name]["n_descartes"], c.name
    for c in COMBINED_CASES:
        r = solve_combined_footing(c.layout, c.h_m, soil=c.soil, concrete=c.concrete,
                                   steel=c.steel, code=CODE, contact_model=KERN,
                                   top_cover=c.top_cover)
        assert len(r.discard_reasons) == base[c.name]["n_descartes"], c.name

    con = json.loads((FREEZE / "baseline_connected.json").read_text(encoding="utf-8"))
    for c in CONNECTED_CASES:
        if c.expects_rejection:
            continue
        assert len(_solve_conectada(c).discard_reasons) == con[c.name]["n_descartes"], c.name


def test_la_causa_esta_excluida_del_congelamiento_generico_y_solo_ella():
    """Documenta la decisión: `failure_cause` es diagnóstico y no altera números ni
    estados. Excluirlo mantiene los baselines idénticos; lo protegen los tests de este
    archivo. La exclusión es por (modelo, campo) y no se extiende a nada más.

    Única ampliación deliberada: Fase 9b, `ConnectedFootingResult.beam_axis` (geometría de
    la viga de la que sale `beam_span_m`, que sí se congela), protegida por
    `tests/test_beam_span_metrics_phase9b.py`; Fase 2, `CombinedFootingResult.discard_records`,
    protegida por `tests/test_combined_discards_phase2.py`; FORMULACION_VOLTEO, las dos lecturas
    de la envolvente del momento volcador —su máximo, que es el que manda, sí se congela en
    `applied_moment_kNm`—, protegidas por `tests/test_formulacion_volteo.py`. Cualquier otra
    exige revisar este test."""
    assert DIAGNOSTIC_FIELDS == frozenset({
        ("PunchingShearResult", "failure_cause"),
        ("ConnectedFootingResult", "beam_axis"),
        ("CombinedFootingResult", "discard_records"),
        ("OverturningResult", "applied_moment_total_kNm"),
        ("OverturningResult", "applied_moment_dead_kNm"),
    })
