"""Estados de verificación del motor.

MÁQUINA DE ESTADOS (corregida tras la observación del usuario sobre la
inconsistencia "PASS vuelve a ser alcanzable en cuanto se implementen L3 y L4"):

    PASS          La verificación se ejecutó completa y cumple.
    INFO          Nota informativa. NO afecta la seguridad del resultado y por
                  tanto NO degrada el estado global (p. ej. no aplicar una
                  reducción normativa permitida: solo vuelve el diseño más
                  conservador).
    WARNING       La verificación se ejecutó pero está INCOMPLETA por una
                  limitación que podría hacer pasar por válido un diseño
                  inseguro. Obligatorio para toda limitación con
                  can_cause_false_pass=True que sea relevante.
    NO VERIFICADO La verificación es APLICABLE pero no pudo ejecutarse por falta
                  de datos de entrada (p. ej. coeficiente de fricción no
                  proporcionado). No se inventa el parámetro faltante.
    FAIL          La verificación se ejecutó y NO cumple. Descarta la alternativa.

REGLA DE AGREGACIÓN (severidad creciente):

    PASS = INFO  <  WARNING  <  NO VERIFICADO  <  FAIL

- INFO no escalona: un conjunto de PASS e INFO produce PASS.
- WARNING y NO VERIFICADO bloquean PASS pero NO descartan la alternativa.
- Solo FAIL descarta.

CONSECUENCIA EXPLÍCITA (lo que el usuario pidió corregir):
resolver L4 y L3 NO convierte automáticamente un WARNING en PASS. Si L1
(transferencia de momento en punzonamiento) sigue pendiente y ES APLICABLE
(hay Mu != 0), el estado global permanece en WARNING. PASS solo se alcanza
cuando NINGUNA limitación relevante con capacidad de producir un falso PASS
sigue sin implementar.
"""

from __future__ import annotations

from enum import Enum


class CheckStatus(str, Enum):
    PASS = "PASS"
    INFO = "INFO"
    WARNING = "WARNING"
    NOT_VERIFIED = "NO VERIFICADO"
    FAIL = "FAIL"

    @property
    def severity(self) -> int:
        return _SEVERITY[self]

    @property
    def blocks_pass(self) -> bool:
        """¿Impide que el estado global sea PASS?"""
        return _SEVERITY[self] >= _SEVERITY[CheckStatus.WARNING]

    @property
    def discards(self) -> bool:
        """¿Descarta la alternativa? Solo FAIL."""
        return self is CheckStatus.FAIL

    @staticmethod
    def worst(statuses: "list[CheckStatus]") -> "CheckStatus":
        if not statuses:
            return CheckStatus.NOT_VERIFIED
        worst_status = max(statuses, key=lambda s: _SEVERITY[s])
        # INFO no escalona: si lo peor es INFO, el conjunto se considera PASS.
        if _SEVERITY[worst_status] == 0:
            return CheckStatus.PASS
        return worst_status


_SEVERITY: dict[CheckStatus, int] = {
    CheckStatus.PASS: 0,
    CheckStatus.INFO: 0,
    CheckStatus.WARNING: 1,
    CheckStatus.NOT_VERIFIED: 2,
    CheckStatus.FAIL: 3,
}
