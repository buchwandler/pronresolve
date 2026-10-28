"""Compile rich build-time lexical evidence into compact runtime cues."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable, Mapping

from .models import Cue
from .normalization import STOPWORDS, tokens

# One owner for runtime scoring policy. Examples intentionally do not participate.
EVIDENCE_WEIGHTS: dict[str, float] = {
    "synonyms": 3.5,
    "glosses": 3.0,
    "topics": 2.5,
    "tags": 1.0,
    # TODO: Antonyms currently behave as positive lexical association. Review
    # separately for removal or signed evidence; do not change this weight here.
    "antonyms": 0.75,
}


def compile_cues(evidence: Mapping[str, Iterable[str]]) -> tuple[Cue, ...]:
    """Return unique, deterministically ordered cues compiled under Policy B.

    Every field is tokenized with the same normalization rules as sentence
    context. If a token occurs in multiple evidence fields, its maximum weight
    is retained rather than summing the evidence.
    """
    weights: dict[str, float] = {}
    for field, weight in EVIDENCE_WEIGHTS.items():
        values = evidence.get(field, ())
        if isinstance(values, str):
            values = (values,)
        for value in values:
            if not isinstance(value, str):
                continue
            for token in tokens(value):
                if token in STOPWORDS:
                    continue
                weights[token] = max(weights.get(token, 0.0), weight)
    return tuple(Cue(token=token, weight=weights[token]) for token in sorted(weights))


@dataclass(frozen=True, slots=True)
class ContrastiveCueCompilation:
    """Cue maps pruned against a complete candidate group."""

    cue_sets: tuple[tuple[Cue, ...], ...]
    shared_tokens: tuple[str, ...] = ()
    reason: str | None = None

    @property
    def selectable(self) -> bool:
        return self.reason is None


def compile_contrastive_cues(
    candidates: Iterable[Iterable[Cue]],
) -> ContrastiveCueCompilation:
    """Drop universally shared cues and fail closed on non-selectable groups."""
    candidate_cues = tuple(tuple(candidate) for candidate in candidates)
    if len(candidate_cues) < 2:
        raise ValueError("contrastive cue compilation requires at least two candidates")
    if any(any(not isinstance(cue, Cue) for cue in candidate) for candidate in candidate_cues):
        raise ValueError("contrastive cue candidates must contain Cue values")

    candidate_maps: list[dict[str, float]] = []
    for candidate in candidate_cues:
        cue_map: dict[str, float] = {}
        for cue in candidate:
            cue_map[cue.token] = max(cue_map.get(cue.token, 0.0), cue.weight)
        candidate_maps.append(cue_map)

    shared_tokens = tuple(sorted(set.intersection(*(set(cue_map) for cue_map in candidate_maps))))
    shared = set(shared_tokens)
    pruned_maps = [
        {token: weight for token, weight in cue_map.items() if token not in shared}
        for cue_map in candidate_maps
    ]
    cue_sets = tuple(
        tuple(Cue(token=token, weight=cue_map[token]) for token in sorted(cue_map))
        for cue_map in pruned_maps
    )
    signatures = [tuple((cue.token, cue.weight) for cue in cues) for cues in cue_sets]
    if len(set(signatures)) != len(signatures):
        reason = "non_discriminative_rules"
    elif any(not cues for cues in cue_sets):
        reason = "insufficient_contrastive_evidence"
    else:
        reason = None
    return ContrastiveCueCompilation(
        cue_sets=cue_sets,
        shared_tokens=shared_tokens,
        reason=reason,
    )
