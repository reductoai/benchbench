"""Real5-OmniDocBench shares OmniDocBench's ground truth and scorer.

Each capture is a photo of an original page, so the original's annotations apply."""

from .omnidocbench import SCORER_COMMIT, export, gt_markdown, score  # noqa: F401
