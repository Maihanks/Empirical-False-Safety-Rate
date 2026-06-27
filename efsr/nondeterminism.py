"""Stage 5: a priori exclusion of intrinsically non-deterministic classes.

This is the discipline point flagged in the methodology as "the single
biggest source of false-positive divergences if skipped": a class whose
behaviour depends on random seeds, wall-clock time, hash-ordering,
concurrency, or external I/O can make the differential tester report
DIVERGE purely from non-determinism, inflating EFSR. Screening is a
heuristic source-level scan -- it is deliberately conservative (prefers
false exclusions over missed ones) and is documented as such.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Each pattern maps to a human-readable reason recorded in the exclusion log.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("uses java.util.Random without a fixed seed", re.compile(r"\bnew\s+Random\s*\(\s*\)")),
    ("reads wall-clock time", re.compile(r"\bSystem\.(currentTimeMillis|nanoTime)\s*\(")),
    ("uses java.time.Instant/Clock.now or LocalDate/Time.now", re.compile(r"\b(Instant|Clock|LocalDate|LocalDateTime|LocalTime)\.now\s*\(")),
    ("generates random UUIDs", re.compile(r"\bUUID\.randomUUID\s*\(")),
    ("spawns or joins threads", re.compile(r"\bnew\s+Thread\s*\(|\.start\s*\(\s*\)\s*;|\bThread\.sleep\s*\(")),
    ("uses java.util.concurrent primitives", re.compile(r"\bjava\.util\.concurrent\.|\bExecutorService\b|\bCompletableFuture\b|\bAtomic\w+\b")),
    ("declares synchronized methods/blocks", re.compile(r"\bsynchronized\b")),
    ("performs file I/O", re.compile(r"\bnew\s+File(Reader|Writer|InputStream|OutputStream)\s*\(|\bFiles\.(read|write)")),
    ("performs network I/O", re.compile(r"\bnew\s+Socket\s*\(|\bURL\s*\(|\bHttpClient\b|\bHttpURLConnection\b")),
    ("exposes HashMap/HashSet iteration order", re.compile(r"\bnew\s+(HashMap|HashSet)\s*<")),
    ("reads environment-dependent state", re.compile(r"\bSystem\.getenv\s*\(|\bSystem\.getProperty\s*\(")),
]


@dataclass
class NondeterminismReport:
    is_nondeterministic: bool
    matched_reasons: list[str] = field(default_factory=list)

    def reason_text(self) -> str:
        return "; ".join(self.matched_reasons)


def screen_source(java_source: str) -> NondeterminismReport:
    """Heuristic scan of a single Java source file's text.

    Note on the HashMap/HashSet pattern: iteration order is only an
    observable-behaviour risk if the class exposes that order (e.g. via
    toString, an iterator, or serialisation) to a caller; this screener
    flags the constructor use conservatively and leaves a human reviewer
    (Stage 8) free to override a false positive via `force_include`.
    """
    matched = [reason for reason, pattern in _PATTERNS if pattern.search(java_source)]
    return NondeterminismReport(is_nondeterministic=bool(matched), matched_reasons=matched)


def screen_file(java_file: Path) -> NondeterminismReport:
    return screen_source(Path(java_file).read_text())
