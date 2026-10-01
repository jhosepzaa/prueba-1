"""Conversión de unidades de entrada.

La sección 17 del encargo pide explícitamente «evitar errores de conversión».
Estos tests contrastan cada factor contra valores de ingeniería conocidos, no
contra la propia tabla — un test que solo repitiera el factor no detectaría un
error de orden de magnitud como el que hubo en `kgf/cm²` de resistencia.
"""

import pytest

from engine.units.si_units import KGF_CM2_TO_MPA, KGF_TO_KN
from engine.units.unit_registry import (
    available_units,
    force_to_kN,
    length_to_m,
    moment_to_kNm,
    pressure_to_kPa,
    strength_to_MPa,
    unit_weight_to_kNm3,
)


# --- Coherencia con las constantes que ya existían en el motor ------------------

def test_registry_agrees_with_the_preexisting_constants():
    """si_units.py ya definía dos conversiones; el registro no puede contradecirlas."""
    assert strength_to_MPa(1.0, "kgf/cm²") == pytest.approx(KGF_CM2_TO_MPA, rel=1e-12)
    assert force_to_kN(1.0, "kgf") == pytest.approx(KGF_TO_KN, rel=1e-12)


# --- Valores de ingeniería conocidos --------------------------------------------

def test_typical_peruvian_concrete_and_steel_grades():
    """f'c = 210 kgf/cm² ≈ 21 MPa ; fy = 4200 kgf/cm² ≈ 420 MPa (grado 60)."""
    assert strength_to_MPa(210.0, "kgf/cm²") == pytest.approx(20.594, abs=0.01)
    assert strength_to_MPa(280.0, "kgf/cm²") == pytest.approx(27.459, abs=0.01)
    assert strength_to_MPa(4200.0, "kgf/cm²") == pytest.approx(411.879, abs=0.01)


def test_steel_grade_60_in_kgf_cm2_stays_under_the_normative_maximum():
    """El error corregido hacía que fy = 4200 kgf/cm² diera 4118 MPa y la
    validación normativa (máx. 550 MPa) rechazara un acero perfectamente común."""
    assert strength_to_MPa(4200.0, "kgf/cm²") < 550.0


def test_one_tonf_is_one_thousand_kgf():
    assert force_to_kN(1.0, "tonf") == pytest.approx(force_to_kN(1000.0, "kgf"), rel=1e-12)
    assert force_to_kN(1.0, "tonf") == pytest.approx(9.80665, rel=1e-9)


def test_one_kip_is_one_thousand_lbf():
    assert force_to_kN(1.0, "kip") == pytest.approx(force_to_kN(1000.0, "lbf"), rel=1e-12)
    assert force_to_kN(1.0, "kip") == pytest.approx(4.4482216, rel=1e-6)


def test_typical_allowable_pressures():
    """1,5 kgf/cm² ≈ 147 kPa ; 15 tonf/m² ≈ 147 kPa (equivalentes entre sí)."""
    assert pressure_to_kPa(1.5, "kgf/cm²") == pytest.approx(147.10, abs=0.01)
    assert pressure_to_kPa(15.0, "tonf/m²") == pytest.approx(147.10, abs=0.01)
    assert pressure_to_kPa(1.0, "kgf/cm²") == pytest.approx(pressure_to_kPa(10.0, "tonf/m²"), rel=1e-12)


def test_typical_unit_weights():
    """Concreto 2,4 tonf/m³ = 23,54 kN/m³ ; suelo 1,8 tonf/m³ = 17,65 kN/m³."""
    assert unit_weight_to_kNm3(2.4, "tonf/m³") == pytest.approx(23.536, abs=0.01)
    assert unit_weight_to_kNm3(1.8, "tonf/m³") == pytest.approx(17.652, abs=0.01)
    assert unit_weight_to_kNm3(150.0, "pcf") == pytest.approx(23.563, abs=0.01)


def test_imperial_pressure_and_strength():
    assert pressure_to_kPa(1.0, "psi") == pytest.approx(6.894757, rel=1e-6)
    assert strength_to_MPa(4000.0, "psi") == pytest.approx(27.579, abs=0.01)  # f'c típico ACI
    assert strength_to_MPa(60.0, "ksi") == pytest.approx(413.685, abs=0.01)   # grado 60


def test_length_conversions():
    assert length_to_m(1.0, "ft") == pytest.approx(0.3048, rel=1e-12)
    assert length_to_m(12.0, "in") == pytest.approx(length_to_m(1.0, "ft"), rel=1e-12)
    assert length_to_m(250.0, "cm") == pytest.approx(2.5, rel=1e-12)


def test_moment_units_are_consistent_with_force_times_length():
    """1 tonf·m debe ser exactamente 1 tonf × 1 m."""
    assert moment_to_kNm(1.0, "tonf·m") == pytest.approx(force_to_kN(1.0, "tonf") * 1.0, rel=1e-12)
    assert moment_to_kNm(1.0, "kgf·m") == pytest.approx(force_to_kN(1.0, "kgf") * 1.0, rel=1e-12)
    assert moment_to_kNm(1.0, "lbf·ft") == pytest.approx(
        force_to_kN(1.0, "lbf") * length_to_m(1.0, "ft"), rel=1e-12
    )
    assert moment_to_kNm(100.0, "kgf·cm") == pytest.approx(moment_to_kNm(1.0, "kgf·m"), rel=1e-12)


# --- Identidad y errores ---------------------------------------------------------

@pytest.mark.parametrize(
    "fn,unit",
    [
        (force_to_kN, "kN"), (moment_to_kNm, "kN·m"), (pressure_to_kPa, "kPa"),
        (strength_to_MPa, "MPa"), (length_to_m, "m"), (unit_weight_to_kNm3, "kN/m³"),
    ],
)
def test_si_units_are_the_identity(fn, unit):
    assert fn(123.456, unit) == pytest.approx(123.456, rel=1e-15)


def test_unknown_unit_is_rejected_with_a_helpful_message():
    with pytest.raises(ValueError, match="no reconocida"):
        force_to_kN(1.0, "quintales")


def test_catalog_matches_the_conversion_tables():
    catalog = available_units()
    assert set(catalog) == {"force", "moment", "pressure", "strength", "length", "unit_weight"}
    for group, entries in catalog.items():
        assert entries, group
        for entry in entries:
            assert entry["value"] and entry["label"]


def test_every_catalogued_unit_actually_converts():
    fns = {
        "force": force_to_kN, "moment": moment_to_kNm, "pressure": pressure_to_kPa,
        "strength": strength_to_MPa, "length": length_to_m, "unit_weight": unit_weight_to_kNm3,
    }
    for group, entries in available_units().items():
        for entry in entries:
            assert fns[group](1.0, entry["value"]) > 0, f"{group}/{entry['value']}"
