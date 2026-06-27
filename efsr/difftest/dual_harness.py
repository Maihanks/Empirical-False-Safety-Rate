"""Stage 7 (channel-detail path): Python wrapper around DualRunner.java.

Invokes the compiled `dualrunner.jar` once per (target, method, args) probe
and parses its one-JSON-object-per-line stdout into `ChannelDiff` records,
one per repetition -- ready for the Stage 8 replay/confirm loop.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from efsr.config import PipelineConfig, DEFAULT_CONFIG


class DualRunnerUnavailable(RuntimeError):
    pass


@dataclass
class ChannelDiff:
    rep: int
    return_differs: bool
    exception_differs: bool
    state_differs: bool
    return_orig: str | None
    return_mod: str | None
    exc_orig: str | None
    exc_mod: str | None
    state_orig: str | None
    state_mod: str | None

    @property
    def any_differs(self) -> bool:
        return self.return_differs or self.exception_differs or self.state_differs

    @property
    def differing_channels(self) -> list[str]:
        channels = []
        if self.return_differs:
            channels.append("return_value")
        if self.exception_differs:
            channels.append("exception")
        if self.state_differs:
            channels.append("state")
        return channels


def run_dual_probe(
    original_classpath: str,
    modified_classpath: str,
    class_name: str,
    method_name: str,
    arg_spec: str,
    repetitions: int,
    config: PipelineConfig = DEFAULT_CONFIG,
) -> list[ChannelDiff]:
    """Stage 7 + part of Stage 8: run the same call against P and P', N times.

    `arg_spec` is the DualRunner argument encoding, e.g. "I:5,S:hello" or
    "-" for a no-argument method.
    """
    if not Path(config.dualrunner_jar).is_file():
        raise DualRunnerUnavailable(
            f"dualrunner.jar not found at {config.dualrunner_jar}. "
            f"Build it with efsr/difftest/harness/build.sh first."
        )
    cmd = [
        config.java_binary, "-cp", str(config.dualrunner_jar), "DualRunner",
        original_classpath, modified_classpath, class_name, method_name, arg_spec,
        str(repetitions),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=config.dualrunner_timeout_seconds
    )
    if proc.returncode != 0:
        raise RuntimeError(f"DualRunner failed (rc={proc.returncode}): {proc.stderr}")

    diffs = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        diffs.append(
            ChannelDiff(
                rep=obj["rep"],
                return_differs=obj.get("return_orig") != obj.get("return_mod"),
                exception_differs=obj.get("exc_orig") != obj.get("exc_mod"),
                state_differs=obj.get("state_orig") != obj.get("state_mod"),
                return_orig=obj.get("return_orig"),
                return_mod=obj.get("return_mod"),
                exc_orig=obj.get("exc_orig"),
                exc_mod=obj.get("exc_mod"),
                state_orig=obj.get("state_orig"),
                state_mod=obj.get("state_mod"),
            )
        )
    return diffs
