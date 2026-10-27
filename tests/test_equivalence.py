import sys
from types import SimpleNamespace

import pytest

from pronresolve.equivalence import (
    EquivalenceConfigurationError,
    ExactEquivalence,
    PhonodistEquivalence,
)


def test_exact_equivalence_uses_pronresolve_normalization_only():
    policy = ExactEquivalence()
    assert policy.equivalent("/p/", "p")
    assert not policy.equivalent("ts", "t͡s")


def test_missing_phonodist_extra_has_configuration_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "phonodist", None)
    with pytest.raises(EquivalenceConfigurationError, match="optional 'phonetic' extra"):
        PhonodistEquivalence("de-DE")


def test_zero_cost_generic_feature_substitution_is_not_notation_identity():
    operation = SimpleNamespace(
        kind="substitute",
        cost=0.0,
        reason="feature vectors happen to match",
    )
    comparison = SimpleNamespace(
        stress_equal=True,
        source=SimpleNamespace(stress=()),
        target=SimpleNamespace(stress=()),
        segment_equal=False,
        segmental=SimpleNamespace(distance=0.0, operations=(operation,)),
    )
    policy = object.__new__(PhonodistEquivalence)
    object.__setattr__(policy, "stress_policy", "all")

    assert not policy.equivalent_comparison(comparison)


def test_german_prefix_primary_stress_is_never_collapsed():
    pytest.importorskip("phonodist")
    left = "ʊmˈfaːʁən"
    right = "ˈʊmˌfaːʁən"

    assert not PhonodistEquivalence("de-DE", "all").equivalent(left, right)
    assert not PhonodistEquivalence("de-DE", "primary").equivalent(left, right)


def test_secondary_stress_is_ignored_only_in_primary_mode():
    pytest.importorskip("phonodist")
    left = "ˈaˌpa"
    right = "ˈapa"

    assert not PhonodistEquivalence("de-DE", "all").equivalent(left, right)
    assert PhonodistEquivalence("de-DE", "primary").equivalent(left, right)


def test_german_affricate_notation_is_explicitly_equivalent():
    pytest.importorskip("phonodist")
    policy = PhonodistEquivalence("de-DE")

    assert policy.equivalent("t͡s", "ts")


def test_nonzero_schwa_syllabic_consonant_rule_is_not_equivalent():
    pytest.importorskip("phonodist")
    policy = PhonodistEquivalence("de-DE")
    comparison = policy.compare("n̩", "ən")

    assert comparison.segmental.distance > 0.0
    assert not policy.equivalent_comparison(comparison)


def test_unsupported_profile_is_a_configuration_error():
    pytest.importorskip("phonodist")
    with pytest.raises(EquivalenceConfigurationError, match="no supported language profile"):
        PhonodistEquivalence("xx-XX")
