"""Compile rich build-time lexical evidence into compact runtime cues."""

from __future__ import annotations

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
