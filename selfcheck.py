"""validate_static_invariants: golden-IR validator, negative guards, prompt-leakage checks."""

import copy

from validator import validate_rule_ir
from fixtures import GOLDEN_SEEDS, NEGATIVE_AND_EDGE_CASES
from prompts import PROMPT_TRAINING_EXAMPLES

def validate_static_invariants() -> None:
    """Checks golden IR/renderer consistency, invalid-IR guards, and prompt leakage."""
    for seed in GOLDEN_SEEDS:
        errors = validate_rule_ir(seed["expected_ir"])
        if errors:
            raise AssertionError(f"Golden fixture {seed['id']} fails v1 semantic validator: {errors}")

    # Invalid structures must be rejected by deterministic code, independent of any model.
    bad_cases = []
    bad = copy.deepcopy(GOLDEN_SEEDS[0]["expected_ir"])
    bad["current"]["conditions"][0]["attribute"] = "cibilScore"
    bad_cases.append(("unknown attribute", bad))
    bad = copy.deepcopy(GOLDEN_SEEDS[0]["expected_ir"])
    bad["current"]["conditions"][0]["value"] = {"type": "STRING", "value": "Uttar Pradesh"}
    bad_cases.append(("space in quoted value", bad))
    bad = copy.deepcopy(GOLDEN_SEEDS[0]["expected_ir"])
    bad.pop("current", None)
    bad_cases.append(("missing required shape block", bad))
    bad = copy.deepcopy(GOLDEN_SEEDS[11]["expected_ir"])
    bad["history"].pop("grouping", None)
    bad_cases.append(("history filter missing grouping", bad))
    bad = copy.deepcopy(GOLDEN_SEEDS[0]["expected_ir"])
    bad["current"]["conditions"][0]["attribute"] = "attribute1"
    bad_cases.append(("unmapped partner slot", bad))
    bad = copy.deepcopy(GOLDEN_SEEDS[0]["expected_ir"])
    bad["current"]["conditions"][0]["attribute"] = "pan"
    bad_cases.append(("sensitive identifier", bad))
    bad = copy.deepcopy(GOLDEN_SEEDS[0]["expected_ir"])
    bad["current"]["conditions"].append(copy.deepcopy(bad["current"]["conditions"][0]))
    bad["current"]["combinator"] = None
    bad_cases.append(("multiple conditions without combinator", bad))
    for name, bad_ir in bad_cases:
        if not validate_rule_ir(bad_ir):
            raise AssertionError(f"Semantic validator incorrectly accepted negative IR fixture: {name}")

    # The few-shot prompts must not contain exact evaluation prompts. Compare against
    # all paraphrases and negatives, not just the refusal cases.
    eval_strings = {
        str(text).strip().lower()
        for seed in GOLDEN_SEEDS for text in seed.get("paraphrases", [])
    }
    eval_strings.update(str(item.get("prompt", "")).strip().lower() for item in NEGATIVE_AND_EDGE_CASES)
    fewshot_examples = {
        str(request).strip().lower()
        for request, seed_id in PROMPT_TRAINING_EXAMPLES
        if seed_id in {
            "sec9_02_and_chain", "sec9_04_list_membership", "sec9_05_list_count",
            "sec9_06_list_amount", "sec9_08_multiply_by_number",
            "sec9_09_multiply_by_percentage", "sec9_10_history_simple_count",
            "sec9_11_history_two_cumulative", "sec9_12_history_with_filter",
            "sec9_14_glob_match", "sec9_15_nested_shape_c",
        }
    }
    collisions = eval_strings.intersection(fewshot_examples)
    if collisions:
        raise AssertionError(f"Few-shot prompt text overlaps evaluation prompts: {sorted(collisions)}")
    training_examples = {request.strip().lower() for request, _ in PROMPT_TRAINING_EXAMPLES}
    training_collisions = eval_strings.intersection(training_examples)
    if training_collisions:
        raise AssertionError(f"Full-example prompt text overlaps evaluation prompts: {sorted(training_collisions)}")
    print(f"[OK] {len(GOLDEN_SEEDS)} gold IR fixtures and {len(bad_cases)} negative IR guard tests passed.")
