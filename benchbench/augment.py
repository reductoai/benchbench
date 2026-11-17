"""Deterministic page perturbations. Each condition maps (image, rng) -> image.

Every condition is seeded from (study_seed, benchmark, page_id, condition), so a rerun gives the same
bytes, and every provider gets the same perturbed file. Parameters are recorded next to each image.
"""

import io
import random
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from .seeding import rng

WHITE = (255, 255, 255)


@dataclass(frozen=True)
class Condition:
    name: str
    description: str
    apply: Callable[[Image.Image, random.Random], tuple[Image.Image, dict]]


def _pad(img: Image.Image, frac: float) -> Image.Image:
    border = max(1, round(max(img.size) * frac))
    return ImageOps.expand(img, border=border, fill=WHITE)


def _rotate(img: Image.Image, angle: float) -> Image.Image:
    return img.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=WHITE)


def clean(img, r):
    return img, {}


def tilt(lo: float, hi: float):
    """Tilt: 2% white margin, then a random lo..hi degree turn either way."""

    def apply(img, r):
        angle = r.uniform(lo, hi) * r.choice([-1, 1])
        return _rotate(_pad(img, 0.02), angle), {"angle_deg": round(angle, 4), "pad_frac": 0.02}

    return apply


def jpeg(quality: int):
    def apply(img, r):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return Image.open(io.BytesIO(buf.getvalue())).convert("RGB"), {"jpeg_quality": quality}

    return apply


def low_res(target_dpi: int, source_dpi: int):
    """Downsample to target_dpi and back up: the page a cheap scanner or fax would produce."""

    def apply(img, r):
        w, h = img.size
        f = target_dpi / source_dpi
        small = img.resize((max(1, round(w * f)), max(1, round(h * f))), Image.Resampling.BILINEAR)
        return small.resize((w, h), Image.Resampling.BICUBIC), {"target_dpi": target_dpi}

    return apply


def scan(img, r):
    """Mild scan artefacts: 1-2 degree skew, slight blur, gray paper, sensor noise."""
    angle = r.uniform(1.0, 2.0) * r.choice([-1, 1])
    out = _rotate(_pad(img, 0.02), angle).filter(ImageFilter.GaussianBlur(radius=0.6))
    arr = np.asarray(out).astype(np.float32)
    gen = np.random.default_rng(r.getrandbits(32))
    # One noise plane for all channels: real scanner noise is mostly luminance, and per-channel noise
    # makes PNGs ~76x larger, which tests upload limits rather than reading.
    noise = gen.normal(0, 6, arr.shape[:2])[..., None]
    arr = np.round(arr * 0.92 + 8 + noise)
    # Grayscale output: a scanner's gray mode, and one channel keeps the file about 1/3 smaller.
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("L")
    return out, {
        "angle_deg": round(angle, 4),
        "blur_radius": 0.6,
        "noise_sigma": 6,
        "noise": "luminance",
        "gain": 0.92,
        "mode": "L",
    }


def _perspective_coeffs(out_pts, in_pts):
    """PIL PERSPECTIVE coefficients that map each output point onto its input point."""
    rows, rhs = [], []
    for (x, y), (u, v) in zip(out_pts, in_pts, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        rhs += [u, v]
    return tuple(np.linalg.solve(np.array(rows, dtype=float), np.array(rhs, dtype=float)))


def perspective(max_frac: float):
    """Phone-photo keystone: each page corner moves inward by up to max_frac of the page size."""

    def apply(img, r):
        img = _pad(img, 0.02)
        w, h = img.size
        page = [(0, 0), (w, 0), (w, h), (0, h)]
        offsets = [(r.uniform(0, max_frac), r.uniform(0, max_frac)) for _ in range(4)]
        signs = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
        moved = [
            (x + sx * dx * w, y + sy * dy * h)
            for (x, y), (dx, dy), (sx, sy) in zip(page, offsets, signs, strict=True)
        ]
        coeffs = _perspective_coeffs(moved, page)
        out = img.transform(
            (w, h), Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BICUBIC, fillcolor=WHITE
        )
        return out, {"corner_offsets_frac": [[round(dx, 4), round(dy, 4)] for dx, dy in offsets]}

    return apply


CONDITIONS: dict[str, Condition] = {
    c.name: c
    for c in [
        Condition("clean", "canonical render, no change", clean),
        Condition("tilt_2_4", "2% margin, random 2-4 deg rotation either way", tilt(2.0, 4.0)),
        Condition("tilt_0_5_1", "2% margin, random 0.5-1 deg rotation either way", tilt(0.5, 1.0)),
        Condition("jpeg_q30", "JPEG re-encode at quality 30", jpeg(30)),
        Condition("dpi_100", "downsample to 100 DPI and back", low_res(100, 200)),
        Condition("scan", "1-2 deg skew + blur + gray paper + noise", scan),
        Condition("perspective", "phone-photo keystone, corners in by up to 4%", perspective(0.04)),
    ]
}


def perturb(img: Image.Image, condition: str, study_seed: int, benchmark: str, page_id: str):
    cond = CONDITIONS[condition]
    r = rng(study_seed, benchmark, page_id, condition)
    out, params = cond.apply(img.convert("RGB"), r)
    return out, {"condition": condition, **params}


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()
