"""Deterministic, explainable context-based pronunciation resolution."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .models import AmbiguityIndex, CandidateScore, ReadingProfile, Resolution
from .normalization import STOPWORDS, normalize_pos, normalize_word, token_spans
from .storage import load_index


class Resolver:
    """Resolve a token only when lexical evidence and score margin are sufficient."""

    def __init__(
        self,
        index: AmbiguityIndex | str | Path,
        *,
        min_score: float = 1.0,
        min_margin: float = 0.75,
    ) -> None:
        self.index = load_index(index) if isinstance(index, (str, Path)) else index
        if min_score < 0 or min_margin < 0:
            raise ValueError("min_score and min_margin must be non-negative")
        self.min_score = float(min_score)
        self.min_margin = float(min_margin)
        by_word: dict[str, dict[str, list[ReadingProfile]]] = defaultdict(lambda: defaultdict(list))
        self._cue_maps: dict[str, dict[str, float]] = {}
        for profile in self.index.profiles:
            word = normalize_word(profile.word)
            pos = normalize_pos(profile.pos)
            by_word[word][pos].append(profile)
            self._cue_maps[profile.reading_id] = {cue.token: cue.weight for cue in profile.cues}
        self._by_word = {
            word: {
                pos: tuple(sorted(profiles, key=lambda profile: profile.reading_id))
                for pos, profiles in groups.items()
            }
            for word, groups in by_word.items()
        }

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        min_score: float = 1.0,
        min_margin: float = 0.75,
    ) -> Resolver:
        return cls(path, min_score=min_score, min_margin=min_margin)

    def resolve(
        self,
        text: str,
        *,
        start: int,
        end: int,
        pos: str | None = None,
        lemma: str | None = None,
    ) -> Resolution | None:
        """Resolve the token spanning ``[start, end)`` in the original sentence.

        Returns ``None`` for unknown words, insufficient evidence, a close score
        tie, invalid offsets, or an omitted POS when the word has ambiguous POS groups.
        """
        if (
            not isinstance(text, str)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end <= start
            or end > len(text)
        ):
            return None
        target_text = lemma or text[start:end]
        word = normalize_word(target_text)
        if not word:
            return None

        pos_groups = self._by_word.get(word)
        if not pos_groups:
            return None
        if pos is not None:
            profiles = pos_groups.get(normalize_pos(pos), ())
        else:
            if len(pos_groups) != 1:
                return None
            profiles = next(iter(pos_groups.values()))
        if len(profiles) < 2:
            return None

        spans = token_spans(text)
        target_index = next(
            (index for index, span in enumerate(spans) if span.start < end and span.end > start),
            sum(1 for span in spans if span.end <= start),
        )
        cue_distances: dict[str, int] = {}
        for index, span in enumerate(spans):
            if span.start < end and span.end > start:
                continue
            term = span.normalized
            if not term or term in STOPWORDS or term == word:
                continue
            distance = abs(index - target_index)
            prior = cue_distances.get(term)
            if prior is None or distance < prior:
                cue_distances[term] = distance

        if not cue_distances:
            return None

        scored: list[CandidateScore] = []
        profile_by_id = {profile.reading_id: profile for profile in profiles}
        for profile in profiles:
            candidate_cues = self._cue_maps[profile.reading_id]
            score = 0.0
            matched: list[str] = []
            for term, distance in cue_distances.items():
                matching_weight = candidate_cues.get(term, 0.0)
                if matching_weight:
                    # Adjacent evidence is strongest; distant cues still contribute.
                    distance_factor = 1.0 / (1.0 + 0.15 * max(distance - 1, 0))
                    score += matching_weight * distance_factor
                    matched.append(term)
            scored.append(
                CandidateScore(
                    reading_id=profile.reading_id,
                    score=round(score, 6),
                    matched_terms=tuple(matched),
                )
            )

        scored.sort(key=lambda item: (-item.score, item.reading_id))
        best = scored[0]
        second_score = scored[1].score if len(scored) > 1 else 0.0
        margin = round(best.score - second_score, 6)
        if best.score < self.min_score or margin < self.min_margin:
            return None

        selected = profile_by_id[best.reading_id]
        return Resolution(
            word=selected.word,
            pos=selected.pos,
            reading_id=selected.reading_id,
            ipa=selected.ipa,
            sense_ids=selected.sense_ids,
            score=best.score,
            margin=margin,
            evidence_terms=best.matched_terms,
            candidates=tuple(scored),
        )

    def resolve_token(self, text: str, token: Any) -> Resolution | None:
        """Convenience adapter for token objects or mappings with offsets and POS."""

        def get(name: str, default: Any = None) -> Any:
            if isinstance(token, Mapping):
                return token.get(name, default)
            return getattr(token, name, default)

        # Prefer character offsets. For spaCy-like tokens, ``idx`` is the
        # character start while ``start`` is a token index.
        start = get("start_char", get("idx", get("start")))
        end = get("end_char", get("end"))
        lemma = get("lemma") or get("lemma_", None)
        pos = get("pos") or get("pos_", None)
        surface = get("text") or get("orth_", None)
        if not isinstance(start, int):
            return None
        if not isinstance(end, int) and surface:
            end = start + len(str(surface))
        if not isinstance(end, int):
            return None
        return self.resolve(
            text,
            start=start,
            end=end,
            pos=str(pos) if pos else None,
            lemma=str(lemma or surface) if (lemma or surface) else None,
        )
