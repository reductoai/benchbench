| preset | native (rank) | clean judge (rank) | tilt_2_4 judge (rank) | scan judge (rank) | perspective judge (rank) |
|---|---|---|---|---|---|
| reducto_r1 | 84.4 (2) | 9.68 (1) | 9.67 (1) Δ -0.01 [-0.05, +0.03] | 9.62 (1) Δ -0.06 [-0.10, -0.02] | 9.66 (1) Δ -0.01 [-0.05, +0.02] |
| llamaparse_agentic_plus | 80.5 (5) | 9.05 (6) | 8.44 (6) Δ -0.61 [-0.73, -0.49] | 8.95 (6) Δ -0.10 [-0.17, -0.04] | 9.04 (5) Δ -0.01 [-0.07, +0.04] |
| datalab_accurate | 59.2 (8) | 9.38 (3) | 9.26 (3) Δ -0.12 [-0.19, -0.07] | 9.35 (2) Δ -0.04 [-0.09, +0.01] | 9.34 (2) Δ -0.04 [-0.09, +0.01] |
| extend_performance_agentic_formulas | 74.6 (7) | 9.11 (5) | 8.74 (4) Δ -0.38 [-0.45, -0.31] | 8.95 (5) Δ -0.16 [-0.22, -0.10] | 9.02 (6) Δ -0.09 [-0.15, -0.03] |
| mistral_ocr_4_1 | 89.4 (1) | 9.33 (4) | 9.36 (2) Δ +0.03 [-0.01, +0.08] | 9.34 (3) Δ +0.01 [-0.04, +0.06] | 9.32 (4) Δ -0.01 [-0.06, +0.04] |
| azure_layout_high_res_formulas | 79.4 (6) | 7.85 (7) | 7.90 (7) Δ +0.05 [-0.04, +0.14] | 7.93 (7) Δ +0.08 [+0.00, +0.16] | 7.97 (7) Δ +0.12 [+0.03, +0.21] |
| pulse_ultra_2 | 81.3 (4) | 9.41 (2) | 8.56 (5) Δ -0.85 [-0.98, -0.72] | 9.23 (4) Δ -0.18 [-0.25, -0.11] | 9.34 (3) Δ -0.07 [-0.13, -0.01] |
| cohere_parse_v5 | 83.3 (3) | 7.39 (8) | 6.08 (8) Δ -1.31 [-1.45, -1.19] | 7.12 (8) Δ -0.28 [-0.36, -0.19] | 7.26 (8) Δ -0.14 [-0.20, -0.06] |
| condition | pages | dropped (failed parse) | failed parses by preset |
|---|---|---|---|
| clean | 500 | 0 | none |
| tilt_2_4 | 500 | 0 | none |
| scan | 500 | 0 | none |
| perspective | 500 | 0 | none |
| preset | provider settings sent | list price per page (USD) |
|---|---|---|
| reducto_r1 | `model: r-1`, `merge_tables: false` | 0.010 |
| llamaparse_agentic_plus | `tier: agentic_plus`, cache disabled | 0.05625 |
| datalab_accurate | `mode: accurate`, `output_format: markdown`, page header/footer kept | 0.010 |
| extend_performance_agentic_formulas | `parse_performance`, markdown, figures + advanced charts, formulas on | 0.030 |
| mistral_ocr_4_1 | `mistral-ocr-4-1`, `table_format: html` | 0.004 |
| azure_layout_high_res_formulas | `prebuilt-layout`, `ocrHighResolution` + `formulas` | 0.022 |
| pulse_ultra_2 | `pulse-ultra-2`, figure descriptions on | 0.015 |
| cohere_parse_v5 | `parse-v5.0`, markdown | 0.0015 |
| vendor | GPT clean (r0+r1) | GPT tilt_2_4 | GPT scan | GPT perspective |
|---|---|---|---|---|
| Reducto | 9.68 | 9.67 (Δ -0.01 [-0.06, +0.04]) | 9.62 (Δ -0.06 [-0.10, -0.01]) | 9.66 (Δ -0.01 [-0.06, +0.03]) |
| LlamaParse | 9.05 | 8.44 (Δ -0.61 [-0.75, -0.48]) | 8.95 (Δ -0.10 [-0.18, -0.03]) | 9.04 (Δ -0.01 [-0.08, +0.05]) |
| Datalab | 9.38 | 9.26 (Δ -0.12 [-0.20, -0.05]) | 9.35 (Δ -0.04 [-0.09, +0.02]) | 9.34 (Δ -0.04 [-0.10, +0.02]) |
| Extend | 9.11 | 8.74 (Δ -0.38 [-0.46, -0.29]) | 8.95 (Δ -0.16 [-0.24, -0.08]) | 9.02 (Δ -0.09 [-0.16, -0.02]) |
| Mistral | 9.33 | 9.36 (Δ +0.03 [-0.03, +0.09]) | 9.34 (Δ +0.01 [-0.05, +0.07]) | 9.32 (Δ -0.01 [-0.07, +0.05]) |
| Azure | 7.85 | 7.90 (Δ +0.05 [-0.06, +0.15]) | 7.93 (Δ +0.08 [-0.02, +0.17]) | 7.97 (Δ +0.12 [+0.02, +0.22]) |
| Pulse | 9.41 | 8.56 (Δ -0.85 [-1.01, -0.70]) | 9.23 (Δ -0.18 [-0.26, -0.10]) | 9.34 (Δ -0.07 [-0.14, -0.00]) |
| Cohere | 7.39 | 6.08 (Δ -1.31 [-1.47, -1.16]) | 7.12 (Δ -0.28 [-0.38, -0.18]) | 7.26 (Δ -0.14 [-0.22, -0.05]) |
| vendor | GPT clean | rank 95% range |
|---|---|---|
| Reducto | 9.68 | 1–1 |
| Pulse | 9.41 | 2–4 |
| Datalab | 9.38 | 2–4 |
| Mistral | 9.33 | 2–4 |
| Extend | 9.11 | 5–6 |
| LlamaParse | 9.05 | 5–6 |
| Azure | 7.85 | 7–7 |
| Cohere | 7.39 | 8–8 |
| vs vendor | GPT win/tie/loss % (r0+r1 avg) | Gemini win/tie/loss % |
|---|---|---|
| LlamaParse | 66 / 27 / 7 | 72 / 16 / 13 |
| Datalab | 30 / 63 / 8 | 48 / 33 / 19 |
| Extend | 45 / 49 / 6 | 53 / 30 / 17 |
| Mistral | 29 / 63 / 8 | 41 / 37 / 22 |
| Azure | 74 / 24 / 2 | 82 / 12 / 6 |
| Pulse | 28 / 63 / 9 | 39 / 37 / 24 |
| Cohere | 67 / 31 / 2 | 71 / 16 / 13 |
| vendor | clean | tilt_2_4 | scan | perspective |
|---|---|---|---|---|
| Reducto | 84.4 (84.4) | 84.5 (84.5) | 84.8 (84.8) | 84.6 (84.6) |
| LlamaParse | 80.5 (80.5) | 78.6 (78.6) | 81.1 (81.1) | 80.4 (80.4) |
| Datalab | 59.2 (82.6) | 59.4 (82.4) | 59.4 (82.5) | 59.2 (82.4) |
| Extend | 74.6 (74.6) | 73.1 (73.1) | 74.3 (74.3) | 74.4 (74.4) |
| Mistral | 89.4 (89.4) | 89.8 (89.7) | 89.7 (89.7) | 89.9 (89.9) |
| Azure | 79.4 (79.4) | 79.3 (79.3) | 79.7 (79.7) | 79.7 (79.7) |
| Pulse | 81.3 (81.3) | 79.8 (79.8) | 81.7 (81.7) | 81.2 (81.2) |
| Cohere | 83.3 (83.3) | 77.7 (77.7) | 83.0 (83.0) | 83.2 (83.2) |
| vendor | mean at original | mean at high (live) |
|---|---|---|
| Reducto | 9.61 | 9.58 |
| Datalab | 9.18 | 9.15 |
| Mistral | 9.13 | 9.08 |
| Pulse | 9.07 | 9.05 |
| Extend | 8.34 | 8.34 |
| LlamaParse | 7.32 | 7.33 |
| Azure | 6.79 | 6.80 |
| Cohere | 6.61 | 6.60 |
| vendor | clean pages rerun | tilt_2_4 pages rerun | scan pages rerun | perspective pages rerun |
|---|---|---|---|---|
| Pulse (402, new key) | 18 | 22 | 31 | 18 |
| Cohere (402/429, new account) | 45 | 33 | 35 | 43 |
| condition | judge tag | verdicts | with raw request/response |
|---|---|---|---|
| clean | gemini-3.1-pro-preview-medium-r0-ue42d6f | 500 | 500 |
| clean | gemini-3.1-pro-preview-medium-r1-ue42d6f | 500 | 500 |
| clean | gpt-6.1-sol-medium-r0 | 500 | 500 |
| clean | gpt-6.1-sol-medium-r1 | 500 | 500 |
| tilt_2_4 | gemini-3.1-pro-preview-medium-r0-ue42d6f | 500 | 500 |
| tilt_2_4 | gpt-6.1-sol-medium-r0 | 500 | 500 |
| scan | gemini-3.1-pro-preview-medium-r0-ue42d6f | 500 | 500 |
| scan | gpt-6.1-sol-medium-r0 | 500 | 500 |
| perspective | gemini-3.1-pro-preview-medium-r0-ue42d6f | 500 | 500 |
| perspective | gpt-6.1-sol-medium-r0 | 500 | 500 |
| preset | GPT r0 | GPT r1 | Gemini shared r0 | Gemini shared r1 | Gemini own r0 | Gemini own r1 | Gemini own mean |
|---|---|---|---|---|---|---|---|
| Reducto | 9.68 | 9.68 | 8.99 | 9.03 | 8.90 | 8.91 | 8.91 |
| Pulse | 9.40 | 9.41 | 8.63 | 8.69 | 8.56 | 8.63 | 8.60 |
| Datalab | 9.38 | 9.38 | 8.46 | 8.48 | 8.38 | 8.39 | 8.38 |
| Mistral | 9.33 | 9.33 | 8.54 | 8.61 | 8.49 | 8.62 | 8.55 |
| Extend | 9.14 | 9.08 | 8.21 | 8.23 | 8.11 | 8.21 | 8.16 |
| LlamaParse | 9.05 | 9.05 | 8.07 | 8.17 | 8.05 | 8.10 | 8.07 |
| Azure | 7.84 | 7.86 | 6.10 | 6.03 | 6.04 | 6.06 | 6.05 |
| Cohere | 7.40 | 7.39 | 6.38 | 6.40 | 6.32 | 6.32 | 6.32 |
| preset | native en | native zh | GPT clean en | GPT clean zh | Gemini clean en | Gemini clean zh |
|---|---|---|---|---|---|---|
| reducto_r1 | 88.2 | 80.6 | 9.75 | 9.61 | 8.89 | 8.90 |
| llamaparse_agentic_plus | 85.6 | 75.4 | 9.18 | 8.93 | 8.16 | 7.94 |
| datalab_accurate | 65.1 | 53.2 | 9.49 | 9.27 | 8.44 | 8.32 |
| extend_performance_agentic_formulas | 81.6 | 67.7 | 9.02 | 9.20 | 7.94 | 8.27 |
| mistral_ocr_4_1 | 91.1 | 87.8 | 9.50 | 9.15 | 8.55 | 8.43 |
| azure_layout_high_res_formulas | 86.7 | 72.1 | 8.57 | 7.13 | 7.03 | 5.04 |
| pulse_ultra_2 | 85.6 | 76.9 | 9.39 | 9.43 | 8.45 | 8.68 |
| cohere_parse_v5 | 86.8 | 79.9 | 8.95 | 5.84 | 8.14 | 4.50 |
| preset | native (as returned) | native (pipe tables -> HTML) | pages with pipe tables | pages moved > 10 points |
|---|---|---|---|---|
| reducto_r1 | 84.4 | 84.4 | 1 | 0 |
| llamaparse_agentic_plus | 80.5 | 80.5 | 2 | 0 |
| datalab_accurate | 59.2 | 82.6 | 275 | 241 |
| extend_performance_agentic_formulas | 74.6 | 74.6 | 0 | 0 |
| mistral_ocr_4_1 | 89.4 | 89.4 | 1 | 0 |
| azure_layout_high_res_formulas | 79.4 | 79.4 | 0 | 0 |
| pulse_ultra_2 | 81.3 | 81.3 | 1 | 0 |
| cohere_parse_v5 | 83.3 | 83.3 | 3 | 0 |
| probe | native score |
|---|---|
| probe-code_fence-gt | 98.6 |
| probe-digits_5pct-gt | 99.7 |
| probe-empty-gt | 0.0 |
| probe-html_tables-gt | 100.0 |
| probe-pipe_tables-gt | 91.4 |
| probe-pretty_html-gt | 92.3 |
| probe-shuffle_paragraphs-gt | 54.2 |
| probe-strip_emphasis-gt | 100.0 |
| gt | 100.0 |
| preset | clean (rank) | tilt_2_4 (rank) | scan (rank) | perspective (rank) |
|---|---|---|---|---|
| reducto_r1 | 8.90 (1) | 9.07 (1) Δ +0.17 [+0.04, +0.29] n=500 | 9.11 (1) Δ +0.22 [+0.08, +0.34] n=500 | 8.92 (1) Δ +0.02 [-0.11, +0.16] n=500 |
| llamaparse_agentic_plus | 8.05 (6) | 7.44 (6) Δ -0.61 [-0.79, -0.43] n=500 | 7.98 (6) Δ -0.07 [-0.21, +0.08] n=500 | 8.08 (5) Δ +0.03 [-0.10, +0.17] n=500 |
| datalab_accurate | 8.38 (4) | 8.39 (3) Δ +0.01 [-0.13, +0.14] n=500 | 8.53 (4) Δ +0.15 [+0.02, +0.29] n=500 | 8.39 (4) Δ +0.01 [-0.13, +0.15] n=500 |
| extend_performance_agentic_formulas | 8.11 (5) | 7.65 (5) Δ -0.45 [-0.60, -0.30] n=500 | 8.11 (5) Δ +0.00 [-0.13, +0.14] n=500 | 8.02 (6) Δ -0.08 [-0.22, +0.05] n=500 |
| mistral_ocr_4_1 | 8.49 (3) | 8.66 (2) Δ +0.17 [+0.03, +0.31] n=500 | 8.63 (2) Δ +0.14 [+0.00, +0.27] n=500 | 8.59 (3) Δ +0.10 [-0.04, +0.25] n=500 |
| azure_layout_high_res_formulas | 6.04 (8) | 6.22 (7) Δ +0.19 [+0.03, +0.34] n=500 | 6.23 (7) Δ +0.19 [+0.05, +0.35] n=500 | 6.20 (8) Δ +0.17 [+0.01, +0.33] n=500 |
| pulse_ultra_2 | 8.56 (2) | 7.79 (4) Δ -0.78 [-0.95, -0.59] n=500 | 8.61 (3) Δ +0.04 [-0.10, +0.18] n=500 | 8.69 (2) Δ +0.12 [-0.02, +0.27] n=500 |
| cohere_parse_v5 | 6.32 (7) | 5.04 (8) Δ -1.28 [-1.46, -1.11] n=500 | 6.19 (8) Δ -0.13 [-0.27, +0.02] n=500 | 6.34 (7) Δ +0.02 [-0.11, +0.16] n=500 |
