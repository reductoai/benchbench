import re
from fnmatch import fnmatch
from pathlib import Path

import yaml

CATALOG_PATH = Path(__file__).with_name("catalog.yaml")


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, dict]:
    return {b["id"]: b for b in yaml.safe_load(path.read_text())["benchmarks"]}


def expand_braces(pattern: str) -> list[str]:
    m = re.search(r"\{([^{}]+)\}", pattern)
    if not m:
        return [pattern]
    head, tail = pattern[: m.start()], pattern[m.end() :]
    return [p for alt in m.group(1).split(",") for p in expand_braces(head + alt + tail)]


def match_files(files: list[str], glob: str) -> list[str]:
    pats = expand_braces(glob)
    # fnmatch's * crosses "/", so "**/" and "*/" both match any depth; require the suffix pattern to match.
    return sorted(f for f in files if any(fnmatch(f, p) or fnmatch(f, p.replace("**/", "")) for p in pats))


def stratum(path: str, regex: str | None) -> str:
    if not regex:
        return "all"
    m = re.search(regex, path)
    return m.group(1) if m else "other"
