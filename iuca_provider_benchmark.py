#!/usr/bin/env python3
"""Run the IUCA IR benchmark against provider APIs.

Current backend: NVIDIA NIM (OpenAI-compatible chat completions).

The deterministic core (catalog, IR schema, validator, renderer, prompt, fixtures)
is imported from iuca_core.py. This script only handles
transport, response parsing, scoring, and run artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = Path(r"C:\Users\yravn\Desktop\ravnit\Projects\drag\.env")
DEFAULT_NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

PILOT_CASE_IDS = [
    "sec9_01_single_condition_p1",
    "sec9_02_and_chain_p1",
    "sec9_04_list_membership_p1",
    "sec9_11_history_two_cumulative_p1",
    "sec9_12_history_with_filter_p1",
    "sec9_14_glob_match_p1",
    "sec9_15_nested_shape_c_p1",
    "neg_vague_03_missing_history_grouping",
    "neg_syntax_01_mixed_and_or",
    "neg_catalog_01_unknown_attribute",
]


def load_core():
    import iuca_core
    return iuca_core


def load_env(path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def load_cases(
    split: str, case_ids: Optional[List[str]], max_samples: int, core
) -> List[Dict[str, Any]]:
    path = ROOT / "eval_data" / f"eval_{split}.json"
    if not path.exists():
        core.generate_datasets(out_dir=str(ROOT / "eval_data"))
    cases = json.loads(path.read_text(encoding="utf-8"))
    if case_ids:
        wanted = set(case_ids)
        selected = [case for case in cases if case.get("id") in wanted]
        missing = wanted - {case.get("id") for case in selected}
        if missing:
            raise SystemExit(f"Unknown case id(s): {sorted(missing)}")
        return selected
    if max_samples and max_samples > 0:
        return core._select_eval_subset(cases, max_samples)
    return cases


def _merge_duplicate_keys(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    """Collapse duplicate JSON keys when the resolution is unambiguous.

    bolt-e4b writes a kind-specific field with its value, then repeats the same key
    as null in the null-skeleton later in the same object. JSON last-key-wins would
    erase the value. If one value is non-null and the rest are null (or all equal),
    keep it; two different non-null values are ambiguous, so reject the object.
    """
    out: Dict[str, Any] = {}
    for key, value in pairs:
        if key not in out:
            out[key] = value
            continue
        existing = out[key]
        if existing == value or value is None:
            continue
        if existing is None:
            out[key] = value
            continue
        raise ValueError(f"ambiguous duplicate key {key!r}")
    return out


def parse_json_text(text: str) -> tuple[Optional[Any], Optional[str]]:
    """Parse model output, tolerating code fences, prose, or a forgotten closing brace.

    Returns (value, mode) where mode is "exact", "extracted", "repaired", or None.
    Duplicate keys are resolved by _merge_duplicate_keys; ambiguity fails the parse.
    """
    if not text or not text.strip():
        return None, None
    raw = text.strip()
    candidates = [raw]
    stripped = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    stripped = re.sub(r"\s*```$", "", stripped)
    if stripped != raw:
        candidates.append(stripped)
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate, object_pairs_hook=_merge_duplicate_keys), (
                "exact" if candidate == raw else "extracted"
            )
        except ValueError:
            continue
    # Last resort: the model stopped before closing its braces. Brace counting is
    # naive (ignores braces inside strings); the result is flagged as repaired.
    for candidate in candidates:
        balanced = candidate + "}" * (candidate.count("{") - candidate.count("}"))
        if balanced == candidate:
            continue
        try:
            return json.loads(
                balanced, object_pairs_hook=_merge_duplicate_keys
            ), "repaired"
        except ValueError:
            continue
    return None, None


def post_json(
    url: str, payload: Dict[str, Any], api_key: str, timeout: int
) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def call_nim(
    model: str,
    messages: List[Dict[str, str]],
    api_key: str,
    url: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
    disable_thinking: bool,
    json_mode: str,
    json_schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if disable_thinking:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    if json_mode == "json_object":
        payload["response_format"] = {"type": "json_object"}
    elif json_mode == "json_schema":
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "assistant_envelope",
                "strict": True,
                "schema": json_schema,
            },
        }
    elif json_mode == "nvext":
        payload["nvext"] = {"guided_json": json_schema}
    return post_json(url, payload, api_key, timeout)


def score_case(
    core, item: Dict[str, Any], content: str, latency_ms: float, usage: Dict[str, Any]
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "id": item.get("id"),
        "category": item.get("category"),
        "pattern_id": item.get("pattern_id"),
        "expected_outcome": item.get("expected_outcome"),
        "predicted_outcome": None,
        "outcome_correct": False,
        "json_valid": False,
        "json_extracted": False,
        "json_repaired": False,
        "schema_valid": False,
        "semantic_errors": None,
        "ir_exact_match": False,
        "dsl_exact_match": False,
        "predicted_dsl": None,
        "unsafe_ready": False,
        "status": "not_run",
        "error": None,
        "latency_ms": round(latency_ms, 1),
        "prompt_tokens": (usage or {}).get("prompt_tokens"),
        "completion_tokens": (usage or {}).get("completion_tokens"),
        "total_tokens": (usage or {}).get("total_tokens"),
        "raw_response": content,
    }
    parsed, parse_mode = parse_json_text(content)
    if parsed is None:
        row["status"] = "invalid_json"
        return row
    row["json_repaired"] = parse_mode == "repaired"
    row["json_valid"] = not row["json_repaired"]
    row["json_extracted"] = parse_mode in ("extracted", "repaired")
    if parse_mode == "extracted":
        row["status"] = "json_extracted"
    elif parse_mode == "repaired":
        row["status"] = "json_repaired"

    predicted = parsed.get("outcome") if isinstance(parsed, dict) else None
    row["predicted_outcome"] = predicted
    if item.get("expected_outcome") != "ready" and predicted == "ready":
        row["unsafe_ready"] = True

    try:
        envelope = core.AssistantEnvelope.model_validate(parsed)
    except Exception as exc:
        row["status"] = "schema_invalid"
        row["error"] = f"{type(exc).__name__}: {exc}"
        return row
    row["schema_valid"] = True

    normalized = envelope.model_dump(exclude_none=False)
    row["predicted_outcome"] = normalized.get("outcome")
    row["outcome_correct"] = normalized.get("outcome") == item.get("expected_outcome")

    consistency_errors = core.validate_envelope_consistency(normalized)
    if consistency_errors:
        row["status"] = "semantic_invalid"
        row["semantic_errors"] = " | ".join(consistency_errors)
        return row

    if normalized.get("outcome") == "ready" and normalized.get("rule_ir") is not None:
        predicted_ir = normalized["rule_ir"]
        if item.get("expected_outcome") == "ready":
            try:
                if core.canonical_json_value(predicted_ir) == core.canonical_json_value(
                    item.get("expected_ir")
                ):
                    row["ir_exact_match"] = True
                row["predicted_dsl"] = core.render_dsl(predicted_ir)
                row["dsl_exact_match"] = row["predicted_dsl"] == item.get(
                    "expected_dsl"
                )
                row["status"] = "ok" if row["dsl_exact_match"] else "dsl_mismatch"
            except Exception as exc:
                row["status"] = "render_error"
                row["error"] = f"{type(exc).__name__}: {exc}"
        else:
            row["status"] = "unsafe_ready"
    else:
        row["status"] = "ok" if row["outcome_correct"] else "outcome_mismatch"
    return row


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(rows)
    ready_rows = [row for row in rows if row.get("expected_outcome") == "ready"]
    negative_rows = [row for row in rows if row.get("expected_outcome") != "ready"]
    attempted = [row for row in rows if row.get("status") != "not_run"]
    return {
        "cases": total,
        "outcome_correct": sum(1 for row in rows if row.get("outcome_correct")),
        "outcome_accuracy_pct": round(
            100 * sum(1 for row in rows if row.get("outcome_correct")) / max(1, total),
            1,
        ),
        "json_valid": sum(1 for row in rows if row.get("json_valid")),
        "json_repaired": sum(1 for row in rows if row.get("json_repaired")),
        "schema_valid": sum(1 for row in rows if row.get("schema_valid")),
        "semantic_valid": sum(
            1
            for row in rows
            if row.get("schema_valid") and not row.get("semantic_errors")
        ),
        "ready_cases": len(ready_rows),
        "ir_exact_matches": sum(1 for row in ready_rows if row.get("ir_exact_match")),
        "dsl_exact_matches": sum(1 for row in ready_rows if row.get("dsl_exact_match")),
        "negative_cases": len(negative_rows),
        "unsafe_ready": sum(1 for row in rows if row.get("unsafe_ready")),
        "prompt_tokens": sum((row.get("prompt_tokens") or 0) for row in rows),
        "completion_tokens": sum((row.get("completion_tokens") or 0) for row in rows),
        "total_tokens": sum((row.get("total_tokens") or 0) for row in rows),
        "avg_latency_ms": round(
            sum(row.get("latency_ms") or 0 for row in attempted)
            / max(1, len(attempted)),
            1,
        ),
    }


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    # Union of keys: an error row and a scored row do not carry identical fields.
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the IUCA IR benchmark against NVIDIA NIM."
    )
    parser.add_argument("--provider", choices=["nim"], default="nim")
    parser.add_argument(
        "--model",
        action="append",
        required=True,
        help="Model ID; repeat for multiple models.",
    )
    parser.add_argument("--split", choices=["dev", "holdout"], default="dev")
    parser.add_argument(
        "--case-ids",
        nargs="*",
        default=None,
        help="Explicit case IDs. Omit for a pilot/subset.",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=10,
        help="Subset size when --case-ids is omitted. 0 = full split.",
    )
    parser.add_argument(
        "--pilot", action="store_true", help="Use the fixed 10-case pilot set."
    )
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=2000)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--disable-thinking", action="store_true")
    parser.add_argument(
        "--json-mode",
        choices=["none", "json_object", "json_schema", "nvext"],
        default="none",
    )
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--nim-url", default=DEFAULT_NIM_URL)
    parser.add_argument("--out-root", default=str(ROOT / "eval_results"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Assert the response parser on canned shapes and exit.",
    )
    parser.add_argument(
        "--prompt-variant",
        default="v6",
        help="Prompt variant from the core (default v6, promoted 2026-10-26; fewshot/v2 kept for older-run reproducibility).",
    )
    args = parser.parse_args()

    if args.self_check:
        assert parse_json_text('{"a":1}') == ({"a": 1}, "exact")
        assert parse_json_text('```json\n{"a":1}\n```') == ({"a": 1}, "extracted")
        assert parse_json_text('sure: {"a":{"b":1}') == ({"a": {"b": 1}}, "repaired")
        assert parse_json_text('{"a":1,') == (None, None)
        assert parse_json_text("") == (None, None)
        # Duplicate keys: unambiguous (one non-null, or equal) collapses; ambiguity fails.
        assert parse_json_text('{"a":1,"a":null}') == ({"a": 1}, "exact")
        assert parse_json_text('{"a":null,"a":2}') == ({"a": 2}, "exact")
        assert parse_json_text('{"a":1,"a":1}') == ({"a": 1}, "exact")
        assert parse_json_text('{"a":1,"a":2}') == (None, None)
        assert parse_json_text('{"cond":{"x":"v1","y":null,"x":null}}') == (
            {"cond": {"x": "v1", "y": None}},
            "exact",
        )
        print("[OK] parse_json_text self-check passed.")
        return

    core = load_core()
    case_ids = PILOT_CASE_IDS if args.pilot else args.case_ids
    cases = load_cases(args.split, case_ids, args.max_samples, core)
    system_prompt = core.PROMPT_VARIANTS.get(args.prompt_variant)
    if system_prompt is None:
        raise SystemExit(
            f"Unknown prompt variant {args.prompt_variant!r}; choose from {sorted(core.PROMPT_VARIANTS)}"
        )
    env = load_env(Path(args.env_file))
    api_key = env.get("NVIDIA_API_KEY", "")

    print(
        f"Cases: {len(cases)} | split={args.split} | model(s)={', '.join(args.model)}"
    )
    for case in cases:
        print(f"  - {case['id']} ({case['expected_outcome']})")
    if args.dry_run:
        return
    if not api_key:
        raise SystemExit(f"NVIDIA_API_KEY not found in {args.env_file}")

    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for model in args.model:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", model)
        out_dir = Path(args.out_root) / args.provider / slug / run_stamp
        out_dir.mkdir(parents=True, exist_ok=True)
        rows: List[Dict[str, Any]] = []
        print(f"\n=== {model} ===")
        for index, case in enumerate(cases, start=1):
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": case["prompt"]},
            ]
            started = time.perf_counter()
            try:
                response = call_nim(
                    model=model,
                    messages=messages,
                    api_key=api_key,
                    url=args.nim_url,
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                    timeout=args.timeout,
                    disable_thinking=args.disable_thinking,
                    json_mode=args.json_mode,
                    json_schema=core.AssistantEnvelope.model_json_schema(),
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                choice = (response.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                content = message.get("content") or ""
                if not content.strip() and message.get("reasoning_content"):
                    content = message["reasoning_content"]
                row = score_case(
                    core, case, content, elapsed_ms, response.get("usage") or {}
                )
                row["finish_reason"] = choice.get("finish_reason")
            except urllib.error.HTTPError as exc:
                elapsed_ms = (time.perf_counter() - started) * 1000
                body = exc.read().decode("utf-8", "replace")
                row = {
                    "id": case["id"],
                    "category": case.get("category"),
                    "pattern_id": case.get("pattern_id"),
                    "expected_outcome": case.get("expected_outcome"),
                    "predicted_outcome": None,
                    "outcome_correct": False,
                    "json_valid": False,
                    "json_extracted": False,
                    "schema_valid": False,
                    "semantic_errors": None,
                    "ir_exact_match": False,
                    "dsl_exact_match": False,
                    "predicted_dsl": None,
                    "unsafe_ready": False,
                    "status": "http_error",
                    "error": f"HTTP {exc.code}: {body[:1000]}",
                    "latency_ms": round(elapsed_ms, 1),
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                    "raw_response": None,
                    "finish_reason": None,
                }
                if exc.code in (401, 403, 404):
                    rows.append(row)
                    print(
                        f"[{index}/{len(cases)}] {case['id']}: HTTP {exc.code} (stopping model)"
                    )
                    break
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - started) * 1000
                row = {
                    "id": case["id"],
                    "category": case.get("category"),
                    "pattern_id": case.get("pattern_id"),
                    "expected_outcome": case.get("expected_outcome"),
                    "predicted_outcome": None,
                    "outcome_correct": False,
                    "json_valid": False,
                    "json_extracted": False,
                    "schema_valid": False,
                    "semantic_errors": None,
                    "ir_exact_match": False,
                    "dsl_exact_match": False,
                    "predicted_dsl": None,
                    "unsafe_ready": False,
                    "status": "request_error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "latency_ms": round(elapsed_ms, 1),
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                    "raw_response": None,
                    "finish_reason": None,
                }
            rows.append(row)
            print(
                f"[{index}/{len(cases)}] {case['id']}: {row['status']} | "
                f"pred={row['predicted_outcome']} | "
                f"tokens={row['prompt_tokens']}/{row['completion_tokens']} | "
                f"{row['latency_ms']} ms"
            )

        summary = summarize(rows)
        summary.update(
            {
                "provider": args.provider,
                "model": model,
                "split": args.split,
                "temperature": args.temperature,
                "max_tokens": args.max_tokens,
                "disable_thinking": args.disable_thinking,
                "prompt_variant": args.prompt_variant,
                "json_mode": args.json_mode,
                "run_utc": run_stamp,
                "case_ids": [case["id"] for case in cases],
            }
        )
        write_csv(out_dir / "details.csv", rows)
        write_csv(out_dir / "summary.csv", [summary])
        (out_dir / "run.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        print("\nSummary:")
        print(json.dumps(summary, indent=2))
        print(f"Artifacts: {out_dir}")


if __name__ == "__main__":
    main()
