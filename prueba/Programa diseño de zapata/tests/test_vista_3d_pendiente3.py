"""Pendiente 3 — vista 3D de la zapata combinada y del sistema conectado.

Es paridad de PRESENTACIÓN: la zapata aislada ya tenía visor 3D; las otras dos, solo planta
y alzado. No cambia ningún criterio, ninguna ecuación ni ningún estado.

La regla que estos tests protegen es la de `scene_dto.py`: **la visualización muestra datos
ya calculados y NUNCA los recalcula**. Los dos visores nuevos consumen exactamente los
mismos DTO que ya alimentan los esquemas 2D —`CombinedSceneDTO` y `ConnectedSceneDTO`—, de
modo que no hay una segunda fuente de posiciones que pueda divergir.

Lo que NO dibujan, y por qué: el armado. El motor resuelve posiciones de barra solo para la
zapata aislada (`FootingRebarGeometry`); dibujar un armado inventado para las otras dos
sería exactamente lo que la regla prohíbe.
"""

from __future__ import annotations

import io
import pathlib

from engine.integration.typology_catalog import CATALOG

UI = pathlib.Path("ui/src/components")


def _fuente(nombre: str) -> str:
    return io.open(UI / nombre, encoding="utf-8").read()


# =========================================================================
# 1. Los visores existen y consumen el DTO del motor
# =========================================================================


def test_los_dos_visores_existen():
    for nombre in ("BoxScene3D.tsx", "CombinedScene3D.tsx", "ConnectedScene3D.tsx"):
        assert (UI / nombre).exists(), nombre


def test_el_visor_de_la_combinada_usa_el_mismo_dto_que_el_esquema_2d():
    fuente = _fuente("CombinedScene3D.tsx")
    assert "CombinedSceneOut" in fuente
    for usado in ("scene.footing", "scene.columns", "scene.dimensions", "scene.status",
                  "scene.status_label", "scene.status_note", "scene.scope_note"):
        assert usado in fuente, usado


def test_el_visor_de_la_conectada_usa_el_mismo_dto_que_el_esquema_2d():
    fuente = _fuente("ConnectedScene3D.tsx")
    assert "ConnectedSceneOut" in fuente
    for usado in ("scene.exterior_footing", "scene.interior_footing", "scene.beam",
                  "scene.exterior_column", "scene.interior_column", "scene.dimensions",
                  "scene.scope_note", "scene.open_tbds"):
        assert usado in fuente, usado


# =========================================================================
# 2. No recalculan nada ni inventan armado
# =========================================================================


def test_ningun_visor_recalcula_geometria_ni_ingenieria():
    for nombre in ("BoxScene3D.tsx", "CombinedScene3D.tsx", "ConnectedScene3D.tsx"):
        fuente = _fuente(nombre)
        for prohibido in ("Math.sqrt", "qadm", "As_", "Mu", "phi", "0.85"):
            assert prohibido not in fuente, f"{nombre}: {prohibido}"


def test_ningun_visor_nuevo_dibuja_armado():
    """El motor no resuelve posiciones de barra para estas dos tipologías."""
    for nombre in ("BoxScene3D.tsx", "CombinedScene3D.tsx", "ConnectedScene3D.tsx"):
        fuente = _fuente(nombre)
        for prohibido in ("cylinderGeometry", "BarOut", "bars"):
            assert prohibido not in fuente, f"{nombre}: {prohibido}"


def test_la_logica_del_visor_esta_en_un_solo_sitio():
    """`BoxScene3D` es el visor; los otros dos solo eligen colores y delegan."""
    for nombre in ("CombinedScene3D.tsx", "ConnectedScene3D.tsx"):
        fuente = _fuente(nombre)
        assert "BoxScene3D" in fuente
        for propio_del_visor in ("<Canvas", "OrbitControls", "boxGeometry"):
            assert propio_del_visor not in fuente, f"{nombre}: {propio_del_visor}"
    visor = _fuente("BoxScene3D.tsx")
    for propio in ("<Canvas", "OrbitControls", "boxGeometry"):
        assert propio in visor


# =========================================================================
# 3. El estado viaja con el dibujo
# =========================================================================


def test_el_visor_muestra_el_estado_crudo_y_el_rotulo():
    """Un dibujo limpio se lee como un diseño conforme: el estado tiene que verse."""
    visor = _fuente("BoxScene3D.tsx")
    assert "statusLabel" in visor and "status" in visor
    assert "statusNote" in visor, "El aviso de «no conforme» llega hasta el visor"
    assert "NUNCA lo presenta como PASS" in visor


# =========================================================================
# 4. Los visores están conectados a sus vistas, y el catálogo lo declara
# =========================================================================


def _montado(nombre: str, componente: str) -> bool:
    """¿Se RENDERIZA el componente, o solo aparece nombrado? Importarlo o dejarlo
    comentado no lo monta: la línea tiene que ser JSX vivo. Lo detectó una mutación."""
    for linea in _fuente(nombre).splitlines():
        limpia = linea.strip()
        if limpia.startswith(("//", "{/*", "*", "/*")):
            continue
        if f"<{componente}" in limpia:
            return True
    return False


def test_las_vistas_de_resultados_montan_el_visor():
    assert _montado("CombinedResultsView.tsx", "CombinedScene3D")
    assert _montado("ConnectedResultsView.tsx", "ConnectedScene3D")
    # Y el esquema 2D sigue montado: la vista 3D lo acompaña, no lo sustituye.
    assert _montado("CombinedResultsView.tsx", "CombinedFootingDiagram")
    assert _montado("ConnectedResultsView.tsx", "ConnectedSystemDiagram")


def test_el_catalogo_declara_la_vista_3d_en_las_tres_tipologias():
    for t in CATALOG.typologies:
        assert t.capabilities["vista_3d"] is True, t.id
        assert t.capabilities["esquema_2d"] is True, t.id


def test_la_diferencia_de_presentacion_queda_cerrada():
    dif = {k.id: k for k in CATALOG.known_differences}
    assert dif["PRESENTACION_COMBINADA"].resolution is not None
