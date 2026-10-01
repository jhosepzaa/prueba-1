"""Conversión BIDIRECCIONAL y redondeo de presentación (2026-09-23).

El registro solo sabía convertir entrada → SI. Para que el usuario pueda cambiar
de unidad sin que el dato cambie de valor físico hacen falta las dos direcciones y
una regla de redondeo declarada.

Lo que se comprueba aquí:
  1. la vuelta devuelve el valor original (invariante del encargo);
  2. los valores de ingeniería conocidos salen donde deben, calculados A MANO en
     este archivo, sin llamar a la tabla que se está probando;
  3. el redondeo declarado (6 cifras) no mueve el dato más de lo anunciado.
"""

import math

import pytest

from engine.units.unit_registry import (
    DISPLAY_SIGNIFICANT_DIGITS,
    KIND_TABLES,
    SI_UNITS,
    available_units,
    convert,
    convert_for_display,
    from_si,
    round_significant,
    to_si,
)

G = 9.80665


# --- 1. Ida y vuelta -----------------------------------------------------------

@pytest.mark.parametrize("kind", sorted(KIND_TABLES))
def test_la_vuelta_devuelve_el_valor_original_en_todas_las_unidades(kind):
    """Sin redondear, convertir y volver es la identidad salvo error de máquina."""
    for unidad in KIND_TABLES[kind]:
        for valor in (0.0, 1.0, 21.0, 4200.0, 0.075):
            ida = convert(valor, kind, SI_UNITS[kind], unidad)
            assert convert(ida, kind, unidad, SI_UNITS[kind]) == pytest.approx(valor, rel=1e-12, abs=1e-15)


@pytest.mark.parametrize("kind", sorted(KIND_TABLES))
def test_la_unidad_si_tiene_factor_uno_y_no_altera_el_valor(kind):
    si = SI_UNITS[kind]
    assert KIND_TABLES[kind][si] == 1.0
    assert to_si(37.5, kind, si) == 37.5
    assert from_si(37.5, kind, si) == 37.5


def test_convertir_a_la_misma_unidad_no_toca_el_valor():
    v = 214.14040472536493
    assert convert(v, "strength", "kgf/cm²", "kgf/cm²") == v


# --- 2. Valores de ingeniería, calculados a mano -------------------------------

def test_el_caso_del_encargo_21_MPa_son_214_kgf_cm2():
    """1 kgf/cm² = 9,80665 N / 1e-4 m² = 0,0980665 MPa. 21 / 0,0980665 = 214,140…"""
    esperado = 21.0 / (G / 100.0)
    assert from_si(21.0, "strength", "kgf/cm²") == pytest.approx(esperado, rel=1e-12)
    assert convert_for_display(21.0, "strength", "MPa", "kgf/cm²") == pytest.approx(214.14, abs=5e-3)


def test_la_ida_y_vuelta_con_redondeo_devuelve_el_valor_de_partida():
    """21 MPa → 214,14 kgf/cm² → 21 MPa. Es el invariante que pidió el usuario."""
    ida = convert_for_display(21.0, "strength", "MPa", "kgf/cm²")
    vuelta = convert_for_display(ida, "strength", "kgf/cm²", "MPa")
    assert vuelta == pytest.approx(21.0, rel=1e-6)


def test_no_se_redondea_al_valor_comercial_vecino():
    """21 MPa NO son 210 kgf/cm²: son 214,14. El programa no ajusta a valores de catálogo."""
    assert convert_for_display(21.0, "strength", "MPa", "kgf/cm²") != pytest.approx(210.0, abs=1.0)


def test_valores_de_proyecto_habituales_en_el_peru():
    # f'c = 210 kgf/cm² → 210 · 0,0980665 = 20,5940 MPa
    assert to_si(210.0, "strength", "kgf/cm²") == pytest.approx(210.0 * G / 100.0, rel=1e-12)
    # q_adm = 1,5 kgf/cm² → 1,5 · 98,0665 = 147,100 kPa
    assert to_si(1.5, "pressure", "kgf/cm²") == pytest.approx(147.09975, rel=1e-12)
    # γ = 1,8 tonf/m³ → 17,6520 kN/m³
    assert to_si(1.8, "unit_weight", "tonf/m³") == pytest.approx(1.8 * G, rel=1e-12)
    # 100 tonf → 980,665 kN
    assert to_si(100.0, "force", "tonf") == pytest.approx(100.0 * G, rel=1e-12)


# --- 3. Redondeo declarado -----------------------------------------------------

def test_el_redondeo_conserva_seis_cifras_significativas():
    assert round_significant(214.14040472536493) == 214.14
    assert round_significant(0.000123456789) == 0.000123457
    assert round_significant(-98765432.1) == -98765400.0
    assert round_significant(0.0) == 0.0


def test_el_redondeo_no_mueve_el_valor_mas_de_lo_anunciado():
    """Error relativo ≤ 5·10⁻⁶, que es lo que declara DISPLAY_SIGNIFICANT_DIGITS.

    Es la cota del redondeo a d cifras: 0,5·10^(exp−d+1) de error absoluto sobre un
    valor del orden de 10^exp. Con d = 6 son cinco partes por millón."""
    cota = 0.5 * 10.0 ** (1 - DISPLAY_SIGNIFICANT_DIGITS)
    for valor in (21.0, 214.14040472536493, 4282.6, 0.0751234567, 1234567.89):
        assert abs(round_significant(valor) - valor) <= cota * abs(valor)


def test_el_redondeo_deja_pasar_los_no_finitos_sin_romperse():
    assert math.isnan(round_significant(float("nan")))
    assert math.isinf(round_significant(float("inf")))


# --- 4. Catálogo para la interfaz ----------------------------------------------

def test_el_catalogo_entrega_el_factor_de_cada_unidad():
    """La interfaz presenta con estos factores; si faltan, tendría que inventarlos."""
    catalogo = available_units()
    assert set(catalogo) == set(KIND_TABLES)
    for kind, entradas in catalogo.items():
        assert {e["value"] for e in entradas} == set(KIND_TABLES[kind])
        for e in entradas:
            assert e["to_si"] == KIND_TABLES[kind][e["value"]]
            assert e["label"]


def test_una_unidad_desconocida_se_rechaza_con_su_nombre():
    with pytest.raises(ValueError, match="resistencia"):
        to_si(1.0, "strength", "MPaa")
    with pytest.raises(ValueError, match="Magnitud no reconocida"):
        to_si(1.0, "temperatura", "K")
