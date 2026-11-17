| stage | what it says |
|---|---|
| 1. Native scorer (clean) | LlamaParse 88.95, Reducto 88.69, Mistral 87.78: the top three are within 1.2 points. LlamaParse minus Reducto +0.26 points (95% paired bootstrap CI -0.93 to +1.40), so the native scorer does not separate them. Reducto is 2nd on its own benchmark. |
| 2. Blind judge (clean) | Reducto first under both judges (GPT 9.51, Gemini 8.71, on a 1-10 scale), LlamaParse second (9.34, 8.54). Gemini does not separate Reducto from LlamaParse, so "Reducto beats LlamaParse on clean pages" is **not** claimed. Of the 24 vendor pairs GPT separates, Gemini confirms 22. |
| 3. Judge on perturbed pages | Reducto is first on every perturbation under both judges and loses at most 0.23 points (GPT; significant on all three perturbations, Gemini's changes are not significant). LlamaParse loses 1.35 on a 2-4° tilt (GPT; Gemini 1.29) and drops from 2nd to 5th; Cohere loses 1.38 and Pulse 1.12. Under GPT Reducto is separated from all 7 others at 95% on every perturbation; under Gemini (one pass) on tilt and scan, and on perspective 6 of 7, all but LlamaParse. |
| parser (preset) | as returned | clean | tilt 2-4° | scan | perspective | clean pages scoring 0 |
|---|---|---|---|---|---|---|
| LlamaParse (`llamaparse_agentic_plus`) | 88.9 | **88.9** | 81.3 (-7.6) | 85.5 (-3.4) | 88.2 (-0.7) | 2 |
| Reducto (`reducto_r1`) | 88.7 | **88.7** | 88.9 (+0.2) | 89.1 (+0.4) | 89.0 (+0.3) | 1 |
| Mistral OCR (`mistral_ocr_4_1`) | 87.8 | **87.8** | 87.2 (-0.6) | 86.9 (-0.8) | 86.7 (-1.1) | 7 |
| Extend (`extend_performance_agentic_formulas`) | 85.9 | **86.0** | 85.1 (-0.9) | 85.5 (-0.5) | 86.1 (+0.1) | 14 |
| Cohere (`cohere_parse_v5`) | 84.5 | **84.5** | 77.9 (-6.7) | 82.2 (-2.4) | 84.1 (-0.4) | 11 |
| Datalab (`datalab_accurate`) | 0.1 | **82.0** | 79.6 (-2.4) | 80.9 (-1.1) | 81.9 (-0.1) | 2 |
| Azure DI (`azure_layout_high_res_formulas`) | 79.8 | **79.8** | 81.2 (+1.4) | 82.1 (+2.4) | 82.1 (+2.3) | 13 |
| Pulse (`pulse_ultra_2`) | 68.8 | **68.8** | 66.8 (-1.9) | 77.9 (+9.2) | 69.2 (+0.5) | 76 |
| probe applied to ground truth | native mean |
|---|---|
| `code_fence` | 100.00 |
| `digits_5pct` | 98.27 |
| `empty` | 0.00 |
| `html_tables` | 100.00 |
| `pipe_tables` | 99.81 |
| `pretty_html` | 100.00 |
| `shuffle_paragraphs` | 92.26 |
| `strip_emphasis` | 99.90 |
| preset | native (rank) | clean judge (rank) | tilt_2_4 judge (rank) | scan judge (rank) | perspective judge (rank) |
| reducto_r1 | 88.7 (2) | 9.51 (1) | 9.31 (1) Δ -0.20 [-0.28, -0.12] | 9.28 (1) Δ -0.23 [-0.30, -0.16] | 9.37 (1) Δ -0.13 [-0.19, -0.07] |
| llamaparse_agentic_plus | 88.9 (1) | 9.34 (2) | 7.99 (5) Δ -1.35 [-1.52, -1.18] | 8.74 (4) Δ -0.60 [-0.73, -0.47] | 9.17 (2) Δ -0.17 [-0.25, -0.08] |
| datalab_accurate | 82.0 (6) | 8.96 (4) | 8.44 (4) Δ -0.52 [-0.65, -0.40] | 8.64 (5) Δ -0.32 [-0.43, -0.21] | 8.91 (4) Δ -0.05 [-0.13, +0.03] |
| extend_performance_agentic_formulas | 86.0 (4) | 9.07 (3) | 8.80 (3) Δ -0.26 [-0.37, -0.16] | 9.01 (3) Δ -0.06 [-0.16, +0.03] | 9.12 (3) Δ +0.06 [-0.03, +0.14] |
| mistral_ocr_4_1 | 87.8 (3) | 8.80 (5) | 8.93 (2) Δ +0.13 [+0.04, +0.22] | 9.08 (2) Δ +0.28 [+0.17, +0.37] | 8.90 (5) Δ +0.10 [+0.01, +0.19] |
| azure_layout_high_res_formulas | 79.8 (7) | 7.26 (8) | 7.18 (6) Δ -0.08 [-0.19, +0.02] | 7.42 (7) Δ +0.16 [+0.07, +0.26] | 7.30 (7) Δ +0.04 [-0.04, +0.13] |
| pulse_ultra_2 | 68.8 (8) | 7.43 (7) | 6.31 (7) Δ -1.12 [-1.30, -0.93] | 7.63 (6) Δ +0.20 [+0.03, +0.37] | 7.28 (8) Δ -0.15 [-0.30, -0.01] |
| cohere_parse_v5 | 84.5 (5) | 7.53 (6) | 6.15 (8) Δ -1.38 [-1.56, -1.21] | 7.19 (8) Δ -0.34 [-0.47, -0.20] | 7.49 (6) Δ -0.04 [-0.15, +0.07] |
| preset | Gemini own order (rank) | 90% CI | GPT clean (rank) |
|---|---|---|---|
| reducto_r1 | 8.71 (1) | 8.60-8.82 | 9.51 (1) |
| llamaparse_agentic_plus | 8.54 (2) | 8.42-8.65 | 9.34 (2) |
| datalab_accurate | 7.78 (5) | 7.64-7.92 | 8.96 (4) |
| extend_performance_agentic_formulas | 7.81 (4) | 7.66-7.96 | 9.07 (3) |
| mistral_ocr_4_1 | 7.87 (3) | 7.73-8.02 | 8.80 (5) |
| azure_layout_high_res_formulas | 4.94 (8) | 4.79-5.11 | 7.26 (8) |
| pulse_ultra_2 | 5.84 (7) | 5.64-6.05 | 7.43 (7) |
| cohere_parse_v5 | 6.44 (6) | 6.26-6.61 | 7.53 (6) |
| preset | native (rank) | clean judge (rank) | tilt_2_4 judge (rank) | scan judge (rank) | perspective judge (rank) |
| reducto_r1 | 88.7 (2) | 8.66 (1) | 8.56 (1) Δ -0.10 [-0.24, +0.04] | 8.61 (1) Δ -0.05 [-0.19, +0.09] | 8.66 (1) Δ +0.00 [-0.14, +0.15] |
| llamaparse_agentic_plus | 88.9 (1) | 8.50 (2) | 7.21 (5) Δ -1.29 [-1.51, -1.06] | 7.88 (4) Δ -0.62 [-0.79, -0.43] | 8.46 (2) Δ -0.04 [-0.20, +0.12] |
| datalab_accurate | 82.0 (6) | 7.72 (5) | 7.40 (4) Δ -0.32 [-0.50, -0.14] | 7.60 (5) Δ -0.13 [-0.31, +0.05] | 7.79 (5) Δ +0.07 [-0.09, +0.23] |
| extend_performance_agentic_formulas | 86.0 (4) | 7.89 (3) | 7.84 (3) Δ -0.05 [-0.23, +0.14] | 7.98 (3) Δ +0.09 [-0.07, +0.26] | 8.03 (4) Δ +0.13 [-0.02, +0.30] |
| mistral_ocr_4_1 | 87.8 (3) | 7.87 (4) | 8.13 (2) Δ +0.27 [+0.12, +0.41] | 8.18 (2) Δ +0.32 [+0.16, +0.47] | 8.04 (3) Δ +0.18 [+0.04, +0.32] |
| azure_layout_high_res_formulas | 79.8 (7) | 4.92 (8) | 4.98 (7) Δ +0.06 [-0.10, +0.22] | 5.25 (8) Δ +0.33 [+0.17, +0.49] | 5.05 (8) Δ +0.13 [-0.01, +0.29] |
| pulse_ultra_2 | 68.8 (8) | 5.77 (7) | 4.87 (8) Δ -0.90 [-1.13, -0.68] | 6.37 (6) Δ +0.61 [+0.38, +0.83] | 5.75 (7) Δ -0.02 [-0.22, +0.19] |
| cohere_parse_v5 | 84.5 (5) | 6.48 (6) | 5.15 (6) Δ -1.33 [-1.54, -1.12] | 6.16 (7) Δ -0.32 [-0.51, -0.13] | 6.48 (6) Δ +0.00 [-0.15, +0.15] |
| preset | native (rank) | clean judge (rank) | tilt_2_4 judge (rank) | scan judge (rank) | perspective judge (rank) |
|---|---|---|---|---|---|
| reducto_r1 | 88.7 (2) | 9.51 (1) | 9.31 (1) Δ -0.20 [-0.28, -0.12] | 9.28 (1) Δ -0.23 [-0.30, -0.16] | 9.37 (1) Δ -0.13 [-0.19, -0.07] |
| llamaparse_agentic_plus | 88.9 (1) | 9.34 (2) | 7.99 (5) Δ -1.35 [-1.52, -1.18] | 8.74 (4) Δ -0.60 [-0.73, -0.47] | 9.17 (2) Δ -0.17 [-0.25, -0.08] |
| datalab_accurate | 82.0 (6) | 8.96 (4) | 8.44 (4) Δ -0.52 [-0.65, -0.40] | 8.64 (5) Δ -0.32 [-0.43, -0.21] | 8.91 (4) Δ -0.05 [-0.13, +0.03] |
| extend_performance_agentic_formulas | 86.0 (4) | 9.07 (3) | 8.80 (3) Δ -0.26 [-0.37, -0.16] | 9.01 (3) Δ -0.06 [-0.16, +0.03] | 9.12 (3) Δ +0.06 [-0.03, +0.14] |
| mistral_ocr_4_1 | 87.8 (3) | 8.80 (5) | 8.93 (2) Δ +0.13 [+0.04, +0.22] | 9.08 (2) Δ +0.28 [+0.17, +0.37] | 8.90 (5) Δ +0.10 [+0.01, +0.19] |
| azure_layout_high_res_formulas | 79.8 (7) | 7.26 (8) | 7.18 (6) Δ -0.08 [-0.19, +0.02] | 7.42 (7) Δ +0.16 [+0.07, +0.26] | 7.30 (7) Δ +0.04 [-0.04, +0.13] |
| pulse_ultra_2 | 68.8 (8) | 7.43 (7) | 6.31 (7) Δ -1.12 [-1.30, -0.93] | 7.63 (6) Δ +0.20 [+0.03, +0.37] | 7.28 (8) Δ -0.15 [-0.30, -0.01] |
| cohere_parse_v5 | 84.5 (5) | 7.53 (6) | 6.15 (8) Δ -1.38 [-1.56, -1.21] | 7.19 (8) Δ -0.34 [-0.47, -0.20] | 7.49 (6) Δ -0.04 [-0.15, +0.07] |
| condition | pages | dropped (failed parse) | failed parses by preset |
|---|---|---|---|
| clean | 500 | 0 | none |
| tilt_2_4 | 500 | 0 | none |
| scan | 500 | 0 | none |
| perspective | 500 | 0 | none |
