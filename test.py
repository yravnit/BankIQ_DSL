#!/usr/bin/env python3
"""Live demo of the IUCA rule assistant pipeline, every step visible on screen.

    python test.py "your rule request in quotes"

Plain-language request -> LLM emits typed IR -> semantic validation -> candidate
DSL. Uses nvidia/nemotron-3.5-bolt-e4b on NIM directly, with the same v6 prompt
settings that won the frozen benchmark (100% on its 15-case run).

When the model answers needs_clarification, the questions are printed, you
answer in this terminal, and your answers continue the SAME conversation
(transcript + answers go to the next model call). Answers pass the same local
privacy gate before being sent. Demo budget: 3 model calls per execution.
If a response is unparseable JSON, one transport-level retry is attempted
(ask the model to re-emit valid JSON); schema/semantic failures stop the demo.

Built from documented patterns - not verified against the IUCA engine.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import time
import urllib.error
from pathlib import Path

from iuca_provider_benchmark import (
    DEFAULT_ENV_PATH,
    DEFAULT_NIM_URL,
    call_nim,
    load_core,
    load_env,
    parse_json_text,
)

MODEL = "nvidia/nemotron-3.5-bolt-e4b"
PROMPT_VARIANT = "v6"
MAX_MODEL_CALLS = 3  # ponytail: demo budget; a real UI loops until resolved

PARSE_NUDGE = (
    "Your previous response was not parseable JSON. Reply again with corrected, "
    "complete JSON only, matching the schema exactly."
)

# ponytail: crude heuristic only — real pre-LLM detector is Phase 1 (progress.md §7).
PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
DIGIT_RUN_RE = re.compile(r"\b(\d[\s-]?){11,16}\b")


def step(n: int, round_no: int, label: str) -> None:
    print(f"\n[STEP {n}/7 · round {round_no}] {label}")
    print("-" * 70)


def privacy_gate(text: str) -> None:
    if not (PAN_RE.search(text) or DIGIT_RUN_RE.search(text)):
        print("OK — no identifier-like digits found; safe to send.")
        return
    print("BLOCKED: looks like a personal identifier (PAN/Aadhaar/long number).")
    print("v1 never sends these to the provider. Refer to the field name instead")
    print('(e.g. "the pan" as an attribute), never the actual value.')
    raise SystemExit(3)


def run_turn(
    core, messages: list, user_text: str, round_no: int, parse_retried: bool = False
) -> dict:
    """Privacy-check user_text, append it, call NIM, run the ladder; print steps 1-6."""
    label = "PARSE RETRY (transport fix, not rule logic)" if parse_retried else (
        "REQUEST" if round_no == 1 else "CLARIFICATION ANSWER"
    )
    step(1, round_no, label)
    print(user_text)

    step(2, round_no, "PRIVACY GATE (local, before anything leaves this machine)")
    privacy_gate(user_text)

    messages.append({"role": "user", "content": user_text})
    step(3, round_no, f"PROMPT (variant {PROMPT_VARIANT}, from the documented catalog)")
    print(f"system prompt: {len(messages[0]['content'])} chars + {len(messages) - 1} conversation turn(s)")

    api_key = load_env(DEFAULT_ENV_PATH).get("NVIDIA_API_KEY", "")
    if not api_key:
        raise SystemExit(f"NVIDIA_API_KEY not found in {DEFAULT_ENV_PATH}")

    step(4, round_no, f"NIM CALL -> {MODEL} (temperature=0.0, max_tokens=2000)")
    started = time.perf_counter()
    try:
        response = call_nim(
            model=MODEL,
            messages=messages,
            api_key=api_key,
            url=DEFAULT_NIM_URL,
            temperature=0.0,
            max_tokens=2000,
            timeout=300,
            disable_thinking=True,
            json_mode="none",
        )
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:800]}")
        raise SystemExit(4) from exc
    elapsed = (time.perf_counter() - started) * 1000
    choice = (response.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content") or ""
    usage = response.get("usage") or {}
    print(
        f"HTTP 200 in {elapsed / 1000:.1f}s | finish={choice.get('finish_reason')}"
        f" | tokens {usage.get('prompt_tokens')} prompt / {usage.get('completion_tokens')} completion"
    )

    step(5, round_no, "RAW MODEL RESPONSE (only JSON is ever emitted)")
    print(content if content.strip() else "(empty response)")
    if not content.strip():
        raise SystemExit(5)
    messages.append({"role": "assistant", "content": content})

    step(6, round_no, "VALIDATION LADDER (tolerant parse -> schema -> semantics)")
    parsed, parse_mode = parse_json_text(content)
    if parsed is None:
        saved = Path(tempfile.gettempdir()) / "iuca_last_bad_response.json"
        saved.write_text(content, encoding="utf-8")
        print(f"FAIL: output is not parseable JSON — model failure, nothing rendered.")
        print(f"(raw response saved for diagnosis: {saved})")
        if not parse_retried:
            print("RETRYING: same conversation, asking the model to re-emit valid JSON…")
            messages.append({"role": "user", "content": PARSE_NUDGE})
            return run_turn(core, messages, PARSE_NUDGE, round_no, parse_retried=True)
        raise SystemExit(6)
    print(f"1. parsed OK (mode={parse_mode})")
    try:
        envelope = core.AssistantEnvelope.model_validate(parsed)
    except Exception as exc:
        print(f"2. SCHEMA INVALID: {exc}")
        print("   (every IR key must be explicitly present; omissions are not 'null')")
        raise SystemExit(6) from exc
    normalized = envelope.model_dump(exclude_none=False)
    print("2. schema valid (AssistantEnvelope)")
    errors = core.validate_envelope_consistency(normalized)
    if errors:
        print("3. SEMANTIC ERRORS:")
        for e in errors:
            print(f"     - {e}")
        raise SystemExit(7)
    print("3. semantically valid against the documented catalog")
    return normalized


def ask_user(questions: list) -> str:
    print("\nThe model needs more information. Answer each question")
    print("(blank answer or Ctrl+C cancels the demo):")
    answers = []
    try:
        for i, q in enumerate(questions, 1):
            print(f"  Q{i}. {q}")
            answer = input("       answer: ").strip()
            if not answer:
                print("\nNo answer given — demo ended. Rerun with a precise request.")
                raise SystemExit(8)
            answers.append(answer)
    except (EOFError, KeyboardInterrupt):
        print("\nInput closed — demo ended.")
        raise SystemExit(8) from None
    return "Clarification answers:\n" + "\n".join(
        f"{i}) {answer}" for i, answer in enumerate(answers, 1)
    )


def show_result(round_no: int, normalized: dict, core) -> None:
    outcome = normalized["outcome"]
    step(7, round_no, f"RESULT (outcome = {outcome})")
    if outcome != "ready":
        if normalized.get("unrepresentable_reason"):
            print(f"unrepresentable_reason: {normalized['unrepresentable_reason']}")
        for q in normalized.get("clarification_questions") or []:
            print(f"clarification: {q}")
        if outcome == "needs_clarification" and not (
            normalized.get("clarification_questions") or []
        ):
            print("The model asked for information but listed no questions.")
        print("No DSL rendered — only 'ready' outcomes produce rules.")
        return
    ir = normalized["rule_ir"]
    print("IR (validated internal representation):")
    print(json.dumps(ir, indent=2))
    dsl = core.render_dsl(ir)
    print("\nCANDIDATE RULE (DSL):")
    print(f"  {dsl}")
    print(
        "\nBuilt from documented patterns — not verified against the IUCA engine.\n"
        "Copy for review only: a human must check this and pass it through the\n"
        "company rule screen, whose parser is the final syntax check."
    )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # em dashes/§ on Windows consoles
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("Usage: python test.py \"<plain-language rule request>\"")
        print('e.g.   python test.py "block transaction if the amount is high"')
        raise SystemExit(2)

    core = load_core()
    if PROMPT_VARIANT not in core.PROMPT_VARIANTS:
        raise SystemExit(
            f"Unknown prompt variant {PROMPT_VARIANT!r}; choose from {sorted(core.PROMPT_VARIANTS)}"
        )
    messages = [{"role": "system", "content": core.PROMPT_VARIANTS[PROMPT_VARIANT]}]

    for round_no in range(1, MAX_MODEL_CALLS + 1):
        user_turn = sys.argv[1].strip() if round_no == 1 else None
        if round_no > 1:
            print(f"\n{'=' * 70}\nROUND {round_no} — same conversation, answers appended")
            user_turn = ask_user(normalized.get("clarification_questions") or [])
        normalized = run_turn(core, messages, user_turn, round_no)
        show_result(round_no, normalized, core)

        outcome = normalized["outcome"]
        if outcome != "needs_clarification":
            return
        if round_no == MAX_MODEL_CALLS:
            print(f"\nDemo budget reached ({MAX_MODEL_CALLS} model calls).")
            return


if __name__ == "__main__":
    main()
