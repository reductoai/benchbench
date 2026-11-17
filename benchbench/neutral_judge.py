"""Count visible content errors under blind labels and derive scores from weighted counts."""

import base64
import hashlib
import json
import time
import urllib.error
import urllib.request

PROMPT_VERSION = "neutral-count-v1"

PROMPT = """You are checking text extractions of one document page against the page image.

Each extraction below has a label. For each extraction, compare it with what is visibly printed on the page
and count errors in these units:
- word: a word, number or symbol that is wrong, missing, or not on the page.
- cell: a table cell whose content is wrong, missing, invented, or placed in the wrong row or column.
- formula: a mathematical expression that is wrong, missing, or invented.
- order: a block of text placed so that the reading order of the page is broken.

Rules:
- Judge only content that is visible on the page image. Anything not visible on the page is invented.
- Ignore formatting: Markdown vs HTML tables, heading levels, bold or italic, line breaks, image placeholders.
- Do not reward or penalise descriptions of pictures or charts; leave them out of every count.
- Count each error once, in the unit that fits it best.
- An empty extraction misses everything on the page: count every visible word, cell and formula as missing.

Return JSON only: {"results": [{"label": "...", "word": n, "cell": n, "formula": n, "order": n,
"notes": "one short sentence"}]} with one entry per label: LABELS.

EXTRACTIONS
"""


def blind_labels(page_id: str, presets: list[str]) -> dict[str, str]:
    """label -> preset. Order is a hash of page and preset, so no preset is always first."""
    order = sorted(presets, key=lambda s: hashlib.sha256(f"{page_id}:{s}".encode()).hexdigest())
    return {f"Extraction {chr(65 + i)}": s for i, s in enumerate(order)}


def score_from_counts(c: dict) -> float:
    """10 for no errors, falling with the weighted error count on a log scale; floor 1."""
    import math

    weighted = c.get("word", 0) + 2 * c.get("cell", 0) + 3 * c.get("formula", 0) + 5 * c.get("order", 0)
    return max(1.0, 10.0 - 2.0 * math.log2(1 + weighted))


def judge_page(
    page_id: str,
    image_png: bytes,
    markdown_by_preset: dict[str, str],
    model: str,
    base_url: str,
    api_key: str,
    effort: str = "medium",
    retries: int = 6,
    image_detail: str = "high",
) -> dict:
    labels = blind_labels(page_id, list(markdown_by_preset))
    sections = "\n\n".join(
        f"## {lab}\n\n````text\n{markdown_by_preset[s]}\n````" for lab, s in labels.items()
    )
    body = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT.replace("LABELS", ", ".join(labels)) + sections},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64," + base64.b64encode(image_png).decode(),
                            "detail": image_detail,
                        },
                    },
                ],
            }
        ],
    }
    if effort:
        body["reasoning_effort"] = effort
    started = time.time()
    url = f"{base_url.rstrip('/')}/chat/completions"
    data = _post(url, body, api_key, retries)
    logged = json.loads(json.dumps(body))
    logged["messages"][0]["content"][1]["image_url"]["url"] = {
        "sha256": hashlib.sha256(image_png).hexdigest(),
        "bytes": len(image_png),
    }
    exchange = {"url": url, "request": logged, "response": data}
    parsed = json.loads(data["choices"][0]["message"]["content"])
    by_label = {r["label"]: r for r in parsed.get("results", [])}
    verdicts = []
    for lab, s in labels.items():
        r = by_label.get(lab)
        if r is None:
            raise ValueError(f"judge omitted {lab}")
        counts = {k: int(r.get(k, 0)) for k in ("word", "cell", "formula", "order")}
        verdicts.append(
            {
                "presetId": s,
                "score": score_from_counts(counts),
                "counts": counts,
                "reasoning": r.get("notes", ""),
                "errors": [],
            }
        )
    return {
        "ok": True,
        "judgeVersion": PROMPT_VERSION,
        "verdicts": verdicts,
        "usage": [{"model": data.get("model", model), "usage": data.get("usage")}],
        "latencyMs": int((time.time() - started) * 1000),
        "exchanges": [exchange],
    }


def _post(url: str, body: dict, key: str, retries: int) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code not in (408, 409, 429, 500, 502, 503, 504) or attempt == retries - 1:
                raise RuntimeError(f"judge HTTP {e.code}: {e.read()[:300]!r}") from e
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
        time.sleep(min(120, 5 * 2**attempt))
    raise RuntimeError("unreachable")
