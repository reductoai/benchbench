# Reproducing BenchBench

There are two reproduction targets. Recomputing summary tables needs only this repository.
Recomputing parses, verdicts and native scores needs benchmark downloads, provider accounts,
and scorer runtimes. Current public APIs need not return the study's historical outputs.

## Install

From the repository root:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
```

Use Python 3.11 or newer. Install Node 22 and pnpm for real bridge calls. With a Node
distribution that includes Corepack, `corepack enable` enables pnpm. Otherwise install
pnpm following its own instructions. On first use the bridge clones Parse Judge, checks
out the commit in `benchbench/__init__.py`, and runs `pnpm install --frozen-lockfile`.
`PARSEJUDGE_DIR` can point to an existing checkout at that same revision with dependencies
installed. Do not use an arbitrary newer checkout when reproducing the study.

Copy `.env.example` to `.env` and fill your own credentials. Export them with:

```sh
set -a
. ./.env
set +a
```

Parser keys use the vendor variable names in `.env.example`. `OPENAI_API_KEY` is the
primary judge key. `GEMINI_API_KEY` is only needed for the secondary Gemini judge.
`HF_TOKEN` may be needed for gated datasets or higher download limits. Dataset access
and licensing remain the operator's responsibility.

### Image hosting

Provision your own private S3-compatible bucket. Set `BENCHBENCH_S3_BUCKET`,
`BENCHBENCH_S3_ACCESS_KEY_ID`, and `BENCHBENCH_S3_SECRET_ACCESS_KEY`. Set
`BENCHBENCH_S3_ENDPOINT_URL` for a non-AWS endpoint and `BENCHBENCH_S3_REGION` as needed.
The bucket name and credentials must not be committed. Provider fetch support varies;
test a tiny paid sample with the chosen endpoint before scaling.

`benchbench host` validates the bucket. It does not create a bucket or write credentials.
The optional `BENCHBENCH_HOST_ENV` names an env file to load without overriding exported
variables. Images are addressed by hash and served with presigned URLs. Manage access,
retention, lifecycle and deletion yourself. The fake presets bypass hosting and real bridge calls.

## Quick plumbing check

Run this fake example to check the pipeline without paid calls. Its first render may download
public SCORE-Bench inputs from Hugging Face. Later cached runs need no parser or judge network calls.

```sh
R=runs/fake
P="fake_ocr fake_empty fake_fail"
benchbench sample "$R" --benchmark score_bench --n 3 --seed 20261107
benchbench render "$R" --workers 2
benchbench perturb "$R" --conditions tilt_2_4
benchbench parse "$R" --presets $P --conditions clean tilt_2_4 --workers 2
benchbench judge "$R" --presets $P --conditions clean tilt_2_4 --judge fake --repeats 2 --workers 2
benchbench report "$R" --benchmark score_bench --presets $P --conditions clean tilt_2_4 --judge fake --repeats 2
```

`fake_empty` returns an empty successful parse. `fake_fail` fails on a seeded subset;
a tiny sample can contain no such failures. Fake judge scores are not quality measurements.

## Primary run, one benchmark

These commands make paid calls. Start with a tiny sample in a separate run directory.
Use the saved study manifests for an exact page-set replay. Do not mix a pilot and the
study run in one directory. The following shell variables are used in every stage:

```sh
export BENCHBENCH_RUNS="$PWD/runs"
B=score_bench
R="$BENCHBENCH_RUNS/$B"
P="reducto_r1 llamaparse_agentic_plus datalab_accurate extend_performance_agentic_formulas mistral_ocr_4_1 azure_layout_high_res_formulas pulse_ultra_2 cohere_parse_v5"
mkdir -p "$R"
cp "results/samples/$B/pages.jsonl" "$R/pages.jsonl"
cp "results/samples/$B/run.json" "$R/run.json"
```

The manifests pin the sample. Alternatively, draw a new sample with
`benchbench sample "$R" --benchmark "$B" --n 500 --seed 20261107` in an empty directory.
That tests sampling but must be checked against the saved IDs before treating it as a replay.
The catalog records dataset revisions and strata. Run all listed public IDs to cover the
study. The summary covers all 12 benchmarks.

### Render and tilt

```sh
benchbench render "$R" --workers 4
benchbench perturb "$R" --conditions tilt_2_4
benchbench estimate "$R" --presets $P --conditions clean tilt_2_4 --repeats 2
```

The estimate uses stored list prices. It is not a quote or a spending limit.

### Parse

```sh
benchbench host
benchbench parse "$R" --presets $P --conditions clean tilt_2_4 --workers 8
benchbench status "$R"
```

The preset IDs and bridge settings must not change between benchmarks. Datalab's bridge
request enables image extraction and captions. Azure and Extend use formula-enabled
presets. Check recorded request settings and model metadata, not only display names.

### Native scores

Install the benchmark's scorer first using the table below. Then:

```sh
benchbench native "$R" --benchmark "$B" --presets $P --conditions clean tilt_2_4
```

For a configured final-run-style runtime, invoke the same command through
`python scripts/native_env.py benchbench native ...`. This wrapper expands
`scripts/native-env.json`; it does not install dependencies. Its paths are examples
under `BENCHBENCH_RUNS`. Read and adjust them before use. It also selects
`scripts/native_python.sh`, which expects an interpreter at
`$BENCHBENCH_RUNS/native-core/bin/python` and formula tools under `native-tools/`.

### PAIR judge and report

```sh
benchbench judge "$R" --presets $P --conditions clean --judge gpt-6.1-sol --prompt parsejudge --effort medium --repeats 2 --judge-image clean --workers 8
benchbench judge "$R" --presets $P --conditions tilt_2_4 --judge gpt-6.1-sol --prompt parsejudge --effort medium --repeats 1 --judge-image clean --workers 8
benchbench report "$R" --benchmark "$B" --presets $P --conditions clean tilt_2_4 --judge gpt-6.1-sol --prompt parsejudge --effort medium --repeats 2
```

The report averages both clean repeats and uses tilt r0. It writes under the run's
`reports/` directory. Review dropped pages and successful-empty outputs before interpreting
ranks. A top score is not a statistically supported pairwise claim. Historical reports
may include secondary comparison-judge checks that these primary-only commands do not run.

## Native scorer setup

Keep scorers in separate environments. Clone each upstream repository, check out the
revision below, and install that revision's documented dependencies. Do not edit scorer
rules to match output formatting. The adapter is the source of truth for conversion,
runtime paths and pin checks. Revisions below come from the adapters and catalog.
Full dependency resolution has not been validated from a clean machine for every scorer.

| Benchmark ID | Upstream revision | Setup and environment variables |
|---|---|---|
| `dp_bench` | Dataset/scorer `24702c61a2fb13325534be664653bc6e60250d13` | `pip install -e '.[dp_bench]'`; adapter fetches the pinned dataset scorer. See [adapter](../benchbench/adapters/dp_bench.py). |
| `idp_leaderboard` | Harness `2fba329699060034a97428f28f3342a42ad23548`; docext `8a08bbd58fd25216331a2134e48374d1a6ed79bb` | `pip install -e '.[idp]'` for parquet access. Clone [harness](https://github.com/NanoNets/idp-leaderboard-benchmarks) and install its pinned [docext](https://github.com/NanoNets/docext) runtime. Set `IDP_BENCH_DIR`, `IDP_SCORER_PYTHON`. |
| `mdpbench` | MultimodalOCR `6ddb0a570419ce7ccb6913cf1c5ed84930320e7e` | Clone [scorer](https://github.com/Yuliang-Liu/MultimodalOCR), install `MDPBench/requirements.txt`. Set `MDPBENCH_SCORER_DIR`, `MDPBENCH_PYTHON`. Formula tools are required. |
| `ocrflux_bench` | OCRFlux `c1b315aa4c8309f8dc436a5d90fc4977bcf0d865` | `pip install -e '.[ocrflux]'`; adapter clones [scorer](https://github.com/chatdoc-com/OCRFlux). Keep NLTK 3.9.1 for the pinned cross-check. |
| `olmocr_bench` | olmOCR `f7cfe4c22098b154c76b6ec950d1c0a464eecf8d` | Clone [scorer](https://github.com/allenai/olmocr), install its `bench` extra. Set `OLMOCR_DIR`, `OLMOCR_PYTHON`. |
| `omnidocbench` | OmniDocBench `0604d9843f1dfa3a292bd5f253ae83a1ba47cd24` | Clone [scorer](https://github.com/opendatalab/OmniDocBench). Set `OMNIDOCBENCH_DIR`. Adapter defaults to its recorded Docker image; for `OMNIDOCBENCH_RUNNER=native`, install its runtime at `$OMNIDOCBENCH_DIR/.venv`. |
| `omniparsebench` | omni_parse_bench `74629e1597259105ed13ae62aded01ece65b3290` | Clone [scorer](https://github.com/datalab-to/omni_parse_bench), install its dependencies. Set `OPB_SCORER_DIR`, `OPB_PYTHON`. Shared headline covers text and tables, not layout. |
| `parsebench2` | ParseBench `31a9ff1dec96f900869b785d8504d18f5035ebf8` | Use a separate [scorer](https://github.com/run-llama/ParseBench) checkout/environment. Set `PARSEBENCH2_DIR`, `PARSEBENCH2_PYTHON`. Adapter invokes its next scorers. |
| `puredocbench` | PureDocBench `4e9d64d`; evaluator OmniDocBench `f133a71e9e91c3621c7ce8994200a7b394a06eb3` | Clone both [benchmark](https://github.com/zhihengli-casia/PureDocBench) and [evaluator](https://github.com/opendatalab/OmniDocBench) at these revisions. Set `PUREDOCBENCH_SCORER_DIR`, `OMNIDOCBENCH_DIR`, `PUREDOCBENCH_ROOT`; native mode also needs `PUREDOCBENCH_EVAL_PYTHON`. See below. |
| `rd_tablebench` | rd-tablebench `1cae108e6395ddc8389af17385f9769519070558` | Adapter clones the pinned [scorer](https://github.com/reductoai/rd-tablebench); `RD_TABLEBENCH_DIR` overrides its location. Install that revision's scorer dependencies in the invoking environment. |
| `real5_omnidocbench` | Same OmniDocBench revision as `omnidocbench` | Reuses the OmniDocBench adapter and runtime. Dataset pairing is separate from scorer setup. |
| `score_bench` | unstructured-eval-metrics `b148439dd428bb10d7f2bb80c7386ea08cbd7447` | Clone [scorer](https://github.com/Unstructured-IO/unstructured-eval-metrics), install its dependencies in a `.venv` inside the checkout. Set `SCORE_UEM_DIR`. |

Formula evaluation needs TeX, fonts and ImageMagick, not only Python dependencies.
MDPBench documents `xelatex`, xeCJK, Source Han Sans SC, PDF reading in ImageMagick,
a `magick` command and Node. `scripts/native-runtime.json` records the study's tool
versions and formula self-check results; it is a historical record, not a test of your
machine. `scripts/texlive.profile` is a profile for a TeX Live installer, not an installer.
Expand its path placeholders to your chosen tool prefix before using it.

The final runtime used TeX Live 2025 and ImageMagick 7. Its MDPBench environment pinned
scikit-image 0.22.0. Consult `native-runtime.json` for the other recorded packages.
Run identity/ground-truth probes before scoring real parses. A formula render failure
can produce a zero that looks like a parsing error. Inspect scorer logs.

For PureDocBench, `python scripts/prepare_puredoc.py` restores the pinned ground-truth
archive under `BENCHBENCH_RUNS` and checks its hash. Its dataset may require `HF_TOKEN`.
The native-process adapter path is already included in this package. The retained
`scripts/puredoc-native-runtime.patch` records that runtime change; do not apply it to
upstream scorer rules. PureDocBench uses a different OmniDocBench evaluator revision
from the main OmniDocBench adapter. Keep separate checkouts and select the matching
environment per command. A single global `OMNIDOCBENCH_DIR` cannot satisfy both pins.

## Rate limits and retries

Start with low `--workers` values. `BENCHBENCH_PER_PRESET` limits simultaneous parse calls
per vendor; `BENCHBENCH_MAX_BRIDGES` limits live Node bridges across processes. Lower both
on a small machine. The bridge retries transient failures with backoff. Persistent failures
remain visible in `benchbench status`. Inspect errors before increasing concurrency.
Do not delete failed records to hide coverage loss. Reruns preserve earlier attempts.

Each stage is resumable. Use separate run directories when changing presets, inputs or
protocols. Do not mix a sensitivity run into primary tags. Raw requests and responses can
contain document content. Treat run directories and hosting credentials accordingly.

## Final refresh

`scripts/parallel_parse.py` is a concurrent parse driver. It takes a runs root,
`--benchmarks`, `--presets`, `--conditions`, `--parallel` and `--workers`. It does not
sample or render pages. For a fresh study, supply all eight presets. Its default Datalab
preset reflects the refresh, not a complete eight-vendor parse run.

`scripts/judge-commands.txt` records the per-benchmark clean/tilt r0 commands.
`scripts/native-commands.txt` records native commands for Datalab only. The refresh reused
the seven other vendors' parses and native scores. To reproduce primary clean r0+r1,
also run the clean judge command with `--repeats 2`, as above. Do not mistake the r0 command
list for the full repeat protocol. `scripts/judge_cli.py` forwards to the public CLI.

`scripts/compare_results.py --benchmarks ... --output ...` aggregates local clean/tilt
scores. It retains benchmark-specific Datalab native aggregation but omits operational
audits and old-versus-new report prose. It is not a byte-identical generator for the
archived `final-all-vendor-comparison.csv`. It expects the eight parses and judge records
under `BENCHBENCH_RUNS`. Missing primary data is not replaced by a default score.

## Analysis

For the checked-in snapshot, no full run download is needed:

```sh
python analysis/headlines.py
python analysis/make_results_md.py
python analysis/make_results_md.py --check
```

The first command computes the 12-benchmark summary. The second writes `docs/RESULTS.md` from
`results/data.json`.
The check compares bytes. `--results PATH` and `--output PATH` support an isolated copy.
The README's headline table uses the same definitions. No generator edits the README.

The small results files have distinct roles:

| Input | Role |
|---|---|
| `results/data.json` | Primary clean/tilt snapshot, with historical secondary fields and refresh metadata |
| `results/results.csv` | Refreshed PAIR clean/tilt and native clean; historical secondary fields |
| `results/native_under_augment_rerun.csv` | Native tilt inputs used by the snapshot refresh |
| `results/final-all-vendor-comparison.csv` | Archived refresh comparison, with old/new scores and repeat choices |
| `results/appendix/` | Refreshed five-judge comparisons, score/change intervals and Sol repeat checks |
| `results/pair_minimal.csv`, `results/drop_ci.csv` | Refreshed minimal means and primary/minimal PAIR change intervals |

To rebuild intermediate files, work in a copy and set `BENCHBENCH_RESULTS` to that copy
and `BENCHBENCH_RUNS` to full run outputs. Preserve an untouched checked-in snapshot.
With an existing `data.json`, `python analysis/build_data.py` overlays the refreshed PAIR
columns, Datalab native clean/tilt values, and MDPBench native clean means from `results.csv`.
With `BENCHBENCH_RUNS` set, it also recomputes Sol r0/r1 winner agreement on matched clean pages.
`python analysis/grader_appendix.py` rebuilds the refreshed appendix, primary/minimal
PAIR intervals, minimal means and repeat checks from full judge verdicts under
`BENCHBENCH_RUNS`. It also updates `data.json`; then regenerate `docs/RESULTS.md`.
Intervals use 2,000 paired page bootstrap resamples, seed 0, with 90% percentile bounds.
Restore each tag's `final-retry/` snapshots and manifests along with canonical verdicts;
the analysis applies manifested snapshots in timestamp order without changing originals.

The historical `native_under_tilt.py`, `native_under_augment.py`, and
`native_under_damage.py` collectors cover the 11 benchmarks with historical secondary data.
They do not cover `parsebench2`. They need a matching
historical `results.csv`, per-page native scores under `BENCHBENCH_RUNS`, and the
corresponding report summaries under `BENCHBENCH_RESULTS/reports/`. They have no
ParseBench-2 aggregation branch. Do not run them against the complete 12-benchmark CSV.
The damage/augment collectors also need scan and perspective outputs. Adding ParseBench-2
support requires checking aggregation against per-page inputs: its checked-in summary
grid does not include those two conditions. Historical raw archives contain additional
conditions but are not part of the final refresh package. Use the checked-in augmented
rerun table and final snapshot for published
clean/tilt numbers instead.

`native_rerun_overlay.py` additionally needs a directory of per-benchmark rerun CSVs as
its positional argument. `drop_ci.py`, `pair_minimal.py`, and `analysis/checks/` are
historical collectors; use `grader_appendix.py` for refreshed judge checks and intervals.
Figure generators read local `results/`; rendering can need a browser and fonts.

## Data and validation

The data repository is [reducto/benchbench-runs](https://huggingface.co/datasets/reducto/benchbench-runs).
Download it with `hf download reducto/benchbench-runs --repo-type dataset --local-dir benchbench-runs`.
Its top-level benchmark folders contain JSONL shards under `parses/` and `judge/`.
`judge/` also holds the Argon, Astra, Fable, terse and minimal judge checks, with their
`final-retry/` snapshots.
From the download directory, run `python restore_runs.py ./expanded` and set
`BENCHBENCH_RUNS` to the absolute path of `expanded/`. This expands records into the
file-per-page paths the harness reads; it makes no API calls. Set `BENCHBENCH_RESULTS`
to the download's `summary/` for the saved analysis inputs. The results generator also
accepts `--results /path/to/download/summary`.

The final source contains all eight vendors' parses and primary PAIR verdicts. The
archive adds clean/tilt native records for the seven reused presets from historical
benchmark runs. A native row is included only when its historical and final parse content
hashes match. Datalab native records come from the final refresh. `NATIVE_BACKFILL.json`
summarizes the backfill; `NATIVE_PARSE_MATCHES.jsonl` records every page comparison.
The hash covers parser status, Markdown, raw response, harness-error status and image hash.
These are hashes of the original records, not of sanitized text.

From the download directory, run `python validate_native.py` to recompute all 192 primary
native means. `NATIVE_VALIDATION.json` records the results. Ten comparisons remain
inconsistent with the saved values. Legacy inputs were saved to two or three decimals in
`native_rotated_corrected.csv`. Refreshed Datalab values retain more precision.
The checker uses those saved resolutions, not an arbitrary score tolerance. OmniDocBench
headlines use the retained official pooled task components, not means of page scores.

ParseBench-2 has a historical aggregation difference. The seven reused presets' saved
means use the historical 480-page complete-case cohort and arithmetic page means, as in
`analysis/build_data.py`. `parsebench2/native/cohorts.json` preserves that membership.
The refreshed Datalab mean uses subset-weighted dimension means without layout, as in
the current adapter. The checker averages its recorded official dimension means. The
recorded Tables dimension differs from its weighted subset scores in both conditions;
see `NATIVE_COMPONENT_CHECKS.json`. The archive preserves these inconsistencies.

PureDocBench's seven reused presets use official pooled formula/table components.
Refreshed Datalab uses page-averaged task components. Those conventions are not harmonized.
The source has no native row for 41 matched MDPBench parse pages; see
`NATIVE_MISSING_ROWS.jsonl`. No rows were excluded for parse-hash mismatches.

Sanitized HTTP judge exchanges, configuration, blinded mappings and prompt hashes are
recorded. Historical secondary raw runs are not in this package. See its dataset card for
coverage, sanitization and source-data terms. No page images are included.

```sh
ruff check . && ruff format --check . && pytest -q
python analysis/make_results_md.py --check
```

These checks do not execute all native scorers or make paid calls. Review licenses before
downloading or sharing images. Report the repository commit, API date, preset IDs, prompt
hash, scorer revisions, sample IDs, page coverage and any changed runtime dependencies
when publishing a rerun.
