import pytest
from pydantic import ValidationError

from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.materials import MaterialConcrete, MaterialSteel


def test_load_case_set_rejects_type_mismatch():
    with pytest.raises(ValidationError):
        LoadCaseSet(
            service=[LoadCombination(name="S1", type=LoadCombinationType.FACTORIZADA, P_kN=100.0)],
            factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=140.0)],
        )


def test_load_case_set_requires_both_lists_nonempty():
    with pytest.raises(ValidationError):
        LoadCaseSet(service=[], factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=140.0)])


def test_load_case_set_rejects_duplicate_names():
    with pytest.raises(ValidationError):
        LoadCaseSet(
            service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=100.0)],
            factored=[LoadCombination(name="S1", type=LoadCombinationType.FACTORIZADA, P_kN=140.0)],
        )


def test_concrete_fc_below_normative_minimum_rejected():
    with pytest.raises(ValidationError):
        MaterialConcrete(fc_MPa=10.0)


def test_steel_fy_above_normative_maximum_rejected():
    with pytest.raises(ValidationError):
        MaterialSteel(fy_MPa=600.0)
