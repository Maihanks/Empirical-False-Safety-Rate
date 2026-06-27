# Empirical-False-Safety-Rate
Automated refactoring tools driven by large language models (LLMs) are routinely accepted as behaviour-preserving on the basis of an evaluation protocol that requires a transformation to compile, pass the existing test suite, and improve a target quality metric. Because test suites are incomplete, a refactoring can satisfy all three criteria yet still alter program behaviour on inputs the suite does not exercise; the frequency of this outcome is unknown. This article defines the Empirical False Safety Rate (EFSR) as the proportion of refactorings satisfying all three criteria that nonetheless exhibit detectable behavioural divergence under automatic difference-revealing test generation, and presents a reproducible methodology to estimate it. Because behavioural equivalence is undecidable, EFSR is explicitly an empirical lower bound: it counts the divergences that a differential testing mechanism detects, not all that exist. Using benchmark Java systems, the methodology estimates EFSR for several LLM-based refactoring strategies, a rule-based refactoring tool, and a reference set of human refactorings, reporting each rate with a Wilson confidence interval. It further models instance-level divergence against a set of structural metrics using regularised feature selection to identify the most informative predictors. The study evaluates whether compile-and-test screening is an adequate proxy for behavioural preservation and characterises the conditions under which it is not, providing a reusable reliability measure, an evidence base for multi-stage verification in LLM-driven refactoring, and a structural risk indicator for cost-proportional verification. All datasets, generated transformations, and analysis scripts are released for reproduction.

## Repository layout

```
efsr/                     Python package implementing the Stage 0-9 measurement pipeline
  config.py                tool paths, generation budget, seeds, thresholds (env-overridable)
  build_runner.py          Stage 1-2: Maven compile + test, Surefire report parsing
  metrics/                 Stage 3 input: structural metrics (ckjm backend + pure-Python fallback)
  protocol.py              Stage 1-4: the three-check protocol and admission to Pi(S)
  nondeterminism.py        Stage 5: a priori exclusion of intrinsically non-deterministic classes
  difftest/                Stage 6-7: EvoSuiteR + Randoop generation, JUnit-suite diff,
                            and a dual-classloader probe (difftest/harness/DualRunner.java)
  replay.py, taxonomy.py   Stage 8: replay/confirm + four-category divergence classification
  pipeline.py              Stage 0-9 orchestrator (one transformation in, one CSV row out)
  results.py               Stage 9: the CSV results store (results/csv/transformations.csv)
  stats/                   Section IV/V: EFSR + Wilson CI, between-process comparisons,
                            L1-penalised logistic regression for structural predictors (RQ3)
scripts/
  run_pipeline.py           runs the pipeline over a corpus manifest (JSON)
  run_pilot_validation.py   sanity check: confirms the oracle distinguishes a known-equivalent
                             pair from a known-divergent pair before trusting the full corpus
  aggregate_results.py      builds Table I / Table II / taxonomy distribution from the CSV
fixtures/pilot/             known-equivalent and known-divergent toy Java pairs for the pilot
tests/                      pytest suite for everything that doesn't require a full JDK/Maven
```

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/pytest tests/ -q
```

Most of the pipeline's correctness logic (EFSR/Wilson CI, the three-check
protocol, non-determinism screening, taxonomy classification, the JUnit
diff, the predictor model) is pure Python and covered by the test suite
with no external tools required. Running the pipeline against real Java
targets additionally needs:

- a JDK (`javac`) to compile `efsr/difftest/harness/{DualRunner,JUnitTextRunner}.java`
  via `efsr/difftest/harness/build.sh <junit.jar> <hamcrest.jar>`,
- Maven (Stage 1-2), and
- EvoSuite and/or Randoop jars (Stage 6), pointed to via the `EFSR_EVOSUITE_JAR`
  / `EFSR_RANDOOP_JAR` / `EFSR_JUNIT_JAR` / `EFSR_CKJM_JAR` environment variables
  (see `efsr/config.py` for the full list).

Once the harness jar is built, validate the oracle before trusting any
corpus-scale numbers:

```bash
python scripts/run_pilot_validation.py
```
