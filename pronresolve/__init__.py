"""Data-driven pronunciation ambiguity discovery and resolution."""

try:
    from ._version import __version__
except ImportError:  # Source checkout before setuptools-scm has generated _version.py.
    __version__ = "0+unknown"

from .discovery import discover_ambiguities, reading_id_for
from .models import (
    AmbiguityIndex,
    Cue,
    CandidateScore,
    DiscoveryReport,
    DiscoveryResult,
    ReadingProfile,
    Resolution,
)
from .resolver import Resolver
from .storage import decode_v1, decode_v2, encode_v2, load_index, save_index

__all__ = [
    "__version__",
    "AmbiguityIndex",
    "CandidateScore",
    "Cue",
    "DiscoveryReport",
    "DiscoveryResult",
    "ReadingProfile",
    "Resolution",
    "Resolver",
    "discover_ambiguities",
    "decode_v1",
    "decode_v2",
    "encode_v2",
    "load_index",
    "reading_id_for",
    "save_index",
]
