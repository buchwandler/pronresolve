"""Build-time pronunciation equivalence policies.

The module itself has no phonodist import so ordinary pronresolve consumers remain
runtime-dependency-free. The optional comparator is imported only when the explicit
phonodist policy is constructed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from collections.abc import Callable

from .normalization import normalize_ipa

StressPolicy = Literal["all", "primary"]

APPROVED_ZERO_COST_NOTATION_RULES = frozenset({"de-DE:affricate-notation"})


class PronunciationEquivalence(Protocol):
    """Policy boundary for build-time decisions about two IPA strings."""

    def equivalent(self, left: str, right: str) -> bool:
        """Return whether the two normalized pronunciations can be collapsed."""
        ...


@dataclass(frozen=True, slots=True)
class ExactEquivalence:
    """Treat only pronresolve-normalized, exactly equal IPA strings as equivalent."""

    def equivalent(self, left: str, right: str) -> bool:
        return normalize_ipa(left) == normalize_ipa(right)


class EquivalenceConfigurationError(ValueError):
    """Raised when an explicitly requested optional equivalence policy is unavailable."""


@dataclass(frozen=True, slots=True)
class PhonodistEquivalence:
    """Conservative structural comparison using phonodist's ``ipa-compare/1`` API."""

    language: str
    stress_policy: StressPolicy = "all"
    _compare_pronunciations: Callable[..., Any] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.language, str) or not self.language.strip():
            raise EquivalenceConfigurationError("phonodist equivalence requires a language profile")
        if self.stress_policy not in ("all", "primary"):
            raise ValueError("stress_policy must be 'all' or 'primary'")
        try:
            from phonodist import compare_pronunciations, get_profile
        except ImportError as exc:
            raise EquivalenceConfigurationError(
                "phonodist equivalence requires the optional 'phonetic' extra"
            ) from exc
        try:
            get_profile(self.language)
        except Exception as exc:
            raise EquivalenceConfigurationError(
                f"phonodist has no supported language profile for {self.language!r}"
            ) from exc
        object.__setattr__(self, "_compare_pronunciations", compare_pronunciations)

    def compare(self, left: str, right: str) -> Any:
        """Return an explained structural comparison (errors are handled by discovery)."""
        return self._compare_pronunciations(
            left,
            right,
            language=self.language,
            explain=True,
        )

    def evaluate(self, left: str, right: str) -> tuple[bool, Any]:
        """Return the safe decision and the comparison used to make it."""
        comparison = self.compare(left, right)
        return self.equivalent_comparison(comparison), comparison

    def equivalent(self, left: str, right: str) -> bool:
        return self.equivalent_comparison(self.compare(left, right))

    def equivalent_comparison(self, comparison: Any) -> bool:
        if self.stress_policy == "all":
            if not comparison.stress_equal:
                return False
        else:
            source_primary = tuple(
                event for event in comparison.source.stress if event.kind == "primary"
            )
            target_primary = tuple(
                event for event in comparison.target.stress if event.kind == "primary"
            )
            if source_primary != target_primary:
                return False

        if comparison.segment_equal:
            return True
        if comparison.segmental.distance != 0.0:
            return False

        approved_operations = 0
        for operation in comparison.segmental.operations:
            if operation.kind == "match":
                continue
            if not (
                operation.kind == "sequence_equivalence"
                and operation.cost == 0.0
                and operation.reason in APPROVED_ZERO_COST_NOTATION_RULES
            ):
                return False
            approved_operations += 1
        return approved_operations > 0
