# Methodology

## Question and scope

BenchBench tests whether document-parsing benchmarks give stable, interpretable comparisons.
The design compares native scoring, image-based
PAIR scoring, and sensitivity to small page tilts on the same sampled pages.

The study covers 12 benchmarks and 96 parser-benchmark pairs. The two
tier-3 private-data entries in the catalog are metadata, not evaluated benchmarks.

## Sampling and inputs

The study seed is `20261107`. Each public benchmark contributes up to 500 pages. Smaller
sets are used in full. Catalog strata control proportional sampling with seeded draws;
see `benchbench/datasets.py`. ParseBench-2 uses the new-case file list in
`benchbench/parsebench2_new.txt`. Real5 is sampled by original page, with captures paired
to that original. The synthetic tilt comparison uses the original-page baseline.

The authoritative sampled IDs and run configuration are in
`results/samples/<benchmark>/pages.jsonl` and `run.json`. Do not substitute a fresh random
sample when checking the published scores. These manifests also record dataset revisions.

PDFs are rendered at 200 DPI with PDFium. Existing benchmark images are converted to PNG.
Each parser gets the same canonical page image for a condition. The judge gets the clean
reference image, even when it evaluates a parse made from a tilted page. Input hashes and
perturbation parameters are recorded in the run. The harness supports private,
user-provisioned S3-compatible hosting with presigned URLs for providers that fetch images.

## Presets and refresh

The eight preset IDs are listed in the README. They are held fixed across benchmarks.
The pinned Parse Judge presets supply provider settings. `bridge/parsejudge-bridge.ts`
adds the Extend and Azure formula-enabled presets and forces image extraction and captions
on for Datalab accurate mode. Public API requests, response metadata and preset settings
are retained in full runs. Provider-side model weights are not pinned by this repository.

The final refresh reran Datalab accurate on clean and tilt pages. Datalab described that
API as Chandra 2.7; the API response does not identify a model version. Other vendors'
parses were reused. All eight outputs were rejudged together. Primary PAIR uses clean
r0+r1 averaged and tilt r0. `results/final-all-vendor-comparison.csv` records old and new
scores, coverage and repeat choices. `results/data.json` records refresh scope.

Argon, Astra, Fable, terse and minimal judge checks use these refreshed parser outputs.
Each is compared with Sol on matched complete pages: clean r0+r1 averaged per page,
tilt r0. Scan, perspective and Gemini 3.1 results predate the refresh.

The appendix reports 90% percentile bootstrap intervals from 2,000 page resamples
with seed 0. Clean/tilt changes pair the same pages and resample both conditions
together; change is `100 * (tilt / clean - 1)`. Sol repeat checks compare r0 and r1
winners on their complete clean-page intersection. `results/drop_ci.csv` contains
refreshed primary and minimal PAIR intervals; native intervals are not included.

## Perturbations

Primary `tilt_2_4` adds a 2% white margin and rotates
by a uniform angle from 2 to 4 degrees, with a seeded random sign. Rotation uses bicubic
resampling, an expanded canvas and white fill. Seeds derive from study seed, benchmark,
page and condition. See `benchbench/augment.py` and `benchbench/seeding.py`.

Secondary scan adds mild skew, blur, gray paper and luminance noise. Perspective applies
a seeded projective transform. Their exact parameters are defined in the same module.
Real5 also supports paired real-capture conditions. These are not the primary synthetic
tilt comparison. ParseBench-2 has clean/tilt results, not the full historical secondary
condition grid. Do not fill missing cells with zero.

## Native scorers

Each adapter records its scorer revision, input conversion and headline aggregation.
Read `benchbench/adapters/<benchmark>.py` before interpreting a native score. All native
headlines in `data.json` are expressed on a 0-100 scale, but measure different things:

- DP-Bench uses NID. It excludes figure-marked elements; Markdown-to-element conversion
  cannot recover bounding boxes. Plain figure descriptions can still count as text.
- IDP Leaderboard covers the IDP Core TABLE portion, not the entire leaderboard. Pipe
  tables are converted to HTML. Its adapter reports upstream-dropped predictions as zero
  to retain paired pages. Only the first table is scored by the upstream table path.
- OmniParseBench pools text and table test-family rates. Layout is not in the shared
  headline. A mean of page-level means is not the same aggregation.
- olmOCR-Bench averages suite pass rates. OCRFlux uses raw Markdown edit similarity.
- ParseBench-2's refreshed Datalab result averages present dimensions without layout
  grounding. The seven reused presets retain historical arithmetic page means on a
  480-page complete-case cohort. See [aggregation details](REPRODUCING.md#data-and-validation).
  These conventions are not harmonized. Markdown parses do not supply element boxes.
- MDPBench uses the mean of present text, formula and table tasks per page. OmniDocBench,
  Real5 and PureDocBench use their recorded text/formula/table overall aggregations.
  PureDocBench's historical presets use pooled formula/table components. Refreshed Datalab
  uses page-averaged task components. Those conventions are not harmonized either.
- SCORE-Bench uses CCT. RD-TableBench uses its table similarity scorer.

The adapter docstrings and saved per-run reports provide the evidence for these statements.
Benchmark-specific missing-prediction rules differ. Native scores therefore need their own
coverage counts; the PAIR complete-case rule below must not be assumed for every native mean.

## PAIR judge

Parse Judge is pinned to `76f65c45c13dd7bf0b0af8bae2cea5ffd93c9cc0` in
`benchbench/__init__.py`. Primary PAIR uses GPT-6.1 Sol, medium effort, OpenAI image detail
`high`, and the compare-v4 error-list and 1-10 score format. All eight parses appear in
one request. Vendor names are replaced by seeded anonymous labels. Visible markup may
still reveal a provider. Label order changes by page, condition and repeat.

The study uses `compare-v4-png`: `benchbench/bridge.py` removes the PDF hyperlink clause
because the judge sees a PNG, not a PDF link layer. The bridge otherwise reuses the pinned
judge and records the prompt hash. `--prompt parsejudge-upstream` retains the original
clause for a separate sensitivity run. Missing figure descriptions are penalised.

Clean primary scores average r0 and r1. Tilt uses r0 against the clean image. Pages with
any failed parser are dropped from primary PAIR comparisons. Empty but successful parses
remain. Tilt deltas use complete pages shared with clean. The report gives dropped-page
counts. Different page coverage can change a benchmark mean.

PAIR has been checked against human raters in a separate
[human evaluation](https://reducto.ai/blog/pairwise-ai-ranking-parse-evaluation).

## Statistics and headline definitions

Native-vs-PAIR agreement uses per-page mean rankings.

`benchbench/stats.py` resamples pages, not individual parses, with paired bootstrap draws.
Its default is 2,000 resamples. Mean-score and delta intervals are 90%; pairwise difference
and rank intervals are 95%. Pairwise tests use Holm correction within a condition. The
report's stronger cross-judge claim rule additionally requires complete comparison-judge
coverage and agreement in direction.

`analysis/headlines.py` and `analysis/make_results_md.py` compute descriptive summaries
from `results/data.json` without rounding values before comparison:

- Winner changes compare the full set of top-scoring vendors on clean and tilt.
- Ranks use competition ranking. Tied means share rank; later ranks skip positions.
- Relative loss is `100 * (1 - tilt / clean)`. Its median pools benchmark-preset cells,
  so each benchmark contributes equally. Negative values are gains.
- The native percentage lead is `100 * (best - second) / best`, using clean scores.
  Compare it with the median parser's percentage tilt loss within that benchmark.
  This gives 9/12. The raw-score-point variant gives 8/12 and is shown separately in RESULTS.md.
- Repeat winner agreement compares refreshed Sol r0 and r1 winners on matched complete
  clean pages. Coverage and winners are saved in `results/data.json` under `refresh.repeat_check`.

The saved values retain their source precision. Not every historical native value has
per-page precision in the small summary files. Raw run data is needed to recompute page
means, intervals or precision beyond those saved values. PAIR's 1-10 scale has a different
origin from native 0-100 scores. Relative-loss comparisons are descriptive, not calibrated
cross-metric measurements.

## Limitations

Reducto sells a parser, wrote the judge prompt and built RD-TableBench. LlamaIndex and
Datalab also sell parsers and built included benchmarks. The judge can miss errors or
prefer particular output styles. API models can change. One preset is not every possible
vendor configuration. Image-only inputs do not test PDF link layers or document-level
context. Finite samples, scorer conventions and coverage affect ranks. Benchmark overlap
and public availability do not establish whether a vendor trained on a page.
