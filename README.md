# Empirical-False-Safety-Rate
Automated refactoring tools driven by large language models (LLMs) are routinely accepted as behaviour-preserving on the basis of an evaluation protocol that requires a transformation to compile, pass the existing test suite, and improve a target quality metric. Because test suites are incomplete, a refactoring can satisfy all three criteria yet still alter program behaviour on inputs the suite does not exercise; the frequency of this outcome is unknown. This article defines the Empirical False Safety Rate (EFSR) as the proportion of refactorings satisfying all three criteria that nonetheless exhibit detectable behavioural divergence under automatic difference-revealing test generation, and presents a reproducible methodology to estimate it. Because behavioural equivalence is undecidable, EFSR is explicitly an empirical lower bound: it counts the divergences that a differential testing mechanism detects, not all that exist. Using benchmark Java systems, the methodology estimates EFSR for several LLM-based refactoring strategies, a rule-based refactoring tool, and a reference set of human refactorings, reporting each rate with a Wilson confidence interval. It further models instance-level divergence against a set of structural metrics using regularised feature selection to identify the most informative predictors. The study evaluates whether compile-and-test screening is an adequate proxy for behavioural preservation and characterises the conditions under which it is not, providing a reusable reliability measure, an evidence base for multi-stage verification in LLM-driven refactoring, and a structural risk indicator for cost-proportional verification. All datasets, generated transformations, and analysis scripts are released for reproduction.

## Repository layout

```
efsr/                     Python package implementing the Stage 0-9 measurement pipeline
  config.py                tool paths, generation budget, seeds, thresholds (env-overridable)
  corpus.py                 Section III-C: Long Method/Large Class smell detection + JaCoCo
                            line-coverage gate -> the corpus of refactoring targets
  generation.py             Section III-D: the five refactoring-producing processes --
                            vendor-agnostic LLM strategies, a JDeodorant wrapper, and a
                            RefactoringMiner-backed human-reference extractor
  selection.py              Section III-D: the retained-output selection rule (lowest
                            post-transformation target metric, ties broken by smallest diff)
  build_runner.py          Stage 1-2: Maven compile + test, Surefire report parsing
  metrics/                 Stage 3 input: structural metrics (ckjm backend + pure-Python fallback)
  protocol.py              Stage 1-4: the three-check protocol and admission to Pi(S)
  nondeterminism.py        Stage 5: a priori exclusion of intrinsically non-deterministic classes
  difftest/                Stage 6-7: EvoSuiteR + Randoop generation, JUnit-suite diff,
                            and a dual-classloader probe (difftest/harness/DualRunner.java)
                            that also proxies interface-typed collaborator fields to capture
                            the Interface/API taxonomy channel
  replay.py, taxonomy.py   Stage 8: replay/confirm + four-category divergence classification
  pipeline.py              Stage 0-9 orchestrator: one already-decided transformation in, one
                            CSV row out (run_pipeline_for_transformation), plus the Section
                            III-D sample-3x/select-1/continue orchestrator for LLM strategies
                            (run_llm_strategy_for_target)
  results.py               Stage 9: the CSV results store (results/csv/transformations.csv)
  stats/                   Section IV/V: EFSR + Wilson CI, between-process comparisons,
                            L1-penalised logistic regression with Wald CIs for structural
                            predictors (RQ3), Section III-I sample-size/power planning, and
                            the Fig. 1 per-project EFSR box plot
scripts/
  build_corpus.py           Section III-C corpus construction CLI
  run_llm_strategy.py       drives one LLM strategy over a corpus (Section III-D), pluggable
                            via --complete-fn so no model SDK is hard-wired into efsr
  build_human_manifest.py   turns RefactoringMiner output into a run_pipeline.py manifest by
                            checking out the pre/post commits as git worktrees
  run_pipeline.py           runs the pipeline over a single-generation-per-target manifest
                            (JSON) -- the JDeodorant and Human paths, which skip selection
  plan_sample_size.py       Section III-I: minimum |Pi(S)| from a pilot divergence rate
  run_pilot_validation.py   sanity check: confirms the oracle distinguishes a known-equivalent
                            pair, a known-divergent pair, and a known-interaction-divergent
                            pair before trusting the full corpus
  aggregate_results.py      builds Table I / Table II (with odds-ratio CIs) / Fig. 1 /
                            taxonomy distribution from the CSV
fixtures/pilot/             known-equivalent, known-divergent, and known-interaction-divergent
                            toy Java pairs for the pilot validation step
tests/                      pytest suite for everything that doesn't require a full JDK/Maven
```

## Quick start

Dependencies and the virtual environment are managed with [uv](https://docs.astral.sh/uv/) (a `uv.lock` is committed for reproducible installs):

```bash
uv sync --all-groups   # creates .venv and installs runtime + dev (pytest) dependencies
uv run pytest tests/ -q
```

Run any script the same way, e.g. `uv run python scripts/run_pilot_validation.py`.
`uv add <package>` / `uv remove <package>` update `pyproject.toml` and `uv.lock` together.

Most of the pipeline's correctness logic (EFSR/Wilson CI, the three-check
protocol, non-determinism screening, taxonomy classification, the JUnit
diff, the predictor model, corpus smell detection, the retained-output
selection rule) is pure Python and covered by the test suite with no
external tools required. Running the pipeline against real Java targets
additionally needs:

- a JDK (`javac`) to compile `efsr/difftest/harness/{DualRunner,JUnitTextRunner}.java`
  via `efsr/difftest/harness/build.sh <junit.jar> <hamcrest.jar>`,
- Maven (Stage 1-2),
- EvoSuite and/or Randoop jars (Stage 6), and
- optionally a ckjm jar (Stage 3, bytecode metrics), a JDeodorant jar
  (the rule-based baseline), and the `RefactoringMiner` binary (the human
  reference set) -- each pointed to via `EFSR_EVOSUITE_JAR` /
  `EFSR_RANDOOP_JAR` / `EFSR_JUNIT_JAR` / `EFSR_CKJM_JAR` /
  `EFSR_JDEODORANT_JAR` / `EFSR_REFACTORINGMINER_BIN` (see `efsr/config.py`
  for the full list). Anything not configured fails loudly and locally
  (an `*Unavailable` exception) rather than silently skipping a stage.

Once the harness jar is built, validate the oracle before trusting any
corpus-scale numbers -- this checks a known-equivalent pair, a
known-divergent pair (Functional category), and a known-interaction-
divergent pair (Interface/API category, via the collaborator-proxying in
`DualRunner.java`):

```bash
uv run python scripts/run_pilot_validation.py
```

A full corpus run is: `build_corpus.py` (Section III-C) ->
`run_llm_strategy.py` per LLM strategy / `build_human_manifest.py` +
`run_pipeline.py` for the Human set / a JDeodorant-produced manifest +
`run_pipeline.py` for the rule-based baseline -> `aggregate_results.py`.
