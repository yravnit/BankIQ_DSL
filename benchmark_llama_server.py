"""Local llama-server benchmark harness (OpenAI-compatible, JSON-schema constrained)."""

import json
import time

from pathlib import Path

from typing import Any, Dict, List, Optional

from ir_models import AssistantEnvelope
from validator import canonical_json_value, validate_envelope_consistency
from renderer import render_dsl
from prompts import PROMPT_VARIANTS
from datasets import _select_eval_subset

CANDIDATE_MODELS = [
    {
        "name": "Bonsai-27B-local-server",
        "repo_id": "local-llama-server",
        "filename": "already-loaded-by-llama-server",
        "est_vram_gb": "server-managed",
        "n_ctx": 8192,
        "chat_template_kwargs": {"enable_thinking": False},
        "notes": "Uses the already-running local llama-server; no model download or Python model loading.",
    },
]



def _apply_chat_template_kwargs(llm: Any, model_cfg: Dict[str, Any]) -> None:
    """Forward model-specific kwargs into the GGUF chat-template renderer.

    llama-cpp-python's direct create_chat_completion API does not expose
    chat_template_kwargs as a top-level argument. Its selected chat-template
    handler accepts extra kwargs, so wrap that handler for models whose cards
    document a template switch such as enable_thinking=False.
    """
    template_kwargs = model_cfg.get("chat_template_kwargs")
    if not template_kwargs:
        return

    # Prefer the embedded default Jinja chat template, which is what these
    # Qwen3.8-family GGUFs use. Fall back to the selected handler only if the
    # default template handler is not registered.
    handlers = getattr(llm, "_chat_handlers", {})
    base_handler = handlers.get("chat_template.default")
    if base_handler is None:
        base_handler = getattr(llm, "chat_handler", None)
    if base_handler is None:
        raise RuntimeError(
            f"{model_cfg['name']} requests chat_template_kwargs={template_kwargs}, "
            "but llama-cpp-python did not expose an embedded/default chat-template handler. "
            "Use a recent llama-cpp-python build with GGUF Jinja chat-template support."
        )

    def configured_handler(**handler_kwargs: Any) -> Any:
        handler_kwargs.update(template_kwargs)
        return base_handler(**handler_kwargs)

    llm.chat_handler = configured_handler


def run_colab_benchmark(
    eval_items: List[Dict[str, Any]],
    max_samples: int = 0,
    model_names: Optional[List[str]] = None,
    max_tokens: int = 0,
    n_ctx: Optional[int] = None,
    out_dir: str = "eval_data",
    verbose_model: bool = False,
    prompt_variant_names: Optional[List[str]] = None,
    temperature: float = 0.2,
    top_p: float = 0.95,
    top_k: int = 20,
    min_p: float = 0.0,
    server_url: str = "http://127.0.0.1:8080",
    api_key: str = "",
) -> None:
    """Run the unchanged evaluation/validators against a local llama-server API."""
    import urllib.request
    import urllib.error
    import pandas as pd

    base_url = server_url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    def http_json(url: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="GET" if payload is None else "POST")
        try:
            with urllib.request.urlopen(req, timeout=600) as response:
                body = response.read().decode("utf-8", errors="replace")
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} from {url}: {body[:2000]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach llama-server at {url}: {exc}. Is llama-server running?") from exc

    print(f"llama-server URL: {base_url}", flush=True)
    models_response = http_json(base_url + "/v1/models")
    model_data = models_response.get("data", [])
    server_model = model_data[0].get("id", "unknown") if model_data else "unknown"
    print(f"Server model: {server_model}", flush=True)
    print("JSON-schema-constrained output will be requested through the OpenAI-compatible API.", flush=True)
    print("VALIDATION BOUNDARY: local catalog/IR/renderer validation only; this does not call the company's IUCA parser.", flush=True)

    schema_dict = AssistantEnvelope.model_json_schema()
    subset = _select_eval_subset(eval_items, max_samples)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    chosen_prompts = prompt_variant_names or ["fewshot"]
    unknown_prompts = set(chosen_prompts) - set(PROMPT_VARIANTS)
    if unknown_prompts:
        raise ValueError("Unknown prompt variant(s): " + ", ".join(sorted(unknown_prompts)))

    print(f"\nEvaluation cases selected: {len(subset)}", flush=True)
    print(f"Prompt variants: {', '.join(chosen_prompts)}", flush=True)
    print("Starting requests; a case may take a while because Bonsai 27B is generating a complete structured IR.", flush=True)
    summary_rows = []
    all_detail_rows = []

    for prompt_variant in chosen_prompts:
        outcome_matches = system_outcome_matches = dsl_exact_matches = ir_exact_matches = 0
        unsafe_ready_predictions = json_valid_count = schema_valid_count = 0
        invalid_json_count = schema_invalid_count = generation_error_count = semantic_invalid_count = 0
        valid_ready_ir_count = predicted_ready_count = 0
        latencies: List[float] = []
        detail_rows = []
        expected_ready_total = sum(x.get("expected_outcome") == "ready" for x in subset)
        expected_negative_llm_total = sum(x.get("expected_outcome") != "ready" and not x.get("pre_llm_blocked") for x in subset)
        llm_eval_items = [x for x in subset if not x.get("pre_llm_blocked")]
        for case_index, item in enumerate(subset, start=1):
            row = {
                "Model": f"Bonsai-27B ({server_model})", "Prompt variant": prompt_variant,
                "ID": item.get("id"), "Category": item.get("category"), "Pattern ID": item.get("pattern_id"),
                "Pattern": item.get("pattern"), "Prompt": item.get("prompt", ""),
                "Expected outcome": item.get("expected_outcome"), "Predicted outcome": None,
                "Expected DSL": item.get("expected_dsl"), "Predicted DSL": None,
                "Outcome correct": False, "Exact DSL match": False, "IR exact match": False,
                "IR validation errors": None, "JSON valid": False, "Schema valid": False,
                "Finish reason": None, "Latency ms": None, "Status": "not_run", "Error": None, "Raw response": None,
            }
            if item.get("pre_llm_blocked"):
                row["Predicted outcome"] = "cannot_express (deterministic pre-LLM block)"
                row["Outcome correct"] = item.get("expected_outcome") == "cannot_express"
                row["Status"] = "deterministic_block"
                row["Schema valid"] = True
                system_outcome_matches += int(row["Outcome correct"])
                detail_rows.append(row)
                continue

            # llama.cpp server follows the OpenAI-compatible chat-completions API.
            # json_schema is preferred; if the installed server rejects this field, the error is recorded.
            payload = {
                "model": server_model,
                "messages": [
                    {"role": "system", "content": PROMPT_VARIANTS[prompt_variant]},
                    {"role": "user", "content": item["prompt"]},
                ],
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens if max_tokens > 0 else -1,
                "stream": False,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "assistant_envelope", "strict": True, "schema": schema_dict},
                },
            }
            started = time.perf_counter()
            try:
                try:
                    resp = http_json(base_url + "/v1/chat/completions", payload)
                except RuntimeError as exc:
                    # Older llama-server builds may not implement json_schema. Retry once with
                    # JSON-object mode so the benchmark remains usable, while validators still reject bad structures.
                    if "response_format" not in str(exc) and "json_schema" not in str(exc).lower() and "schema" not in str(exc).lower():
                        raise
                    print(f"[WARN] Server rejected JSON-schema mode; retrying {item['id']} with JSON-object mode.", flush=True)
                    payload["response_format"] = {"type": "json_object"}
                    resp = http_json(base_url + "/v1/chat/completions", payload)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                row["Latency ms"] = round(elapsed_ms, 1)
                latencies.append(elapsed_ms)
                choice = (resp.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                content = message.get("content") or ""
                row["Finish reason"] = choice.get("finish_reason")
                row["Raw response"] = content
                if not content.strip():
                    generation_error_count += 1
                    row["Status"] = "empty_output"
                    row["Error"] = f"Empty response; finish_reason={row['Finish reason']}"
                    detail_rows.append(row)
                    print(f"[{case_index}/{len(subset)}] {item['id']}: EMPTY RESPONSE", flush=True)
                    continue
                try:
                    parsed = json.loads(content)
                    json_valid_count += 1
                    row["JSON valid"] = True
                except json.JSONDecodeError as exc:
                    invalid_json_count += 1
                    row["Status"] = "invalid_json"
                    row["Error"] = str(exc)
                    detail_rows.append(row)
                    print(f"[{case_index}/{len(subset)}] {item['id']}: INVALID JSON ({elapsed_ms:.0f} ms)", flush=True)
                    continue
                pred_outcome = parsed.get("outcome") if isinstance(parsed, dict) else None
                row["Predicted outcome"] = pred_outcome
                if item.get("expected_outcome") != "ready" and pred_outcome == "ready":
                    unsafe_ready_predictions += 1
                try:
                    validated = AssistantEnvelope.model_validate(parsed)
                    schema_valid_count += 1
                    row["Schema valid"] = True
                    normalized = validated.model_dump(exclude_none=False)
                    pred_outcome = normalized.get("outcome")
                    row["Predicted outcome"] = pred_outcome
                    correct = pred_outcome == item.get("expected_outcome")
                    row["Outcome correct"] = correct
                    outcome_matches += int(correct)
                    system_outcome_matches += int(correct)
                    consistency_errors = validate_envelope_consistency(normalized)
                    if consistency_errors:
                        semantic_invalid_count += 1
                        row["IR validation errors"] = " | ".join(consistency_errors)
                        row["Status"] = "ir_validation_error"
                        row["Error"] = row["IR validation errors"]
                    elif pred_outcome == "ready" and normalized.get("rule_ir") is not None:
                        valid_ready_ir_count += 1
                        if item.get("expected_outcome") == "ready":
                            predicted_ir = normalized["rule_ir"]
                            if canonical_json_value(predicted_ir) == canonical_json_value(item.get("expected_ir")):
                                ir_exact_matches += 1
                                row["IR exact match"] = True
                            try:
                                pred_dsl = render_dsl(predicted_ir)
                                row["Predicted DSL"] = pred_dsl
                                if pred_dsl == item.get("expected_dsl"):
                                    dsl_exact_matches += 1
                                    row["Exact DSL match"] = True
                                row["Status"] = "ok" if row["Exact DSL match"] else "dsl_mismatch"
                            except (KeyError, TypeError, ValueError) as exc:
                                semantic_invalid_count += 1
                                row["Status"] = "ir_render_error"
                                row["Error"] = f"{type(exc).__name__}: {exc}"
                        else:
                            row["Status"] = "unsafe_ready"
                    else:
                        row["Status"] = "ok" if correct else "outcome_mismatch"
                except Exception as exc:
                    schema_invalid_count += 1
                    row["Status"] = "schema_invalid"
                    row["Error"] = f"{type(exc).__name__}: {exc}"
                detail_rows.append(row)
                print(f"[{case_index}/{len(subset)}] {item['id']}: {row['Status']} | {elapsed_ms:.0f} ms", flush=True)
            except Exception as exc:
                generation_error_count += 1
                row["Status"] = "generation_error"
                row["Error"] = f"{type(exc).__name__}: {exc}"
                detail_rows.append(row)
                print(f"[{case_index}/{len(subset)}] {item['id']}: ERROR {type(exc).__name__}: {exc}", flush=True)

            # Save after every case so a server crash doesn't lose all progress.
            pd.DataFrame(detail_rows).to_csv(out_path / "llm_benchmark_details.csv", index=False)

        attempted_total = sum(not item.get("pre_llm_blocked") for item in subset)
        predicted_ready_count = sum(r.get("Predicted outcome") == "ready" for r in detail_rows)
        ready_correct_decisions = sum(r.get("Predicted outcome") == "ready" and r.get("Expected outcome") == "ready" for r in detail_rows)
        safe_ready_exact = sum(r.get("Predicted outcome") == "ready" and r.get("Expected outcome") == "ready" and r.get("IR exact match") and not r.get("IR validation errors") for r in detail_rows)
        summary = {
            "Model": f"Bonsai-27B ({server_model})", "Prompt variant": prompt_variant, "Cases": len(subset),
            "LLM Cases": attempted_total, "Outcome Acc (%)": round(100*outcome_matches/max(1,attempted_total),1),
            "System Decision Acc incl. guards (%)": round(100*system_outcome_matches/max(1,len(subset)),1),
            "IR Exact Match (% of ready gold)": round(100*ir_exact_matches/max(1,expected_ready_total),1),
            "DSL Exact Match (% of ready gold)": round(100*dsl_exact_matches/max(1,expected_ready_total),1),
            "Valid Ready IR (%)": round(100*valid_ready_ir_count/max(1,predicted_ready_count),1),
            "Ready Decision Precision (%)": round(100*ready_correct_decisions/max(1,predicted_ready_count),1),
            "Safe Exact Ready Precision (%)": round(100*safe_ready_exact/max(1,predicted_ready_count),1),
            "Unsafe Ready Rate (% of LLM-tested negatives)": round(100*unsafe_ready_predictions/max(1,expected_negative_llm_total),1),
            "False Ready Count": unsafe_ready_predictions,
            "Valid JSON (%)": round(100*json_valid_count/max(1,attempted_total),1),
            "Schema Valid (%)": round(100*schema_valid_count/max(1,attempted_total),1),
            "Invalid JSON": invalid_json_count, "Schema Errors": schema_invalid_count,
            "Generation Errors": generation_error_count, "Semantic/IR Errors": semantic_invalid_count,
            "Avg Latency (ms)": int(sum(latencies)/max(1,len(latencies))),
        }
        summary_rows.append(summary)
        all_detail_rows.extend(detail_rows)
        pd.DataFrame(summary_rows).to_csv(out_path / "llm_leaderboard.csv", index=False)
        pd.DataFrame(all_detail_rows).to_csv(out_path / "llm_benchmark_details.csv", index=False)
        print("\n=== IUCA BONSAI 27B SERVER BENCHMARK ===", flush=True)
        print(pd.DataFrame(summary_rows).to_string(index=False), flush=True)
        print(f"\nSaved: {(out_path / 'llm_leaderboard.csv').resolve()}", flush=True)
        print(f"Saved: {(out_path / 'llm_benchmark_details.csv').resolve()}", flush=True)
        print("Reminder: benchmark DSL exactness checks the local renderer, not the private IUCA parser.", flush=True)
