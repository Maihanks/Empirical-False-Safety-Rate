"""Section III-D: the five refactoring-producing processes.

Three LLM strategies (two distinct models under identical instructions,
plus a chain-of-thought prompt variant), one rule-based tool (JDeodorant),
and a human reference set recovered from version history with
RefactoringMiner. This module produces candidate transformations; Stage
1-4 admission (efsr.protocol) and the retained-output selection rule
(efsr.selection) decide what happens to them next.

LLM strategies are intentionally vendor-agnostic: `LLMRefactoringGenerator`
takes a plain `complete_fn: Callable[[str], str]` so this module has no
hard dependency on any particular provider's SDK. Plug in whatever client
the corpus run actually uses (see `build_llm_strategies` for the expected
shape).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from efsr.config import PipelineConfig, DEFAULT_CONFIG
from efsr.corpus import SmellCandidate
from efsr.protocol import RefactoringType

_CODE_BLOCK_RE = re.compile(r"```(?:java)?\s*\n(.*?)```", re.DOTALL)


@dataclass
class GeneratedTransformation:
    process: str
    target: SmellCandidate
    generation_index: int
    modified_source: str
    raw_response: str = ""


def extract_java_code_block(text: str) -> str:
    """Pull the Java source out of an LLM response.

    Prefers the last fenced ```java block (models sometimes "think out
    loud" in an earlier block before the final answer); falls back to the
    raw text if no fence is present, on the assumption the caller asked
    for code-only output.
    """
    matches = _CODE_BLOCK_RE.findall(text)
    if matches:
        return matches[-1].strip()
    return text.strip()


# --- LLM strategies ----------------------------------------------------------

_DEFAULT_INSTRUCTION = (
    "You are refactoring a Java {refactoring_type} smell.\n"
    "Apply the refactoring to {member_description} in the class below.\n"
    "The refactored code MUST compile and MUST preserve behaviour exactly "
    "for every input -- this is a behaviour-preserving refactoring, not a "
    "feature change.\n"
    "Return ONLY the complete refactored Java source file for this "
    "compilation unit, inside a single ```java code block, with no "
    "explanation outside the block.\n\n"
    "```java\n{source}\n```"
)

_COT_INSTRUCTION = (
    "You are refactoring a Java {refactoring_type} smell.\n"
    "Apply the refactoring to {member_description} in the class below.\n"
    "The refactored code MUST compile and MUST preserve behaviour exactly "
    "for every input -- this is a behaviour-preserving refactoring, not a "
    "feature change.\n"
    "First, think step by step about how to decompose the smell safely. "
    "Then give your final answer as ONLY the complete refactored Java "
    "source file for this compilation unit, inside a single ```java code "
    "block, with no explanation after it.\n\n"
    "```java\n{source}\n```"
)


def _member_description(target: SmellCandidate) -> str:
    if target.method_name:
        return f"the method `{target.method_name}`"
    return f"the class `{target.class_name}`"


def build_prompt(target: SmellCandidate, original_source: str, chain_of_thought: bool = False) -> str:
    template = _COT_INSTRUCTION if chain_of_thought else _DEFAULT_INSTRUCTION
    return template.format(
        refactoring_type=target.refactoring_type.value,
        member_description=_member_description(target),
        source=original_source,
    )


@dataclass
class LLMRefactoringGenerator:
    """Wraps a single model behind a pluggable completion function.

    `complete_fn(prompt) -> raw_text` is the only integration point with
    an actual model provider; this class does not import any vendor SDK.
    """
    process_name: str
    complete_fn: Callable[[str], str]
    chain_of_thought: bool = False
    temperature: float = 0.0  # documented intent only; enforcing it is complete_fn's job

    def generate(self, target: SmellCandidate, original_source: str, generation_index: int = 0) -> GeneratedTransformation:
        prompt = build_prompt(target, original_source, self.chain_of_thought)
        raw = self.complete_fn(prompt)
        modified_source = extract_java_code_block(raw)
        return GeneratedTransformation(
            process=self.process_name, target=target, generation_index=generation_index,
            modified_source=modified_source, raw_response=raw,
        )

    def generate_samples(
        self, target: SmellCandidate, original_source: str, n: int = 3,
    ) -> list[GeneratedTransformation]:
        """Sample `n` independent generations (Section III-D: temperature-
        zero decoding, sampled three times; `complete_fn` is called once
        per sample so it can apply whatever seeding/backend it controls).
        """
        return [self.generate(target, original_source, i) for i in range(n)]


def build_llm_strategies(
    model_a_complete_fn: Callable[[str], str],
    model_b_complete_fn: Callable[[str], str],
    config: PipelineConfig = DEFAULT_CONFIG,
) -> dict[str, LLMRefactoringGenerator]:
    """The three LLM strategies of Section III-D: two distinct models under
    identical instructions, plus a chain-of-thought variant of model A.
    """
    return {
        "LLM-A": LLMRefactoringGenerator("LLM-A", model_a_complete_fn, chain_of_thought=False,
                                          temperature=config.llm_temperature),
        "LLM-B": LLMRefactoringGenerator("LLM-B", model_b_complete_fn, chain_of_thought=False,
                                          temperature=config.llm_temperature),
        "LLM-A (chain-of-thought)": LLMRefactoringGenerator(
            "LLM-A (chain-of-thought)", model_a_complete_fn, chain_of_thought=True,
            temperature=config.llm_temperature,
        ),
    }


# --- Rule-based baseline: JDeodorant -----------------------------------------

class JDeodorantUnavailable(RuntimeError):
    pass


@dataclass
class JDeodorantResult:
    returncode: int
    modified_source: Optional[str]
    log: str


class JDeodorantGenerator:
    """Wraps a headless JDeodorant invocation.

    JDeodorant's command-line surface is not as uniformly documented as
    EvoSuite/Randoop's and varies by fork/build; the command below follows
    the common pattern of the other external-tool wrappers in this
    repository (jar + main class + project/class identifiers) and is the
    one piece of this module a real corpus run should double check against
    whatever JDeodorant build is actually installed, adjusting
    `_build_command` if the local build's CLI differs.
    """
    process_name = "Rule-based (JDeodorant)"

    def __init__(self, config: PipelineConfig = DEFAULT_CONFIG):
        self.config = config
        if not (config.jdeodorant_jar and Path(config.jdeodorant_jar).is_file()):
            raise JDeodorantUnavailable(
                "JDeodorant jar not configured/found (set EFSR_JDEODORANT_JAR)."
            )

    def _build_command(self, project_dir: Path, target: SmellCandidate) -> list[str]:
        refactoring_flag = (
            "-extractMethod" if target.refactoring_type == RefactoringType.LONG_METHOD
            else "-extractClass"
        )
        cmd = [
            self.config.java_binary, "-jar", str(self.config.jdeodorant_jar),
            refactoring_flag,
            "-project", str(project_dir),
            "-class", target.class_name,
        ]
        if target.method_name:
            cmd += ["-method", target.method_name]
        return cmd

    def generate(self, project_dir: Path, target: SmellCandidate, target_relative_path: str) -> JDeodorantResult:
        """`project_dir` must be a disposable copy of the project (e.g. via
        `materialize_project_copy` with `modified_source` set to the
        original, unchanged text) -- JDeodorant-style tools refactor a
        project in place, so the modified source is read back from
        `project_dir / target_relative_path` after the tool runs, not
        returned directly on stdout.
        """
        cmd = self._build_command(project_dir, target)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.config.maven_timeout_seconds)
        if proc.returncode != 0:
            return JDeodorantResult(returncode=proc.returncode, modified_source=None,
                                     log=proc.stdout + proc.stderr)
        modified_source = (Path(project_dir) / target_relative_path).read_text()
        return JDeodorantResult(returncode=0, modified_source=modified_source, log=proc.stdout + proc.stderr)


# --- Human reference set: RefactoringMiner -----------------------------------

class RefactoringMinerUnavailable(RuntimeError):
    pass


@dataclass
class MinedRefactoring:
    commit_sha: str
    refactoring_type: str          # RefactoringMiner's own type label, e.g. "Extract Method"
    file_path: str                 # path of the affected file at the post-commit state
    description: str = ""


def run_refactoring_miner(
    repo_path: Path, output_json: Path, config: PipelineConfig = DEFAULT_CONFIG,
) -> Path:
    """Run `RefactoringMiner -a <repo> -json <output>` over a repo's full
    history. Raises RefactoringMinerUnavailable if the binary is missing.
    """
    if not shutil.which(config.refactoringminer_binary):
        raise RefactoringMinerUnavailable(
            f"RefactoringMiner binary not found ({config.refactoringminer_binary}); "
            f"set EFSR_REFACTORINGMINER_BIN to a valid installation."
        )
    cmd = [config.refactoringminer_binary, "-a", str(repo_path), "-json", str(output_json)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=config.maven_timeout_seconds)
    if proc.returncode != 0:
        raise RuntimeError(f"RefactoringMiner failed (rc={proc.returncode}): {proc.stderr}")
    return output_json


_RELEVANT_TYPES = {"Extract Method", "Extract Class"}


def parse_refactoring_miner_output(output_json: Path) -> list[MinedRefactoring]:
    """Extract Extract Method / Extract Class instances from RefactoringMiner's
    JSON report (the `commits[].refactorings[]` schema of RM 2.x).
    """
    data = json.loads(Path(output_json).read_text())
    mined: list[MinedRefactoring] = []
    for commit in data.get("commits", []):
        sha = commit.get("sha1", commit.get("commitId", ""))
        for refactoring in commit.get("refactorings", []):
            rtype = refactoring.get("type", "")
            if rtype not in _RELEVANT_TYPES:
                continue
            locations = refactoring.get("rightSideLocations") or refactoring.get("leftSideLocations") or []
            file_path = locations[0].get("filePath", "") if locations else ""
            mined.append(MinedRefactoring(
                commit_sha=sha, refactoring_type=rtype, file_path=file_path,
                description=refactoring.get("description", ""),
            ))
    return mined


def extract_before_after_source(repo_path: Path, commit_sha: str, file_path: str) -> tuple[str, str]:
    """Recover the pre- and post-commit content of `file_path` via `git show`.

    Used to materialise the (P, P') pair for a mined human refactoring so
    it can flow through the same Stage 1-9 pipeline as LLM/JDeodorant
    output, with `process="Human"`.
    """
    def _show(rev: str) -> str:
        proc = subprocess.run(
            ["git", "show", f"{rev}:{file_path}"], cwd=repo_path,
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"git show {rev}:{file_path} failed: {proc.stderr}")
        return proc.stdout

    before = _show(f"{commit_sha}^")
    after = _show(commit_sha)
    return before, after


# --- Shared materialisation utility ------------------------------------------

def materialize_project_copy(
    original_project_dir: Path, target_relative_path: str, modified_source: str, work_dir: Path,
) -> Path:
    """Copy `original_project_dir` into a fresh directory under `work_dir`
    and overwrite `target_relative_path` with `modified_source`.

    Every generator above produces only a modified *source file*; running
    the three-check protocol (efsr.protocol) needs a full project tree to
    compile and test against, so this is the one shared step that turns a
    generation into something `TransformationSpec.modified_project_dir`
    can point at.
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    destination = work_dir / f"candidate-{uuid.uuid4().hex[:10]}"
    shutil.copytree(original_project_dir, destination)
    (destination / target_relative_path).write_text(modified_source)
    return destination
