"""Show the page and blind parses, ask which is better, and request a 1-10 score per parse.

The prompt contains the question and output format without a rubric. It uses one call per page,
all parses under the primary's `parse_a..h` labels, and the clean page image.
"""

import base64
import hashlib
import json
import time

from .neutral_judge import _post

PROMPT_VERSION = "minimal-v1"

PROMPT = """Here is a document page image and several parses of it. Which parse is better? Score each parse from 1 to 10.

Return JSON only: {"results": [{"label": "...", "score": n}]} with one entry per label: LABELS.

"""  # noqa: E501


def judge_page(
    labels: dict[str, str],
    image_png: bytes,
    markdown_by_preset: dict[str, str],
    model: str,
    base_url: str,
    api_key: str,
    effort: str = "medium",
    retries: int = 6,
    image_detail: str = "high",
) -> dict:
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
    parsed = json.loads(data["choices"][0]["message"]["content"])
    by_label = {r.get("label"): r for r in parsed.get("results", [])}
    verdicts = []
    for lab, s in labels.items():
        r = by_label.get(lab)
        if r is None or r.get("score") is None:
            raise ValueError(f"judge omitted {lab}")
        verdicts.append({"presetId": s, "score": float(r["score"]), "reasoning": "", "errors": []})
    return {
        "ok": True,
        "judgeVersion": PROMPT_VERSION,
        "verdicts": verdicts,
        "usage": [{"model": data.get("model", model), "usage": data.get("usage")}],
        "latencyMs": int((time.time() - started) * 1000),
        "exchanges": [{"url": url, "request": logged, "response": data}],
    }
