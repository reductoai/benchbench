# Refreshed ablations — snapshot 20261116T220719Z

Sol clean: per-page r0+r1 average on complete repeat intersections; tilt: r0. Both sides use exactly the same matched pages. Ties count as first; same-winner requires identical winner sets. Reducto rank uses competition ranks; Spearman uses average tie ranks.

| Judge | Condition | Status | Evaluated | Fully covered | Same winner | Reducto first | Matched/Sol pages | ok:false | Non-Reducto winners |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| argon | clean | complete_with_failures | 12/12 | 10/12 | 6/12 | 4/12 | 5219/5221 | 2 | DP-Bench: Pulse; olmOCR-Bench: Datalab; OmniParseBench: Datalab; OCRFlux-bench: Pulse; IDP Leaderboard: LlamaParse; MDPBench: LlamaParse; RD-TableBench: LlamaParse; PureDocBench: Datalab |
| argon | tilt_2_4 | complete_with_failures | 12/12 | 8/12 | 9/12 | 8/12 | 5213/5220 | 7 | olmOCR-Bench: Datalab; OmniParseBench: Datalab [failed pages excluded]; MDPBench: LlamaParse [failed pages excluded]; PureDocBench: Datalab |
| astra | clean | complete | 12/12 | 12/12 | 12/12 | 10/12 | 5221/5221 | 0 | IDP Leaderboard: LlamaParse; MDPBench: LlamaParse |
| astra | tilt_2_4 | complete | 12/12 | 12/12 | 12/12 | 9/12 | 5220/5220 | 0 | IDP Leaderboard: Mistral OCR; MDPBench: LlamaParse; PureDocBench: Datalab |
| fable | clean | complete_with_failures | 12/12 | 8/12 | 12/12 | 10/12 | 5212/5221 | 9 | IDP Leaderboard: LlamaParse; MDPBench: LlamaParse |
| fable | tilt_2_4 | complete_with_failures | 12/12 | 8/12 | 12/12 | 9/12 | 5212/5220 | 8 | IDP Leaderboard: Mistral OCR; MDPBench: LlamaParse; PureDocBench: Datalab |
| terse | clean | complete | 12/12 | 12/12 | 12/12 | 10/12 | 5221/5221 | 0 | IDP Leaderboard: LlamaParse; MDPBench: LlamaParse |
| terse | tilt_2_4 | complete | 12/12 | 12/12 | 10/12 | 9/12 | 5220/5220 | 0 | DP-Bench: Mistral OCR; IDP Leaderboard: Mistral OCR; MDPBench: LlamaParse |
| minimal | clean | complete | 12/12 | 12/12 | 12/12 | 10/12 | 5221/5221 | 0 | IDP Leaderboard: LlamaParse; MDPBench: LlamaParse |
| minimal | tilt_2_4 | complete | 12/12 | 12/12 | 10/12 | 11/12 | 5220/5220 | 0 | MDPBench: LlamaParse |

Score and relative-change intervals are 90% percentile intervals from 2,000 page bootstrap resamples (seed 0). Clean/tilt changes resample matched page pairs together and use `100 * (tilt / clean - 1)`; negative values indicate a loss. `p_reducto_top` is the fraction of score bootstrap samples in which Reducto is tied for first.
