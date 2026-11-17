"""Stages: sample -> render -> perturb -> parse -> judge. Each stage is idempotent and append-safe."""

import hashlib
import importlib
import json
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from . import PARSEJUDGE_COMMIT, bridge
from .augment import CONDITIONS, perturb
from .catalog import load_catalog
from .datasets import fetch, sample_pages
from .render import page_count, render_page, to_png
from .seeding import derive_seed, sha256_bytes
from .storage import Run, done, page_key, read_json, write_bytes, write_json, write_jsonl

FAKE_PRESETS = {"fake_ocr", "fake_empty", "fake_fail"}
REAL5_CONDITIONS = (
    "real_illumination",
    "real_scanning",
    "real_screen_photography",
    "real_skew",
    "real_warping",
)


def log(msg: str) -> None:
    print(f"[{datetime.now(UTC).strftime('%H:%M:%S')}] {msg}", flush=True)


def init_run(root: Path, benchmarks: list[str], n: int | None, seed: int, dpi: int, notes: str = "") -> Run:
    run = Run(root)
    cfg = run.config
    if cfg and (cfg["seed"] != seed or cfg["dpi"] != dpi):
        raise SystemExit(f"{root} exists with seed={cfg['seed']} dpi={cfg['dpi']}; use a new run directory")
    catalog = load_catalog()
    rows = {(p["benchmark"], p["page_id"]): p for p in run.pages()}
    for b in benchmarks:
        for p in sample_pages(catalog[b], n, seed):
            p["page_key"] = page_key(p["benchmark"], p["page_id"])
            rows.setdefault((p["benchmark"], p["page_id"]), p)
    write_jsonl(root / "pages.jsonl", sorted(rows.values(), key=lambda p: p["page_key"]))
    write_json(
        root / "run.json",
        {
            **cfg,
            "seed": seed,
            "dpi": dpi,
            "benchmarks": sorted(set(cfg.get("benchmarks", [])) | set(benchmarks)),
            "sample_n": n,
            "parsejudge_commit": PARSEJUDGE_COMMIT,
            "notes": notes,
            "created": cfg.get("created") or datetime.now(UTC).isoformat(),
        },
    )
    log(f"{len(rows)} pages in {root}")
    return run


def render_all(run: Run, workers: int = 8) -> None:
    catalog, dpi = load_catalog(), run.config["dpi"]

    def one(p):
        out = run.image("clean", p["page_key"])
        if out.exists():
            return
        src = fetch(p, catalog[p["benchmark"]])
        n_pages = page_count(src)
        if n_pages != 1 and catalog[p["benchmark"]].get("multi_page") != "first":
            raise RuntimeError(
                f"{p['page_key']} has {n_pages} pages; set multi_page: first in catalog.yaml only if the "
                "benchmark itself scores page 1, otherwise add per-page sampling"
            )
        data = to_png(render_page(src, p["page_index"], dpi))
        write_bytes(out, data)
        write_json(
            run.image_meta("clean", p["page_key"]),
            {
                "condition": "clean",
                "sha256": sha256_bytes(data),
                "bytes": len(data),
                "dpi": dpi,
                "source_pages": n_pages,
            },
        )

    _pool(one, run.pages(), workers, "render")


def perturb_all(run: Run, conditions: list[str], workers: int = 8) -> None:
    seed = run.config["seed"]
    for cond in conditions:
        if cond == "clean":
            continue
        if cond not in CONDITIONS and cond not in REAL5_CONDITIONS:
            raise SystemExit(f"unknown condition {cond}; known: {', '.join(CONDITIONS + REAL5_CONDITIONS)}")

        def one(p, cond=cond):
            out = run.image(cond, p["page_key"])
            if out.exists():
                return
            if cond in REAL5_CONDITIONS:
                cap = (p.get("captures") or {}).get(cond)
                if not cap:
                    raise RuntimeError(
                        f"{p['page_key']}: no {cond} capture (sample with a pair_with benchmark)"
                    )
                src = fetch({**p, **cap}, load_catalog()[p["benchmark"]])
                data = to_png(Image.open(src).convert("RGB"))
                write_bytes(out, data)
                write_json(
                    run.image_meta(cond, p["page_key"]),
                    {
                        "condition": cond,
                        "capture": cap["file"],
                        "sha256": sha256_bytes(data),
                        "bytes": len(data),
                    },
                )
                return
            img = Image.open(run.image("clean", p["page_key"])).convert("RGB")
            new, params = perturb(img, cond, seed, p["benchmark"], p["page_id"])
            data = to_png(new)
            write_bytes(out, data)
            write_json(
                run.image_meta(cond, p["page_key"]),
                {**params, "sha256": sha256_bytes(data), "bytes": len(data)},
            )

        _pool(one, run.pages(), workers, f"perturb {cond}")


_FETCH_ERROR = re.compile(
    r"download|fetch|retrieve|unreachable|could not (get|access|open) (the )?(url|image)", re.I
)


_S3_HOST_LOCK = threading.Lock()
_S3_HOST_CLIENT: list = []
_URLS: dict = {}


HOST_ENV = ("BENCHBENCH_S3_BUCKET", "BENCHBENCH_S3_ACCESS_KEY_ID", "BENCHBENCH_S3_SECRET_ACCESS_KEY")


def load_host_env() -> None:
    """Load optional hosting credentials without overriding the process environment."""
    path = Path(os.environ.get("BENCHBENCH_HOST_ENV") or Path.home() / ".benchbench-host.env").expanduser()
    if path.exists():
        for line in path.read_text().splitlines():
            k, sep, v = line.removeprefix("export ").strip().partition("=")
            if sep and k and k not in os.environ:
                os.environ[k] = v.strip().strip("'\"")
    if missing := [k for k in HOST_ENV if not os.environ.get(k)]:
        raise SystemExit(
            f"missing {', '.join(missing)} (looked in {path}): run `benchbench host` once for this benchmark"
        )


def _s3_host():
    # One shared client: a boto3 client per call under 96 threads used >30 GB and was OOM-killed.
    with _S3_HOST_LOCK:
        if not _S3_HOST_CLIENT:
            _S3_HOST_CLIENT.append(_new_s3_host())
        return _S3_HOST_CLIENT[0]


def _new_s3_host():
    import boto3
    from botocore.config import Config

    need = ("BENCHBENCH_S3_BUCKET", "BENCHBENCH_S3_ACCESS_KEY_ID", "BENCHBENCH_S3_SECRET_ACCESS_KEY")
    if missing := [k for k in need if not os.environ.get(k)]:
        raise SystemExit(
            f"missing {', '.join(missing)}: run `benchbench host` once per benchmark and source its env file"
        )
    client = boto3.client(
        "s3",
        endpoint_url=os.environ.get("BENCHBENCH_S3_ENDPOINT_URL"),
        aws_access_key_id=os.environ["BENCHBENCH_S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["BENCHBENCH_S3_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("BENCHBENCH_S3_REGION", "us-east-1"),
        config=Config(signature_version="s3v4"),
    )
    return client, os.environ["BENCHBENCH_S3_BUCKET"]


def _page_url(path: Path) -> str:
    """24-hour presigned URL for an image in the configured S3-compatible bucket."""
    cached = _URLS.get(str(path))
    if cached and time.time() - cached[1] < 12 * 3600:
        return cached[0]
    data = path.read_bytes()
    key = f"p/{sha256_bytes(data)}.png"
    s3, bucket = _s3_host()
    try:
        s3.head_object(Bucket=bucket, Key=key)
    except Exception:
        s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType="image/png")
    url = s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=86400)
    _URLS[str(path)] = (url, time.time())
    return url


def make_host(env_file: Path, days: int = 30) -> dict:
    """Validate user-provisioned S3-compatible hosting. No credentials are written to disk."""
    os.environ["BENCHBENCH_HOST_ENV"] = str(env_file)
    load_host_env()
    client, bucket = _s3_host()
    client.head_bucket(Bucket=bucket)
    return {"bucket": bucket, "env_file": str(env_file), "lifecycle": "managed by bucket owner"}


def _fake_parse(preset: str, key: str, cond: str) -> dict:
    text = "" if preset == "fake_empty" else f"# {key}\n\nFake parse of {key} under {cond}.\n"
    return {
        "ok": not (preset == "fake_fail" and derive_seed(key, cond) % 10 == 0),
        "presetId": preset,
        "provider": "fake",
        "markdown": text,
        "raw": None,
        "reportedCost": None,
        "listPriceUsdPerPage": 0,
        "latencyMs": 1,
    }


def _archive_attempt(run: Run, out: Path, cond: str, preset: str, key: str, tag: str, obj) -> None:
    rec = dict(obj or {}, page_key=key, condition=cond, archived=datetime.now(UTC).isoformat())
    write_json(run.root / "attempts" / cond / preset / f"{out.stem}.{tag}.json", rec)


def parse_all(
    run: Run, presets: list[str], conditions: list[str], workers: int = 16, retries: int = 6
) -> None:
    # Interleave vendors and pages so a wide pool spreads load; a per-preset cap keeps each vendor under
    # its rate limit (BENCHBENCH_PER_PRESET, default 16 in flight).
    jobs = sorted(
        ((c, s, p) for c in conditions for s in presets for p in run.pages()),
        key=lambda j: derive_seed(j[0], j[1], j[2]["page_key"]),
    )
    cap = int(os.environ.get("BENCHBENCH_PER_PRESET", "16"))
    # Per-vendor overrides for slow vendors, e.g. BENCHBENCH_PRESET_CAPS="llamaparse_agentic_plus=48,..."
    caps = dict(kv.split("=") for kv in os.environ.get("BENCHBENCH_PRESET_CAPS", "").split(",") if kv)
    gates = {s: threading.BoundedSemaphore(int(caps.get(s, cap))) for s in presets}
    # Seconds between job-status polls per vendor, e.g. BENCHBENCH_POLL_SECS="llamaparse_agentic_plus=10".
    polls = dict(kv.split("=") for kv in os.environ.get("BENCHBENCH_POLL_SECS", "").split(",") if kv)

    if any(s not in FAKE_PRESETS for s in presets):
        load_host_env()

    def one(job):
        with gates[job[1]]:
            _parse_one(job)

    def _parse_one(job):
        cond, preset, p = job
        out = run.parse(cond, preset, p["page_key"])
        if done(out):
            return
        img = run.image(cond, p["page_key"])
        if preset in FAKE_PRESETS:
            write_json(out, _fake_parse(preset, p["page_key"], cond))
            return
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        # Keep every attempt: an earlier run's failed record and each retried attempt go to RUN/attempts/.
        if out.exists():
            _archive_attempt(run, out, cond, preset, p["page_key"], f"{stamp}-prior", read_json(out))
            out.unlink()
        result: dict = {}
        for attempt in range(retries):
            req = {"op": "parse", "presetId": preset, "imageUrl": _page_url(img), "imagePath": str(img)}
            if preset in polls:
                req["pollSec"] = float(polls[preset])
            result = bridge.call(req)
            fetch_error = not result.get("ok") and bool(_FETCH_ERROR.search(str(result.get("error"))))
            if result.get("ok") or not (result.get("retryable") or fetch_error):
                break
            _archive_attempt(run, out, cond, preset, p["page_key"], f"{stamp}-try{attempt}", result)
            time.sleep(min(120, 5 * 2**attempt) * random.uniform(0.5, 1.5))
        result.update(
            {
                "page_key": p["page_key"],
                "condition": cond,
                "image_sha256": sha256_bytes(img.read_bytes()),
                "image_bytes": img.stat().st_size,
                "image_host": "s3-presigned",
                # The provider could not fetch our URL: a harness fault, counted apart from parse failures.
                "harness_error": not result.get("ok") and bool(_FETCH_ERROR.search(str(result.get("error")))),
                "finished": datetime.now(UTC).isoformat(),
            }
        )
        write_json(out, result)
        if not result.get("ok"):
            raise RuntimeError(f"{preset} {p['page_key']}: {str(result.get('error'))[:200]}")

    _pool(one, jobs, workers, "parse")


DEFAULT_BASE_URL = "https://api.openai.com/v1"


def judge_tag(
    model: str,
    effort: str,
    repeat: int,
    prompt: str = "parsejudge",
    image: str = "clean",
    allow_failed: bool = False,
    base_url: str = DEFAULT_BASE_URL,
    strip_style: bool = False,
    label: str = "",
    image_detail: str = bridge.IMAGE_DETAIL,
    gemini_resolution: str = bridge.GEMINI_MEDIA_RESOLUTION,
    label_order: str = "shared",
) -> str:
    """Directory name for one judge configuration. Every setting that changes a verdict is in the tag,
    so primary, secondary and sensitivity runs never share verdict files."""
    parts = [] if prompt == "parsejudge" else [prompt]
    parts.append(f"{model.replace('/', '_')}-{effort}-r{repeat}")
    if label_order != "shared":
        parts.append(label_order)
    if image != "clean":
        parts.append("img-cond")
    if allow_failed:
        parts.append("failed-empty")
    if strip_style:
        parts.append("nostyle")
    if base_url.rstrip("/") != DEFAULT_BASE_URL:
        parts.append("u" + hashlib.sha256(base_url.rstrip("/").encode()).hexdigest()[:6])
    if image_detail != bridge.IMAGE_DETAIL:
        parts.append(f"detail-{image_detail}")
    if gemini_resolution != bridge.GEMINI_MEDIA_RESOLUTION:
        parts.append("gem-" + gemini_resolution.removeprefix("MEDIA_RESOLUTION_").lower())
    if label:
        parts.append(label)
    return "-".join(parts)


def blind_id(page_key: str, cond: str, repeat: int, model: str, label_order: str = "shared") -> str:
    """Seed of the label order the judge sees. "shared": (page, condition, repeat), so every judge model gets
    the same order as the GPT primary at that repeat. "own": the judge model is added, so a second judge's
    order is independent of the primary's (cross-judge agreement then controls for position bias)."""
    base = f"{page_key}|{cond}|r{repeat}"
    return base if label_order == "shared" else f"{base}|{model}"


def label_order_map(bid: str, presets: list[str]) -> dict[str, str]:
    """Pinned Parse Judge blinding (judge.ts blindLabels): parse_a, parse_b, ... by sha256(id:preset)."""
    keyed = sorted(presets, key=lambda s: hashlib.sha256(f"{bid}:{s}".encode()).hexdigest())
    return {f"parse_{chr(97 + i)}": s for i, s in enumerate(keyed)}


_STYLE = [
    (re.compile(r"<!--.*?-->", re.S), ""),
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), ""),
    (re.compile(r"</?span[^>]*>"), ""),
    (re.compile(r'\s(?:id|class|data-[\w-]+)="[^"]*"'), ""),
]


def strip_style(md: str) -> str:
    """Remove vendor-identifying markup that carries no page content: comments, image refs, spans, ids."""
    for rx, rep in _STYLE:
        md = rx.sub(rep, md)
    return md


def _fake_judge(markdown_by_preset: dict[str, str], page_id: str) -> dict:
    verdicts = []
    for preset, md in markdown_by_preset.items():
        score = 1 if not md.strip() else 1 + derive_seed(page_id, preset) % 10
        verdicts.append({"presetId": preset, "score": score, "reasoning": "fake", "errors": []})
    return {
        "ok": True,
        "judgeVersion": "fake",
        "verdicts": verdicts,
        "usage": [{"model": "fake"}],
        "latencyMs": 0,
    }


def _prompt_sha(prompt: str, model: str) -> str | None:
    """Hash of the exact judge prompt text, so an edited prompt with an unchanged version string rejudges."""
    if model == "fake":
        return None
    if prompt == "neutral":
        from . import neutral_judge

        return hashlib.sha256(neutral_judge.PROMPT.encode()).hexdigest()[:16]
    if prompt in ("minimal", "terse"):
        mod = importlib.import_module(f".{prompt}_judge", __package__)

        return hashlib.sha256(mod.PROMPT.encode()).hexdigest()[:16]
    root = bridge.parsejudge_dir() / "packages" / "core" / "src"
    name = "prompt.benchbench-png.ts" if prompt == "parsejudge" else "prompt.ts"
    return hashlib.sha256((root / name).read_bytes()).hexdigest()[:16]


def _md_hash(md: str) -> str:
    return hashlib.sha256(md.encode()).hexdigest()[:16]


def judge_all(
    run: Run,
    presets: list[str],
    conditions: list[str],
    model: str,
    effort: str = "medium",
    repeats: int = 1,
    workers: int = 16,
    base_url: str = DEFAULT_BASE_URL,
    key_env: str = "OPENAI_API_KEY",
    prompt: str = "parsejudge",
    image: str = "clean",
    allow_failed: bool = False,
    style_strip: bool = False,
    label: str = "",
    image_detail: str = bridge.IMAGE_DETAIL,
    gemini_resolution: str = bridge.GEMINI_MEDIA_RESOLUTION,
    label_order: str = "shared",
) -> None:
    """One blind call per (page, condition, repeat) with every preset's parse.

    - One judge model per run: no fallback model, so verdicts are never mixed across models. Rate limits are
      retried with backoff; the model that answered is written into each verdict file.
    - `image="clean"` (default) judges every condition's parse against the clean page, so stage 3 measures
      parser loss and not the judge reading a worse image.
    - A page with any failed parse is not judged unless `allow_failed`, in which case failed parses are
      judged as empty text and listed in `failed_parses` (the secondary analysis).
    - `label_order="own"` seeds the label order on the judge model too (see `blind_id`) and judges into its
      own `-own` tag, next to the shared-order verdicts.
    - A verdict is reused only when the markdown hashes, judge version, image hash and request config all
      match; anything else rejudges.
    """
    if prompt not in ("parsejudge", "parsejudge-upstream", "neutral", "minimal", "terse"):
        raise ValueError(f"unknown judge prompt {prompt}")
    if image_detail != bridge.IMAGE_DETAIL and prompt == "parsejudge-upstream":
        raise ValueError("--image-detail needs --prompt parsejudge or neutral (upstream is fixed at high)")
    gemini = bool(gemini_resolution)
    if gemini and (
        prompt in ("neutral", "minimal", "terse") or "generativelanguage.googleapis.com" not in base_url
    ):
        raise ValueError("--gemini-media-resolution needs a Gemini --judge-base-url and a parsejudge prompt")
    jobs = [(c, r, p) for c in conditions for r in range(repeats) for p in run.pages()]
    skipped: dict[str, list[str]] = {"missing_parse": [], "failed_parse": []}
    if model == "fake":
        version = "fake"
    elif prompt == "neutral":
        from .neutral_judge import PROMPT_VERSION as version
    elif prompt in ("minimal", "terse"):
        version = importlib.import_module(f".{prompt}_judge", __package__).PROMPT_VERSION
    else:
        version = bridge.PNG_VERSION if prompt == "parsejudge" else "compare-v4"

    def one(job):
        cond, rep, p = job
        tag = judge_tag(
            model,
            effort,
            rep,
            prompt,
            image,
            allow_failed,
            base_url,
            style_strip,
            label,
            image_detail,
            gemini_resolution,
            label_order,
        )
        out = run.judge(cond, tag, p["page_key"])
        parses = {s: read_json(run.parse(cond, s, p["page_key"])) for s in presets}
        missing = [s for s, v in parses.items() if v is None or v.get("harness_error")]
        if missing:
            skipped["missing_parse"].append(f"{cond}/{p['page_key']}: {','.join(missing)}")
            return
        failed = sorted(s for s, v in parses.items() if not v.get("ok"))
        if failed and not allow_failed:
            skipped["failed_parse"].append(f"{cond}/{p['page_key']}: {','.join(failed)}")
            return
        md = {s: (v.get("markdown") or "") if v.get("ok") else "" for s, v in parses.items()}
        if style_strip:
            md = {s: strip_style(m) for s, m in md.items()}
        hashes = {s: _md_hash(m) for s, m in md.items()}
        img = run.image(image if image == "clean" else cond, p["page_key"])
        config = {
            "model": model,
            "effort": effort,
            "prompt": prompt,
            "base_url": base_url.rstrip("/"),
            "judge_image": image if image == "clean" else cond,
            "image_sha256": sha256_bytes(img.read_bytes()),
            "allow_failed": allow_failed,
            "strip_style": style_strip,
            "parsejudge_commit": PARSEJUDGE_COMMIT,
            "prompt_sha": _prompt_sha(prompt, model),
        }
        # Image settings enter the config only when not the default, so verdicts made before these keys
        # existed (all at the defaults) still match and are not rejudged.
        if image_detail != bridge.IMAGE_DETAIL:
            config["image_detail"] = image_detail
        if gemini:
            config["image_resolution"] = gemini_resolution
        if label_order != "shared":
            config["label_order"] = label_order
        if base_url.startswith("https://api.anthropic.com/"):
            img = _fit_anthropic_image(run, image if image == "clean" else cond, p["page_key"], img, config)
        prev = read_json(out) if done(out) else None
        if (
            prev
            and prev.get("markdown_sha") == hashes
            and prev.get("judgeVersion") == version
            and prev.get("config") == config
        ):
            return
        bid = blind_id(p["page_key"], cond, rep, model, label_order)
        if prompt == "neutral":
            from . import neutral_judge

            labels = neutral_judge.blind_labels(bid, list(md))
        else:
            labels = label_order_map(bid, list(md))
        if model == "fake":
            result = _fake_judge(md, bid)
        elif prompt in ("minimal", "terse"):
            result = importlib.import_module(f".{prompt}_judge", __package__).judge_page(
                labels,
                img.read_bytes(),
                md,
                model,
                base_url,
                os.environ.get(key_env, ""),
                effort,
                image_detail=image_detail,
            )
        elif prompt == "neutral":
            from . import neutral_judge

            result = neutral_judge.judge_page(
                bid,
                img.read_bytes(),
                md,
                model,
                base_url,
                os.environ.get(key_env, ""),
                effort,
                image_detail=image_detail,
            )
        else:
            result = bridge.call(
                {
                    "op": "judge",
                    "pageId": bid,
                    "imagePath": str(img),
                    "markdownByPreset": md,
                    "models": [model],
                    "reasoningEffort": effort,
                    "baseUrl": base_url,
                    "promptVariant": "upstream" if prompt == "parsejudge-upstream" else "png",
                    **({"geminiMediaResolution": gemini_resolution} if gemini else {}),
                },
                env={"JUDGE_API_KEY": os.environ.get(key_env, ""), "BENCHBENCH_IMAGE_DETAIL": image_detail},
            )
        answered = sorted({u.get("model") for u in result.get("usage") or [] if u.get("model")})
        result.update(
            {
                "page_key": p["page_key"],
                "condition": cond,
                "repeat": rep,
                "prompt": prompt,
                "judgeVersion": result.get("judgeVersion") or version,
                "judge_image": image if image == "clean" else cond,
                "requested_model": model,
                "answered_models": answered,
                "presets": sorted(presets),
                "markdown_sha": hashes,
                "blind_id": bid,
                "label_order": labels,
                "config": config,
                "failed_parses": failed,
                "finished": datetime.now(UTC).isoformat(),
            }
        )
        raw = out.with_name(f"{out.stem}.raw.json")
        if out.exists():
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
            prior = run.root / "attempts" / "judge" / cond / tag
            write_json(prior / f"{out.stem}.{stamp}-prior.json", read_json(out))
            if raw.exists():
                write_json(prior / f"{out.stem}.{stamp}-prior.raw.json", read_json(raw))
        # Full judge request (prompt text, image as sha256 + bytes) and raw model response, every call.
        write_json(
            raw,
            {
                "page_key": p["page_key"],
                "condition": cond,
                "blind_id": bid,
                "label_order": labels,
                "exchanges": result.pop("exchanges", []),
            },
        )
        write_json(out, result)

    _pool(one, jobs, workers, f"judge {prompt}/{model}")
    for why, items in skipped.items():
        if items:
            log(f"judge skipped {len(items)} page-conditions ({why}); first: {items[:3]}")
            write_json(run.root / "judge" / f"skipped_{why}.json", sorted(items))


def _pool(fn, items, workers: int, label: str) -> None:
    items = list(items)
    errors = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fn, it): it for it in items}
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                fut.result()
            except Exception as e:  # keep going; the artefact stays missing and a rerun retries it
                errors += 1
                log(f"{label} error: {type(e).__name__}: {str(e)[:300]}")
            if i % 50 == 0 or i == len(items):
                log(f"{label}: {i}/{len(items)} ({errors} errors)")


S3_BUCKET = os.environ.get("BENCHBENCH_RESULTS_BUCKET", "")


def upload_s3(run: Run, benchmark: str, bucket: str = S3_BUCKET, workers: int = 64) -> dict:
    """Mirror the whole run directory (images, raw parse records and every earlier attempt, judge verdicts,
    native scores, reports) to s3://<bucket>/benchbench/runs/<benchmark>/. Uploads files that are missing or
    differ in size; safe to rerun at any time and after every stage. Writes a manifest of what is there."""
    import boto3
    from botocore.config import Config

    s3 = boto3.client("s3", region_name="us-west-2", config=Config(max_pool_connections=workers))
    prefix = f"benchbench/runs/{benchmark}/"
    have = {}
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        have.update({o["Key"]: o["Size"] for o in page.get("Contents", [])})
    sizes = {}
    for f in run.root.rglob("*"):
        try:  # a running native scorer creates and deletes temp files while we walk
            if f.is_file() and ".tmp" not in f.name:
                sizes[f] = f.stat().st_size
        except FileNotFoundError:
            continue
    files = list(sizes)
    todo = [f for f in files if have.get(prefix + f.relative_to(run.root).as_posix()) != sizes[f]]

    def one(f):
        try:
            s3.upload_file(str(f), bucket, prefix + f.relative_to(run.root).as_posix())
        except FileNotFoundError:
            pass

    _pool(one, todo, workers, "upload")
    manifest = {
        "bucket": bucket,
        "prefix": prefix,
        "files": len(files),
        "uploaded_now": len(todo),
        "bytes": sum(sizes.values()),
        "finished": datetime.now(UTC).isoformat(),
    }
    s3.put_object(Bucket=bucket, Key=prefix + "_manifest.json", Body=json.dumps(manifest, indent=1).encode())
    return manifest


def status(run: Run) -> dict:
    counts: dict = {}
    for f in sorted((run.root / "judge").glob("skipped_*.json")):
        counts[f"judge/{f.stem}"] = len(json.loads(f.read_text()))
    for kind in ("images", "parses", "judge"):
        base = run.root / kind
        for f in base.rglob("*.json") if base.exists() else []:
            if "attempts" in f.parts or f.name.endswith(".raw.json"):
                continue
            rel = f.parent.relative_to(base).as_posix()
            obj = json.loads(f.read_text())
            if not isinstance(obj, dict):
                counts[f"{kind}/{f.stem}"] = len(obj)
                continue
            ok = obj.get("ok", True)
            c = counts.setdefault(f"{kind}/{rel}", {"ok": 0, "failed": 0})
            c["ok" if ok else "failed"] += 1
    return counts


# Anthropic rejects images whose base64 is over 10 MiB. Larger pages are downscaled for that API only; the
# downscaled image's sha256 enters the config, so only those verdicts differ from the other judges' inputs.
ANTHROPIC_MAX_IMAGE_B64 = 10 * 1024 * 1024


def _fit_anthropic_image(run, cond: str, key: str, img: Path, config: dict) -> Path:
    raw_max = ANTHROPIC_MAX_IMAGE_B64 * 3 // 4 - 4096
    size = img.stat().st_size
    if size <= raw_max:
        return img
    from PIL import Image

    out = run.root / "images_downscaled" / cond / f"{key}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    src = Image.open(img)
    scale = (raw_max / size) ** 0.5 * 0.95
    # Clean and rotated verdicts share the clean image, so concurrent workers
    # write to a private file and swap it in.
    tmp = out.with_name(f"{out.stem}.{os.getpid()}.{threading.get_ident()}.tmp.png")
    while True:
        im = src.resize((max(1, int(src.width * scale)), max(1, int(src.height * scale))), Image.LANCZOS)
        im.save(tmp, format="PNG", optimize=True)
        if tmp.stat().st_size <= raw_max:
            break
        scale *= 0.9
    os.replace(tmp, out)
    config["image_downscaled"] = {
        "sha256": sha256_bytes(out.read_bytes()),
        "width": im.width,
        "height": im.height,
        "orig_width": src.width,
        "orig_height": src.height,
    }
    return out
