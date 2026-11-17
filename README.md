# BenchBench
[![Dataset](https://img.shields.io/badge/Hugging_Face-Dataset-yellow)](https://huggingface.co/datasets/reducto/benchbench-runs) [![PAIR](https://img.shields.io/badge/PAIR-Human_evaluation-blue)](https://reducto.ai/blog/pairwise-ai-ranking-parse-evaluation)

Do document-parsing benchmarks measure what they claim? We ran eight parsers on 12 benchmarks, on clean and tilted pages, and scored them with each benchmark's own scorer and the PAIR image judge. Rankings change with the scorer and with small page tilts.

![A 2–4° tilt reshuffles the parser leaderboard](https://cdn.reducto.ai/benchbench/tilt-leaderboard.png)

## Results
| Measure | 12 benchmarks |
|---|---:|
| Native winner changes after tilt | 6/12 |
| PAIR winner changes after tilt | 2/12 |
| Median native relative tilt loss | 2.2% |
| Median PAIR relative tilt loss | 4.0% |
| Native percentage lead smaller than median percentage tilt loss | 9/12 |
| PAIR clean repeat winner agreement | 12/12 |

| Benchmark | Native clean | Native tilt | PAIR clean | PAIR tilt |
|---|---|---|---|---|
| DP-Bench | Cohere | Mistral OCR | Reducto | Reducto |
| SCORE-Bench | Mistral OCR | Mistral OCR | Reducto | Reducto |
| olmOCR-Bench | Datalab | Datalab | Reducto | Reducto |
| OmniParseBench | Datalab | Reducto | Reducto | Reducto |
| OCRFlux-bench | Mistral OCR | Mistral OCR | Reducto | Reducto |
| IDP Leaderboard | LlamaParse | Reducto | LlamaParse | Mistral OCR |
| MDPBench | Datalab | Datalab | LlamaParse | LlamaParse |
| RD-TableBench | LlamaParse | Reducto | Reducto | Reducto |
| PureDocBench | LlamaParse | Reducto | Reducto | Datalab |
| OmniDocBench | Mistral OCR | Mistral OCR | Reducto | Reducto |
| Real5-OmniDocBench | Mistral OCR | Mistral OCR | Reducto | Reducto |
| ParseBench-2 | LlamaParse | Reducto | Reducto | Reducto |
Loss is `100 * (1 - tilt / clean)`; the native percentage lead is `100 * (best - second) / best`. See [full scores and definitions](docs/RESULTS.md).
## How it works
1. **Sample:** draw up to 500 pages per benchmark with seed `20261107`.
2. **Tilt:** add a 2% white margin and rotate each page 2–4 degrees.
3. **Parse:** send the same images to eight fixed vendor presets.
4. **Score:** run each native scorer and PAIR (GPT-6.1 Sol, medium effort, high image detail); PAIR sees all eight blinded outputs and the clean reference image.
5. **Compare:** measure rankings, winner changes and tilt losses; average clean PAIR repeats r0+r1 and use tilt r0.

[Methodology](docs/METHODOLOGY.md) · [Reproduction guide](docs/REPRODUCING.md)
## Parsers and benchmarks
| Parser | Preset | Parser | Preset |
|---|---|---|---|
| Reducto | `reducto_r1` | Mistral OCR | `mistral_ocr_4_1` |
| LlamaParse | `llamaparse_agentic_plus` | Azure Document Intelligence | `azure_layout_high_res_formulas` |
| Datalab | `datalab_accurate` | Pulse | `pulse_ultra_2` |
| Extend | `extend_performance_agentic_formulas` | Cohere | `cohere_parse_v5` |

Datalab accurate uses Chandra 2.7 with image extraction and captions. Settings: [catalog](benchbench/catalog.yaml), [bridge](bridge/parsejudge-bridge.ts).
| Benchmark | Builder | Sampled | Native headline metric | Dataset license | Source |
|---|---|---:|---|---|---|
| DP-Bench | Upstage | 200 | NID | MIT | [dataset](https://huggingface.co/datasets/upstage/dp-bench) |
| SCORE-Bench | Unstructured | 224 | CCT | Annotations CC BY 4.0; source PDFs vary | [scorer](https://github.com/Unstructured-IO/unstructured-eval-metrics) |
| olmOCR-Bench | Allen Institute for AI | 500 | Mean suite pass rate | ODC-BY | [source](https://github.com/allenai/olmocr) |
| OmniParseBench | Datalab | 500 | Text and tables family pass rate | Per-source licenses | [source](https://github.com/datalab-to/omni_parse_bench) |
| OCRFlux-bench | ChatDOC | 500 | Raw Markdown edit similarity | Apache-2.0 | [source](https://github.com/chatdoc-com/OCRFlux) |
| IDP Leaderboard | Nanonets | 300 | IDP Core TABLE GriTS-Con | MIT, dataset cards | [source](https://github.com/NanoNets/idp-leaderboard-benchmarks) |
| MDPBench | HUST and Kingsoft Office | 500 | Present-task page mean | Apache-2.0 | [source](https://github.com/Yuliang-Liu/MultimodalOCR) |
| RD-TableBench | Reducto | 500 | Table similarity | CC BY-NC-ND 4.0 | [source](https://github.com/reductoai/rd-tablebench) |
| PureDocBench | UCAS, CASIA and collaborators | 500 | Text, formula and table overall | CC BY 4.0 | [source](https://github.com/zhihengli-casia/PureDocBench) |
| OmniDocBench | Shanghai AI Laboratory / OpenDataLab | 500 | Text, formula and table overall | Unstated on the pinned HF card; verify upstream | [source](https://github.com/opendatalab/OmniDocBench) |
| Real5-OmniDocBench | Baidu PaddlePaddle and HKUST (Guangzhou) | 500 | OmniDocBench overall | Apache-2.0 | [scorer](https://github.com/opendatalab/OmniDocBench) |
| ParseBench-2 | LlamaIndex | 500 | Page/dimension means, no layout grounding | Apache-2.0 | [source](https://github.com/run-llama/ParseBench) |
## Judge checks
Across 24 benchmark/condition cases, winner agreement with Sol is Argon 15/24, Astra 24/24, Fable 24/24, terse 22/24 and minimal 22/24. [Judge-model and prompt ablations](results/appendix/) include matched-page coverage, failures and confidence intervals.
## Quick start
Install Python 3.11+, Node 22 and pnpm. [Restore run data and configure credentials and image hosting](docs/REPRODUCING.md), then run the primary clean judge:
```sh
python -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
benchbench judge runs/score_bench --presets reducto_r1 llamaparse_agentic_plus datalab_accurate extend_performance_agentic_formulas mistral_ocr_4_1 azure_layout_high_res_formulas pulse_ultra_2 cohere_parse_v5 --conditions clean --judge gpt-6.1-sol --repeats 2 --workers 8
```
## Data
[reducto/benchbench-runs](https://huggingface.co/datasets/reducto/benchbench-runs) contains parse and judge shards, vendor responses, judge HTTP exchanges, manifests and native scores for all eight parsers. `restore_runs.py` expands them to the harness layout; `validate_native.py` rechecks the native means ([notes](docs/REPRODUCING.md#data-and-validation)). Page images are not included; see the dataset card.
## License
Code: [Apache-2.0](LICENSE). Benchmarks retain their own licenses; vendor outputs follow provider and source-data terms. This repository grants no rights to redistribute page images.
## Citation
Reducto, *BenchBench: testing document-parsing benchmarks*, 2026. See [CITATION.cff](CITATION.cff).

Reducto built this study, wrote the judge prompt, built RD-TableBench and is one of the parsers.
