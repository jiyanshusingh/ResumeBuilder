#!/usr/bin/env python3
"""
AI Bullet Enhancement Module

Rewrites weak resume bullets into strong, action-oriented, metric-driven ones.

Two enhancement paths:
  1. LLM (preferred): calls a local Ollama model (e.g. gemma2:2b / llama3.2) to
     rewrite weak bullets. Uses stdlib urllib (no hard dependency on requests).
  2. Rule-based fallback: when Ollama is unavailable, applies deterministic
     rewrites (strong action verbs, metric guidance) so the feature never errors.
"""

import json
import re
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

OLLAMA_BASE = "http://localhost:11434"

# Weak / passive verb-start phrases that trigger "weak bullet" detection.
WEAK_LEADINS = [
    "responsible for",
    "responsible to",
    "worked on",
    "worked with",
    "worked at",
    "assisted with",
    "assisted in",
    "helped with",
    "helped",
    "was responsible",
    "was in charge",
    "was part of",
    "involved in",
    "participated in",
    "tasked with",
    "had to",
    "needed to",
    "handled",
    "supported",
    "i was",
    "i am",
]

# Strong action verbs (from ats_scorer vocabulary, extended).
STRONG_VERBS = [
    "managed",
    "led",
    "built",
    "created",
    "developed",
    "designed",
    "implemented",
    "deployed",
    "optimized",
    "improved",
    "increased",
    "reduced",
    "launched",
    "engineered",
    "analyzed",
    "established",
    "generated",
    "initiated",
    "coordinated",
    "executed",
    "produced",
    "supervised",
    "trained",
    "transformed",
    "converted",
    "delivered",
    "automated",
    "architected",
    "streamlined",
    "scaled",
    "drove",
    "spearheaded",
    "accelerated",
    "modernized",
    "expanded",
    "owned",
]

# Lead-in phrase -> strong replacement verb.
PHRASE_TO_VERB = [
    ("responsible for", "owned"),
    ("worked with", "collaborated with"),
    ("worked on", "drove"),
    ("worked at", "contributed to"),
    ("assisted with", "supported"),
    ("assisted in", "supported"),
    ("helped with", "enabled"),
    ("helped", "enabled"),
    ("was responsible for", "owned"),
    ("was in charge of", "directed"),
    ("in charge of", "directed"),
    ("involved in", "contributed to"),
    ("participated in", "contributed to"),
    ("tasked with", "drove"),
    ("had to", "delivered"),
    ("needed to", "developed to"),
    ("handled", "managed"),
]

METRIC_RE = re.compile(
    r"[\d]+(?:,\d{3})*(?:\.\d+)?\s*[%Kk+]+"
    r"|[₹$€£]\s?[\d,]+(?:\.\d+)?[KkMm]?"
    r"|\b\d+(?:,\d{3})+\b"
    r"|\b\d+k\b"
)


def _has_strong_lead(bullet: str) -> bool:
    """Return True if the bullet opens with a strong action verb."""
    m = re.match(r"^\s*([A-Za-z]+)\b", (bullet or "").strip())
    if not m:
        return False
    first = m.group(1).lower()
    # strip trailing 'ed'/'ing' for matching
    return (
        first in STRONG_VERBS
        or (first.endswith("ed") and first[:-2] in STRONG_VERBS)
        or (first.endswith("ing") and first[:-3] in STRONG_VERBS)
    )


def _match_weak_leadin(bullet: str) -> Optional[str]:
    """Return the weak lead-in phrase found at the start, if any."""
    lower = bullet.lower().strip()
    for phrase in WEAK_LEADINS:
        if lower.startswith(phrase):
            return phrase
    return None


def detect_weak_bullet(bullet: str) -> Dict[str, Any]:
    """
    Classify a bullet as weak or strong.
    Returns an info dict: {is_weak, has_metric, has_strong_lead, reasons}.
    """
    bullet = (bullet or "").strip()
    if not bullet:
        return {
            "is_weak": True,
            "has_metric": False,
            "has_strong_lead": False,
            "reasons": ["empty bullet"],
        }

    has_metric = bool(METRIC_RE.search(bullet))
    has_strong = _has_strong_lead(bullet)
    weak_leadin = _match_weak_leadin(bullet)

    reasons = []
    if weak_leadin:
        reasons.append("weak lead-in ('%s')" % weak_leadin)
    elif not has_strong:
        reasons.append("does not start with a strong action verb")
    if not has_metric:
        reasons.append("no quantified metric")

    is_weak = weak_leadin is not None or not has_strong or not has_metric
    return {
        "is_weak": is_weak,
        "has_metric": has_metric,
        "has_strong_lead": has_strong,
        "reasons": reasons,
    }


def _normalize(bullet: str) -> str:
    """Deterministic rewrite: strong verb lead + metric guidance."""
    b = (bullet or "").strip().rstrip(".")
    if not b:
        return b

    # 1) Replace a detected weak lead-in with a strong verb.
    changed = False
    leadin = _match_weak_leadin(b)
    for phrase, verb in PHRASE_TO_VERB:
        if re.search(rf"^\s*{re.escape(phrase)}\b", b.lower(), flags=re.IGNORECASE):
            rest = re.sub(
                rf"^\s*{re.escape(phrase)}\b", "", b, count=1, flags=re.IGNORECASE
            ).lstrip()
            rest = re.sub(r"^(on|with|and|the)\s+", "", rest)
            b = f"{verb} {rest}"
            changed = True
            break

    if not changed and leadin:
        # Known weak lead-in but no strong mapping: strip it and prepend a verb.
        rest = re.sub(
            rf"^\s*{re.escape(leadin)}\b", "", b, count=1, flags=re.IGNORECASE
        ).lstrip()
        rest = re.sub(r"^(on|with|and|the|for)\s+", "", rest)
        b = f"Drove {rest}"
        changed = True

    if not changed and not _has_strong_lead(b):
        b = "Drove " + b[0].lower() + b[1:]

    # 2) Capitalize.
    b = b[0].upper() + b[1:]

    # 3) Metric guidance.
    if not METRIC_RE.search(b):
        b = b.rstrip(".") + " [add a measurable metric: %, $, # of items]"
    return b


def ollama_available() -> bool:
    """Check whether a local Ollama server is reachable."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def enhance_with_llm(bullet: str, model: str = "gemma2:2b") -> Optional[str]:
    """Rewrite a single bullet using Ollama. Returns None on any failure."""
    prompt = (
        "Rewrite the following weak resume bullet into a strong, action-oriented, "
        "quantified achievement. Keep it one sentence, past tense, start with a strong "
        "action verb, and include a specific metric. If no metric exists, keep a "
        "[metric] placeholder. Output ONLY the rewritten bullet.\n\n"
        "Bullet: {bullet}".format(bullet=bullet)
    )
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": 120},
        }
    ).encode()

    req = urllib.request.Request(
        f"{OLLAMA_BASE}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return (data.get("response", "") or "").strip() or None
    except Exception:
        return None


def enhance_bullets(
    bullets: List[str], use_llm: bool = True, model: str = "gemma2:2b"
) -> Dict[str, Any]:
    """
    Enhance a list of resume bullets.

    Returns {"results": [{original, improved, is_weak, method, reasons}],
             "used_llm": bool, "summary": str}
    """
    llm_ready = use_llm and ollama_available()
    results: List[Dict[str, Any]] = []

    for bullet in bullets:
        bullet = (bullet or "").strip()
        info = detect_weak_bullet(bullet)

        if not info["is_weak"]:
            results.append(
                {
                    "original": bullet,
                    "improved": bullet,
                    "is_weak": False,
                    "method": "unchanged",
                    "reasons": [],
                }
            )
            continue

        improved = None
        method = "rule-based"
        if llm_ready:
            candidate = enhance_with_llm(bullet, model)
            if candidate:
                improved = candidate.strip().strip('"')
                method = "ollama"
        if not improved:
            improved = _normalize(bullet)
            method = "rule-based"

        results.append(
            {
                "original": bullet,
                "improved": improved,
                "is_weak": True,
                "method": method,
                "reasons": info["reasons"],
            }
        )

    weak_count = sum(1 for r in results if r["is_weak"])
    engine = (
        "Ollama local LLM" if llm_ready else "rule-based fallback (Ollama unavailable)"
    )
    summary = (
        f"Processed {len(bullets)} bullet(s). Enhanced {weak_count} weak "
        f"bullet(s) using {engine}."
    )
    return {"results": results, "used_llm": llm_ready, "summary": summary}


def format_enhancement_report(payload: Dict[str, Any]) -> str:
    """Render enhancement results for the UI."""
    lines = ["=" * 60, "BULLET ENHANCEMENT", "=" * 60, payload.get("summary", "")]
    for item in payload.get("results", []):
        if item["method"] == "unchanged":
            lines.append("\n• (already strong) %s" % item["original"])
            continue
        lines.append("\n• Original: %s" % item["original"])
        lines.append("  Enhanced: %s  [via %s]" % (item["improved"], item["method"]))
        if item.get("reasons"):
            lines.append("  Flags:    %s" % "; ".join(item["reasons"]))
    return "\n".join(lines)
