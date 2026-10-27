"""Semantic validation: coerce, validate IR against the catalog, canonicalize for equality."""

import copy
import json
import math

from typing import Any, Dict, List

from pydantic import ValidationError

from catalog import (
    CATALOG, COMPARATOR_SET, EVENT_SET, FUNCTION_SET, HISTORY_METRIC_SET,
    LIST_CATEGORY_SET, PARTNER_ATTRIBUTE_SET, SENSITIVE_ATTRIBUTE_SET,
    STRING_TOKEN_RE, SUPPORTED_ATTRIBUTE_SET,
)
from ir_models import RuleIR

def _check_string_token(value: Any, path: str, errors: List[str]) -> None:
    if not isinstance(value, str):
        errors.append(f"{path} must be a string token.")
        return
    if " " in value:
        errors.append(f"{path} contains a space; the PDF says quoted strings cannot contain spaces.")
    if not STRING_TOKEN_RE.fullmatch(value):
        errors.append(f"{path} contains characters outside the v1 allow-list [A-Z, a-z, 0-9, _, ., *, -].")


def _check_value(value: Any, path: str, errors: List[str]) -> None:
    if value is None:
        errors.append(f"{path} is missing.")
        return
    if isinstance(value, dict):
        if set(value) != {"type", "value"}:
            errors.append(f"{path} typed value must contain exactly 'type' and 'value'.")
            return
        value_type = value.get("type")
        raw = value.get("value")
        if value_type == "NUMBER":
            if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
                errors.append(f"{path} declares NUMBER but does not contain a finite number.")
        elif value_type == "BOOLEAN":
            if not isinstance(raw, bool):
                errors.append(f"{path} declares BOOLEAN but does not contain true/false.")
        elif value_type == "STRING":
            _check_string_token(raw, path, errors)
        else:
            errors.append(f"{path} has unknown typed value kind {value_type!r}.")
        return
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            errors.append(f"{path} must be a finite number.")
        return
    if isinstance(value, str):
        _check_string_token(value, path, errors)
        return
    errors.append(f"{path} must be a string, finite number, boolean, or typed value object.")


def _check_attribute(attribute: Any, path: str, errors: List[str]) -> None:
    if not isinstance(attribute, str):
        errors.append(f"{path} must be a string.")
        return
    if attribute in SENSITIVE_ATTRIBUTE_SET:
        errors.append(f"{path} uses sensitive identifier '{attribute}', which is excluded from v1.")
    elif attribute in PARTNER_ATTRIBUTE_SET:
        errors.append(f"{path}='{attribute}' is partner-configurable; obtain and verify its partner mapping before use.")
    elif attribute not in SUPPORTED_ATTRIBUTE_SET:
        errors.append(f"{path}='{attribute}' is not in the documented v1 catalog.")


def _check_chain(chain: Any, path: str, errors: List[str]) -> None:
    if not isinstance(chain, dict):
        errors.append(f"{path} must be an object.")
        return
    conditions = chain.get("conditions")
    combinator = chain.get("combinator")
    if not isinstance(conditions, list) or len(conditions) == 0:
        errors.append(f"{path}.conditions must contain at least one condition.")
        return
    if len(conditions) > 1 and combinator not in ("and", "or"):
        errors.append(f"{path} needs exactly one documented combinator ('and' or 'or') when it has multiple conditions.")
    if combinator not in (None, "and", "or"):
        errors.append(f"{path}.combinator must be 'and', 'or', or null.")
    for idx, condition in enumerate(conditions):
        _check_condition(condition, f"{path}.conditions[{idx}]", errors)


def _check_condition(condition: Any, path: str, errors: List[str]) -> None:
    if not isinstance(condition, dict):
        errors.append(f"{path} must be an object.")
        return
    kind = condition.get("kind")
    comparator = condition.get("comparator")
    if comparator not in COMPARATOR_SET:
        errors.append(f"{path}.comparator is not in the documented comparator catalog.")
    required_by_kind = {
        "ATTRIBUTE_CMP": ["attribute", "value"],
        "LIST_CHECK": ["category", "listName", "mode", "value"],
        "FUNCTION_CALL": ["functionName", "argument", "value"],
        "SCALED_CMP": ["attribute", "multiplier", "scaleUnit", "target"],
        "EVENT_COUNT": ["eventName", "value"],
        "GLOB_MATCH": ["attribute", "pattern", "value"],
    }
    if kind not in required_by_kind:
        errors.append(f"{path}.kind={kind!r} is not a supported condition kind.")
        return
    for field in required_by_kind[kind]:
        if field not in condition or condition[field] is None:
            errors.append(f"{path}.{field} is required for kind {kind}.")

    if kind in ("ATTRIBUTE_CMP", "SCALED_CMP", "GLOB_MATCH"):
        if condition.get("attribute") is not None:
            _check_attribute(condition.get("attribute"), f"{path}.attribute", errors)
    if kind == "LIST_CHECK":
        category = condition.get("category")
        if category not in LIST_CATEGORY_SET:
            errors.append(f"{path}.category={category!r} is not a documented v1 list category.")
        _check_string_token(condition.get("listName"), f"{path}.listName", errors)
        if condition.get("mode") not in CATALOG["list_modes"]:
            errors.append(f"{path}.mode must be one of {CATALOG['list_modes']}.")
    if kind == "FUNCTION_CALL":
        if condition.get("functionName") not in FUNCTION_SET:
            errors.append(f"{path}.functionName is not in the documented v1 function catalog.")
        _check_string_token(condition.get("argument"), f"{path}.argument", errors)
    if kind == "SCALED_CMP":
        multiplier = condition.get("multiplier")
        if isinstance(multiplier, bool) or not isinstance(multiplier, int) or multiplier <= 0:
            errors.append(f"{path}.multiplier must be a positive integer in v1.")
        if condition.get("scaleUnit") not in ("Times", "Percentage"):
            errors.append(f"{path}.scaleUnit must be 'Times' or 'Percentage'.")
        target = condition.get("target")
        if target not in ("previousTxnAmount", "merchantMonthlyLimit"):
            errors.append(f"{path}.target must be a documented scaled-comparison target.")
    if kind == "EVENT_COUNT":
        if condition.get("eventName") not in EVENT_SET:
            errors.append(f"{path}.eventName is outside the documented v1 event examples.")
    if kind == "GLOB_MATCH":
        _check_string_token(condition.get("pattern"), f"{path}.pattern", errors)
    if "value" in condition:
        _check_value(condition.get("value"), f"{path}.value", errors)


def expand_ir_for_schema(ir_data: Any) -> Any:
    """Fill nullable keys explicitly for hand-authored fixtures/prompts only.

    Do NOT call this on model output before AssistantEnvelope.model_validate():
    model output must satisfy the required-key JSON Schema without repair.
    """
    if not isinstance(ir_data, dict):
        return ir_data
    ir = copy.deepcopy(ir_data)
    ir.setdefault("current", None)
    ir.setdefault("history", None)

    nullable_condition_fields = (
        "attribute", "category", "listName", "mode", "functionName", "argument",
        "multiplier", "scaleUnit", "target", "eventName", "pattern", "value",
    )

    def expand_chain(chain: Any) -> Any:
        if not isinstance(chain, dict):
            return chain
        chain.setdefault("combinator", None)
        conditions = chain.get("conditions")
        if isinstance(conditions, list):
            expanded = []
            for item in conditions:
                if isinstance(item, dict):
                    node = copy.deepcopy(item)
                    for field in nullable_condition_fields:
                        node.setdefault(field, None)
                    expanded.append(node)
                else:
                    expanded.append(item)
            chain["conditions"] = expanded
        return chain

    if isinstance(ir.get("current"), dict):
        ir["current"] = expand_chain(ir["current"])

    history = ir.get("history")
    if isinstance(history, dict):
        window = history.get("window")
        if isinstance(window, dict):
            window.setdefault("value", None)
            window.setdefault("unit", None)
        history.setdefault("filter", None)
        history.setdefault("grouping", None)
        if isinstance(history.get("filter"), dict):
            history["filter"] = expand_chain(history["filter"])
        aggregations = history.get("aggregations")
        if isinstance(aggregations, dict):
            aggregations.setdefault("combinator", None)
        ir["history"] = history
    return ir


def expand_envelope_for_examples(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Make few-shot examples conform to the explicit-null response schema."""
    result = copy.deepcopy(envelope)
    result.setdefault("rule_ir", None)
    result.setdefault("clarification_questions", None)
    result.setdefault("unrepresentable_reason", None)
    if isinstance(result.get("rule_ir"), dict):
        result["rule_ir"] = expand_ir_for_schema(result["rule_ir"])
    return result


def validate_rule_ir(ir_data: Any) -> List[str]:
    """Return semantic validation errors; an empty list means valid for this v1 subset only."""
    errors: List[str] = []
    try:
        ir_model = RuleIR.model_validate(expand_ir_for_schema(ir_data))
    except ValidationError as exc:
        return [f"IR schema error: {exc.errors(include_url=False)}"]
    ir = ir_model.model_dump(exclude_none=True)
    shape = ir.get("shape")
    current = ir.get("current")
    history = ir.get("history")
    if shape not in CATALOG["rule_shapes"]:
        errors.append(f"Unsupported rule shape: {shape!r}.")
        return errors
    if shape == "CURRENT_TXN":
        if current is None or history is not None:
            errors.append("CURRENT_TXN requires current and must not include history.")
        if current is not None:
            _check_chain(current, "current", errors)
    elif shape == "HISTORY_TXN":
        if history is None or current is not None:
            errors.append("HISTORY_TXN requires history and must not include current.")
    elif shape == "NESTED_CURRENT_AND_HISTORY":
        if current is None or history is None:
            errors.append("NESTED_CURRENT_AND_HISTORY requires both current and history.")
        if current is not None:
            _check_chain(current, "current", errors)

    if shape in ("HISTORY_TXN", "NESTED_CURRENT_AND_HISTORY") and history is not None:
        window = history.get("window")
        if not isinstance(window, dict):
            errors.append("history.window must be an object.")
        else:
            wkind = window.get("kind")
            if wkind not in CATALOG["history_windows"]:
                errors.append(f"Unsupported history window kind: {wkind!r}.")
            if wkind == "WITHIN":
                val, unit = window.get("value"), window.get("unit")
                if isinstance(val, bool) or not isinstance(val, int) or val <= 0:
                    errors.append("WITHIN window requires a positive integer value.")
                if unit not in ("hours", "minutes"):
                    errors.append("WITHIN window unit must be 'hours' or 'minutes'.")
            elif window.get("value") is not None or window.get("unit") is not None:
                errors.append(f"{wkind} must not include a numeric value or unit.")

        filter_block = history.get("filter")
        grouping = history.get("grouping")
        if filter_block is not None:
            _check_chain(filter_block, "history.filter", errors)
            if grouping is None:
                errors.append("A history where/filter requires 'from same' or 'to different' grouping.")
        elif grouping is not None:
            errors.append("History grouping cannot appear without a where/filter in v1.")
        if grouping is not None:
            if grouping.get("direction") not in ("from same", "to different"):
                errors.append("history.grouping.direction must be 'from same' or 'to different'.")
            _check_attribute(grouping.get("attribute"), "history.grouping.attribute", errors)

        aggs = history.get("aggregations")
        if not isinstance(aggs, dict) or not isinstance(aggs.get("checks"), list) or not aggs.get("checks"):
            errors.append("history.aggregations.checks must contain at least one check.")
        else:
            checks = aggs["checks"]
            if len(checks) > 1 and aggs.get("combinator") not in ("and", "or"):
                errors.append("Multiple history aggregations require an 'and' or 'or' combinator.")
            for idx, check in enumerate(checks):
                if check.get("metric") not in HISTORY_METRIC_SET:
                    errors.append(f"history.aggregations.checks[{idx}].metric is not documented.")
                if check.get("comparator") not in COMPARATOR_SET:
                    errors.append(f"history.aggregations.checks[{idx}].comparator is not documented.")
                value = check.get("value")
                if isinstance(value, bool) or not isinstance(value, int):
                    errors.append(f"history.aggregations.checks[{idx}].value must be an integer in v1.")
        if aggs and aggs.get("combinator") not in (None, "and", "or"):
            errors.append("history.aggregations.combinator must be 'and', 'or', or null.")
    return errors


def validate_envelope_consistency(envelope: Dict[str, Any]) -> List[str]:
    """Validate status/rule payload consistency in addition to JSON-schema validity."""
    errors: List[str] = []
    outcome = envelope.get("outcome")
    rule_ir = envelope.get("rule_ir")
    if outcome == "ready":
        if rule_ir is None:
            errors.append("outcome=ready requires a non-null rule_ir.")
        else:
            errors.extend(validate_rule_ir(rule_ir))
        if envelope.get("clarification_questions"):
            errors.append("outcome=ready must not include clarification questions.")
        if envelope.get("unrepresentable_reason"):
            errors.append("outcome=ready must not include unrepresentable_reason.")
    else:
        if rule_ir is not None:
            errors.append("Non-ready outcome must have rule_ir=null.")
        if outcome == "needs_clarification" and not envelope.get("clarification_questions"):
            errors.append("needs_clarification requires at least one clarification question.")
        if outcome == "cannot_express" and not envelope.get("unrepresentable_reason"):
            errors.append("cannot_express requires unrepresentable_reason.")
    return errors


def canonical_json_value(value: Any) -> Any:
    """Canonicalize IR for semantic equality, including typed vs scalar values."""
    if isinstance(value, dict):
        # A typed value node and its scalar equivalent describe the same literal.
        if set(value) == {"type", "value"} and value.get("type") in {"NUMBER", "STRING", "BOOLEAN"}:
            kind = value["type"]
            raw = value["value"]
            return {"$literal_type": kind, "value": raw}
        normalized = {k: canonical_json_value(v) for k, v in sorted(value.items()) if v is not None}
        # Condition and aggregation order does not change semantics inside a single
        # all-AND or all-OR chain, so ignore ordering for IR semantic comparison.
        for key in ("conditions", "checks"):
            if key in normalized and isinstance(normalized[key], list):
                normalized[key] = sorted(normalized[key], key=lambda item: json.dumps(item, sort_keys=True))
        return normalized
    if isinstance(value, list):
        return [canonical_json_value(v) for v in value]
    if isinstance(value, bool):
        # bool subclasses int in Python; tag it so true can never compare equal to 1.
        return {"$literal_type": "BOOLEAN", "value": value}
    if isinstance(value, (int, float)):
        return {"$literal_type": "NUMBER", "value": value}
    if isinstance(value, str):
        return {"$literal_type": "STRING", "value": value}
    return value


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
