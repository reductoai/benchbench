"""PAIR with `compare-v4`'s output format but almost none of its prompt.

`compare-v4` is ~2,200 words of rubric. This keeps its exact structured output (page features, per-parse
errors with severity and category, reasoning, 1-10 score) and replaces the rubric with one sentence, so a
score change against the primary isolates the rubric text. Same call shape, labels and clean page image.
"""

import base64
import hashlib
import json
import time

from .neutral_judge import _post

PROMPT_VERSION = "terse-v1"

PROMPT = "Compare these parses of the document page against the page image. List each parse's errors and score it from 1 to 10.\n\n"  # noqa: E501

CATEGORIES = [
    "content_omission",
    "content_hallucination",
    "text_corruption",
    "generation_repetition_loop",
    "reading_order",
    "table_structure",
    "table_content",
    "field_association_error",
    "checkbox_state_error",
    "watermark",
    "figure_precision",
    "figure_recall",
    "other",
]


def response_format(labels: list[str]) -> dict:
    error = {
        "type": "object",
        "additionalProperties": False,
        "required": ["severity", "category", "visual_region_type", "location_hint", "description"],
        "properties": {
            "severity": {"type": "string", "enum": ["high", "low", "figure_error"]},
            "category": {"type": "string", "enum": CATEGORIES},
            "visual_region_type": {"type": "string"},
            "location_hint": {"type": "string"},
            "description": {"type": "string"},
        },
    }
    evaluation = {
        "type": "object",
        "additionalProperties": False,
        "required": ["label", "errors", "reasoning", "score"],
        "properties": {
            "label": {"type": "string", "enum": labels},
            "errors": {"type": "array", "items": error},
            "reasoning": {"type": "string"},
            "score": {"type": "integer", "minimum": 1, "maximum": 10},
        },
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "page_comparison",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["page_features", "evaluations"],
                "properties": {
                    "page_features": {"type": "array", "items": {"type": "string"}},
                    "evaluations": {"type": "array", "items": evaluation},
                },
            },
        },
    }


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
        "response_format": response_format(list(labels)),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT + sections},
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
    by_label = {r.get("label"): r for r in parsed.get("evaluations", [])}
    verdicts = []
    for lab, s in labels.items():
        r = by_label.get(lab)
        if r is None or r.get("score") is None:
            raise ValueError(f"judge omitted {lab}")
        verdicts.append(
            {
                "presetId": s,
                "score": float(r["score"]),
                "reasoning": r.get("reasoning", ""),
                "errors": r.get("errors", []),
            }
        )
    return {
        "ok": True,
        "judgeVersion": PROMPT_VERSION,
        "verdicts": verdicts,
        "pageFeatures": parsed.get("page_features", []),
        "usage": [{"model": data.get("model", model), "usage": data.get("usage")}],
        "latencyMs": int((time.time() - started) * 1000),
        "exchanges": [{"url": url, "request": logged, "response": data}],
    }
