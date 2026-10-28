"""Data-driven pronunciation ambiguity discovery and resolution."""

try:
    from ._version import __version__
except ImportError:  # Source checkout before setuptools-scm has generated _version.py.
    __version__ = "0+unknown"

from .discovery import discover_ambiguities, reading_id_for, reading_id_v2
from .equivalence import (
    EquivalenceConfigurationError,
    EquivalencePair,
    EquivalencePartition,
    ExactEquivalence,
    PhonodistEquivalence,
    PronunciationClass,
    PronunciationEquivalence,
    partition_pronunciations,
)
from .models import (
    AmbiguityIndex,
    Cue,
    CandidateScore,
    DiscoveryReport,
    DiscoveryResult,
    ReadingProfile,
    Resolution,
    SemanticAnchor,
    UnresolvedAmbiguity,
    SemanticIdentity,
    INDEX_SCHEMA_VERSION,
    READING_ID_VERSION,
    is_reading_id_v2,
)
from .resolver import Resolver
from .storage import (
    decode_v1,
    decode_v2,
    decode_v3,
    encode_v2,
    encode_v3,
    load_index,
    save_index,
)

__all__ = [
    "__version__",
    "AmbiguityIndex",
    "CandidateScore",
    "Cue",
    "EquivalenceConfigurationError",
    "ExactEquivalence",
    "PhonodistEquivalence",
    "PronunciationEquivalence",
    "DiscoveryReport",
    "DiscoveryResult",
    "ReadingProfile",
    "Resolution",
    "Resolver",
    "discover_ambiguities",
    "decode_v1",
    "decode_v2",
    "decode_v3",
    "encode_v2",
    "encode_v3",
    "load_index",
    "reading_id_for",
    "SemanticAnchor",
    "SemanticIdentity",
    "INDEX_SCHEMA_VERSION",
    "READING_ID_VERSION",
    "is_reading_id_v2",
    "reading_id_v2",
    "EquivalencePair",
    "EquivalencePartition",
    "PronunciationClass",
    "UnresolvedAmbiguity",
    "partition_pronunciations",
    "save_index",
]
