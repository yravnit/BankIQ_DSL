"""IUCA deterministic core: API surface + CLI.

Modules:
  catalog.py      documented names/sets the validator accepts
  ir_models.py    Pydantic RuleIR + AssistantEnvelope schema
  validator.py    schema expansion, semantic validation, canonicalization
  renderer.py     IR -> DSL (fixed templates)
  fixtures.py     golden seeds + negative cases (data only)
  selfcheck.py    validate_static_invariants (the one runnable check)
  datasets.py     generate_datasets + _select_eval_subset
  prompts.py      system/fewshot prompts and variants v2..v6
  benchmark_llama_server.py  local llama-server harness

Deterministic generation only; candidate rules are never verified
against the company's IUCA parser.
"""

import argparse
import os

from catalog import (
    CATALOG, COMPARATOR_SET, EVENT_SET, FUNCTION_SET, HISTORY_METRIC_SET,
    LIST_CATEGORY_SET, PARTNER_ATTRIBUTE_SET, PARTNER_PROVISIONAL_ATTRIBUTES,
    SENSITIVE_ATTRIBUTES, SENSITIVE_ATTRIBUTE_SET, STRING_TOKEN_RE,
    SUPPORTED_ATTRIBUTES, SUPPORTED_ATTRIBUTE_SET,
)
from ir_models import AssistantEnvelope, RuleIR
from validator import (
    canonical_json_value, expand_envelope_for_examples, expand_ir_for_schema,
    validate_envelope_consistency, validate_rule_ir,
)
from renderer import render_condition, render_current_block, render_dsl, render_history_block
from fixtures import GOLDEN_SEEDS, NEGATIVE_AND_EDGE_CASES
from selfcheck import validate_static_invariants
from datasets import RANDOM_SEED, generate_datasets, _select_eval_subset
from prompts import (
    PROMPT_TRAINING_EXAMPLES, PROMPT_VARIANTS, SYSTEM_PROMPT,
    build_fewshot_prompt, build_fewshot_prompt_v2, build_pdf_examples_prompt,
    build_system_prompt,
)
from benchmark_llama_server import CANDIDATE_MODELS, run_colab_benchmark

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate IUCA fixtures and benchmark a running local llama-server."
    )
    parser.add_argument("--benchmark", action="store_true", help="Run model benchmarks after generating fixtures.")
    parser.add_argument("--max-samples", type=int, default=0,
                        help="Cases per model/prompt pair; 0 means the full selected split (default).")
    parser.add_argument("--models", nargs="*", default=None, choices=[cfg["name"] for cfg in CANDIDATE_MODELS],
                        help="Optional candidate model name(s). This single-model version only runs Bonsai-27B-Q1_0.")
    parser.add_argument("--prompt-variants", nargs="+", default=["v6"],
                        choices=list(PROMPT_VARIANTS), help="Default is v6 (2026-10-26 promotion). fewshot/v2 kept for reproducing earlier runs; thinking is disabled during JSON-schema generation.")
    parser.add_argument("--max-tokens", type=int, default=0,
                        help="Generation token cap. 0 (default) means no separate cap; generation stops at EOS or n_ctx. This is not infinite context.")
    parser.add_argument("--n-ctx", type=int, default=None,
                        help="Override all model context sizes. Defaults to 4096 for Bonsai; larger contexts increase memory use and may OOM.")
    parser.add_argument("--temperature", type=float, default=0.6,
                        help="Sampling temperature (default: 0.6; preserved from v7 for a controlled comparison).")
    parser.add_argument("--top-p", type=float, default=0.95,
                        help="Nucleus sampling p (default: 0.95).")
    parser.add_argument("--top-k", type=int, default=20,
                        help="Top-k sampling (default: 20).")
    parser.add_argument("--min-p", type=float, default=0.0,
                        help="Min-p sampling (default: 0.0).")
    parser.add_argument("--out-dir", default="eval_data", help="Output directory (default: eval_data).")
    parser.add_argument("--split", choices=["dev", "holdout", "all"], default="dev",
                        help="Which generated cases to benchmark (default: dev). Run holdout only after prompt/model choices are frozen; holdout measures unseen phrasings of documented patterns, not unseen grammar constructs.")
    parser.add_argument("--verbose-model", action="store_true",
                        help="Print llama.cpp initialization logs for the first selected model.")
    parser.add_argument("--server-url", default="http://127.0.0.1:8080", help="Base URL of the running llama-server (default: http://127.0.0.1:8080).")
    parser.add_argument("--api-key", default=os.environ.get("LLAMA_SERVER_API_KEY", ""), help="Optional llama-server API key; can also use LLAMA_SERVER_API_KEY env var.")
    args = parser.parse_args()

    datasets = generate_datasets(args.out_dir)
    if not args.benchmark:
        print("Fixtures generated. To run the benchmark, add --benchmark to this command.")
        return

    if args.split == "dev":
        eval_items = datasets["dev"]
    elif args.split == "holdout":
        eval_items = datasets["holdout"]
    else:
        eval_items = datasets["dev"] + datasets["holdout"]

    run_colab_benchmark(
        eval_items,
        max_samples=args.max_samples,
        model_names=args.models,
        max_tokens=args.max_tokens,
        n_ctx=args.n_ctx,
        out_dir=args.out_dir,
        verbose_model=args.verbose_model,
        prompt_variant_names=args.prompt_variants,
        temperature=args.temperature,
        top_p=args.top_p,
        top_k=args.top_k,
        min_p=args.min_p,
        server_url=args.server_url,
        api_key=args.api_key,
    )


if __name__ == "__main__":
    main()
