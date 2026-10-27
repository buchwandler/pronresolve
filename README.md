# pronresolve MVP

`pronresolve` discovers same-spelling, same-part-of-speech pronunciation ambiguity from dictionary data and chooses a reading from sentence context when the evidence is strong enough.

The package is data-driven. It contains **no word-specific heteronym table** and has no runtime dependency on Lexhint, G2Lex, or Lexphon. The build pipeline supplies dictionary-entry objects; the runtime loads a generated JSON ambiguity index.

## Package layout

The Python package lives directly at `pronresolve/`. There is intentionally no `src/` directory.

## Install

```bash
python -m pip install .
```

Versioning is VCS-driven through `setuptools-scm`. When installed from a source archive without Git metadata, the configured fallback version is `0.1.0.dev0`. Release builds should be made from version tags.

For development:

```bash
python -m pip install -e ".[dev]"
pytest
```

## Discover candidate readings from Lexhint entries

The builder accepts Lexhint-style `DictionaryEntry` objects or dictionaries with the same fields. It deliberately accepts an iterable so a caller can stream entries instead of loading the full dictionary into memory.

```python
from pronresolve import discover_ambiguities, save_index

# lexicon.iter_entries() is the proposed Lexhint streaming API described in
# implementation-briefs/01_lexhint_entry_stream.md.
result = discover_ambiguities(
    lexicon.iter_entries(),
    language="en",
    locale="en-US",
)
save_index(result.index, "en-us.pronresolve.json")
print(result.report.as_dict())
```

For a standalone smoke test, the CLI accepts JSONL records with `word`, `pos`, `pronunciations` (or `sounds`), `senses`, and optional `etymology_number` fields:

```bash
pronresolve build \
  --input-jsonl dictionary-entries.jsonl \
  --output en-us.pronresolve.json \
  --language en \
  --locale en-US
pronresolve inspect en-us.pronresolve.json
```

## Runtime resolution

The resolver needs the original sentence and the target token's character offsets. Supply POS and lemma when the frontend has them.

```python
from pronresolve import Resolver

resolver = Resolver.from_path("en-us.pronresolve.json")
decision = resolver.resolve(
    text="The archer picked up the bow and an arrow.",
    start=25,
    end=28,
    pos="NOUN",
    lemma="bow",
)

if decision is not None:
    selector = decision.selector  # e.g. "READING:r1-en-<stable-id>"
    ipa = decision.ipa
    print(selector, ipa, decision.score, decision.evidence_terms)
```

The selector is intended to be passed through an existing selector-aware lexicon lookup. If the resolver returns `None`, keep the current default/POS pronunciation path.

## MVP discovery rules

The discovery step groups entries by normalized spelling and POS.

- One distinct IPA across entries: not ambiguous.
- Multiple distinct IPA values attached to different entries, where each contributing entry has exactly one normalized IPA: resolvable candidate profiles are generated. The profile inherits that entry's sense evidence.
- Multiple distinct IPA values on the same entry: classified as unlinked ambiguity and **not** turned into a context-resolution profile. The source does not tell us which sense belongs to which IPA, so the MVP refuses to guess.
- Missing IPA: ignored for candidate generation and counted in the report.

The MVP does not yet infer morphological lemmas, perform embedding-based similarity, or train a classifier. Context matching uses Unicode tokenization and weighted exact-token overlap across glosses, topics, tags, examples, synonyms, and antonyms. It is deterministic and explainable, not a claim of linguistic certainty.

`locale` is stored as index metadata but the MVP does not apply locale-specific pronunciation filtering itself. Generate separate locale-specific indexes from correctly filtered source data when regional variants must be separated.

## JSON index

Schema version 1 contains:

- `language`, `locale`, and `schema_version`
- `profiles`: one profile per generated reading
- stable reading IDs based on language, normalized word, normalized POS, and IPA
- sense IDs and the Lexhint evidence used for scoring

Index files should be built alongside the pronunciation lexicon and published with matching dataset/version metadata. Do not independently update one without the other.

## Integration boundary

- `lexhint`: add a public streaming `Lexicon.iter_entries()` API (implementation brief 01).
- `g2lex-data`: generate the JSON index and add `READING:<reading_id>` selectors to the corresponding lexicon entries (brief 02).
- G2P frontends: pass token spans, POS, and lemma to the resolver and use the returned selector (briefs 03–06).
- Based on the current interfaces reviewed, G2Lex already supports arbitrary selector names and Lexphon already passes a selector tag to lookup. No functional changes to those packages are expected for this MVP; add compatibility tests where they are consumed.
