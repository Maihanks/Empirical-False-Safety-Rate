import json
import subprocess
from pathlib import Path

import pytest

from efsr.corpus import SmellCandidate
from efsr.generation import (
    JDeodorantGenerator,
    JDeodorantUnavailable,
    LLMRefactoringGenerator,
    RefactoringMinerUnavailable,
    build_llm_strategies,
    build_prompt,
    extract_before_after_source,
    extract_java_code_block,
    materialize_project_copy,
    parse_refactoring_miner_output,
    run_refactoring_miner,
)
from efsr.protocol import RefactoringType


def _target(method_name="longMethod", refactoring_type=RefactoringType.LONG_METHOD):
    return SmellCandidate(
        source_file=Path("Foo.java"), class_name="org.example.Foo",
        refactoring_type=refactoring_type, method_name=method_name, cc=12.0, loc=60.0,
    )


# ---- code-block extraction --------------------------------------------------

def test_extract_java_code_block_pulls_fenced_block():
    text = "Here is the refactored code:\n```java\nclass A {}\n```\nDone."
    assert extract_java_code_block(text) == "class A {}"


def test_extract_java_code_block_takes_last_block_when_multiple():
    text = "```java\nclass Draft {}\n```\nActually:\n```java\nclass Final {}\n```"
    assert extract_java_code_block(text) == "class Final {}"


def test_extract_java_code_block_falls_back_to_raw_text_without_fence():
    text = "class A {}"
    assert extract_java_code_block(text) == "class A {}"


# ---- prompt construction -----------------------------------------------------

def test_build_prompt_mentions_method_and_refactoring_type():
    prompt = build_prompt(_target(), "class Foo { void longMethod() {} }")
    assert "Long Method" in prompt or "LongMethod" in prompt
    assert "longMethod" in prompt
    assert "```java" in prompt


def test_build_prompt_chain_of_thought_asks_for_step_by_step_reasoning():
    prompt = build_prompt(_target(), "class Foo {}", chain_of_thought=True)
    assert "step by step" in prompt


def test_build_prompt_class_level_mentions_class_not_method():
    target = _target(method_name=None, refactoring_type=RefactoringType.LARGE_CLASS)
    prompt = build_prompt(target, "class Foo {}")
    assert "org.example.Foo" in prompt


# ---- LLMRefactoringGenerator --------------------------------------------------

def test_llm_generator_round_trips_through_a_fake_completion_fn():
    calls = []

    def fake_complete(prompt: str) -> str:
        calls.append(prompt)
        return "```java\nclass Foo { void m() {} }\n```"

    generator = LLMRefactoringGenerator(process_name="LLM-A", complete_fn=fake_complete)
    result = generator.generate(_target(), "class Foo { void longMethod() {} }")

    assert result.process == "LLM-A"
    assert result.modified_source == "class Foo { void m() {} }"
    assert len(calls) == 1


def test_llm_generator_generate_samples_calls_n_times():
    counter = {"n": 0}

    def fake_complete(prompt: str) -> str:
        counter["n"] += 1
        return f"```java\nclass Foo {{ int v = {counter['n']}; }}\n```"

    generator = LLMRefactoringGenerator(process_name="LLM-A", complete_fn=fake_complete)
    samples = generator.generate_samples(_target(), "class Foo {}", n=3)

    assert len(samples) == 3
    assert [s.generation_index for s in samples] == [0, 1, 2]
    assert counter["n"] == 3


def test_build_llm_strategies_returns_three_named_processes():
    strategies = build_llm_strategies(lambda p: "```java\nA\n```", lambda p: "```java\nB\n```")
    assert set(strategies) == {"LLM-A", "LLM-B", "LLM-A (chain-of-thought)"}
    assert strategies["LLM-A (chain-of-thought)"].chain_of_thought is True
    assert strategies["LLM-A"].chain_of_thought is False


# ---- JDeodorantGenerator -------------------------------------------------------

def test_jdeodorant_generator_raises_when_jar_not_configured():
    from efsr.config import PipelineConfig

    with pytest.raises(JDeodorantUnavailable):
        JDeodorantGenerator(PipelineConfig(jdeodorant_jar=None))


def test_jdeodorant_generator_reads_back_modified_source_on_success(tmp_path, monkeypatch):
    from efsr.config import PipelineConfig

    jar = tmp_path / "jdeodorant.jar"
    jar.write_text("fake")
    config = PipelineConfig(jdeodorant_jar=jar)
    generator = JDeodorantGenerator(config)

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "Foo.java").write_text("class Foo { /* refactored in place */ }")

    monkeypatch.setattr(
        "efsr.generation.subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
    )

    result = generator.generate(project_dir, _target(), "Foo.java")
    assert result.returncode == 0
    assert "refactored in place" in result.modified_source


def test_jdeodorant_generator_reports_failure_without_reading_file(tmp_path, monkeypatch):
    from efsr.config import PipelineConfig

    jar = tmp_path / "jdeodorant.jar"
    jar.write_text("fake")
    config = PipelineConfig(jdeodorant_jar=jar)
    generator = JDeodorantGenerator(config)

    monkeypatch.setattr(
        "efsr.generation.subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom"),
    )

    result = generator.generate(tmp_path, _target(), "Foo.java")
    assert result.returncode == 1
    assert result.modified_source is None
    assert "boom" in result.log


# ---- RefactoringMiner --------------------------------------------------------

def test_run_refactoring_miner_raises_when_binary_missing():
    from efsr.config import PipelineConfig

    config = PipelineConfig()
    config.refactoringminer_binary = "definitely-not-a-real-binary-xyz"
    with pytest.raises(RefactoringMinerUnavailable):
        run_refactoring_miner(Path("."), Path("out.json"), config)


def test_parse_refactoring_miner_output_filters_to_extract_method_and_class(tmp_path):
    payload = {
        "commits": [
            {
                "sha1": "abc123",
                "refactorings": [
                    {"type": "Extract Method", "description": "Extract Method foo()",
                     "rightSideLocations": [{"filePath": "src/Foo.java"}]},
                    {"type": "Rename Variable", "description": "irrelevant",
                     "rightSideLocations": [{"filePath": "src/Bar.java"}]},
                    {"type": "Extract Class", "description": "Extract Class Helper",
                     "leftSideLocations": [{"filePath": "src/Baz.java"}]},
                ],
            }
        ]
    }
    out = tmp_path / "rm.json"
    out.write_text(json.dumps(payload))

    mined = parse_refactoring_miner_output(out)
    types = {m.refactoring_type for m in mined}
    assert types == {"Extract Method", "Extract Class"}
    assert all(m.commit_sha == "abc123" for m in mined)


def test_extract_before_after_source_uses_git_show(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "a@b.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)

    (repo / "Foo.java").write_text("class Foo { /* v1 */ }")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v1"], cwd=repo, check=True)

    (repo / "Foo.java").write_text("class Foo { /* v2 */ }")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v2"], cwd=repo, check=True)

    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()

    before, after = extract_before_after_source(repo, sha, "Foo.java")
    assert "v1" in before
    assert "v2" in after


# ---- materialize_project_copy -------------------------------------------------

def test_materialize_project_copy_overwrites_target_file(tmp_path):
    original = tmp_path / "original"
    (original / "src").mkdir(parents=True)
    (original / "src" / "Foo.java").write_text("class Foo { /* old */ }")
    (original / "pom.xml").write_text("<project/>")

    work_dir = tmp_path / "work"
    copy_dir = materialize_project_copy(original, "src/Foo.java", "class Foo { /* new */ }", work_dir)

    assert (copy_dir / "pom.xml").read_text() == "<project/>"
    assert "new" in (copy_dir / "src" / "Foo.java").read_text()
    assert "old" in (original / "src" / "Foo.java").read_text()  # original untouched


def test_materialize_project_copy_produces_distinct_dirs_per_call(tmp_path):
    original = tmp_path / "original"
    original.mkdir()
    (original / "Foo.java").write_text("class Foo {}")
    work_dir = tmp_path / "work"

    first = materialize_project_copy(original, "Foo.java", "class Foo { /* a */ }", work_dir)
    second = materialize_project_copy(original, "Foo.java", "class Foo { /* b */ }", work_dir)

    assert first != second
    assert "a" in (first / "Foo.java").read_text()
    assert "b" in (second / "Foo.java").read_text()
