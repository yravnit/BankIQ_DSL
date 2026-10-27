"""Prompt builders: system prompt, fewshot, and variants v2..v6 (registered at import)."""

import json

from typing import List

from catalog import CATALOG
from fixtures import GOLDEN_SEEDS
from renderer import render_dsl
from validator import expand_ir_for_schema, validate_rule_ir

def build_system_prompt() -> str:
    """Build the model prompt from the same catalog that validation reads."""
    safe_attributes = ", ".join(CATALOG["attributes"]["documented_subset"])
    provisional = ", ".join(CATALOG["attributes"]["partner_provisional_unmapped"])
    sensitive = ", ".join(CATALOG["attributes"]["sensitive_excluded_from_v1"])
    categories = ", ".join(f'"{x}"' for x in CATALOG["list_categories"])
    functions = ", ".join(CATALOG["built_in_functions"])
    events = ", ".join(CATALOG["event_examples"])
    comparators = ", ".join(f'"{x}"' for x in CATALOG["comparators"])
    return f"""You are the IUCA Rule DSL Assistant. Translate the user's plain-language transaction rule request into a strictly typed JSON Intermediate Representation (IR).

Return only the JSON object required by the response schema. Never emit raw DSL text, Markdown, code fences, or commentary outside JSON.

DOCUMENTED V1 CATALOG ONLY:
- Documented attributes supported in v1: {safe_attributes}.
- Partner-configurable slots whose mappings are unknown: {provisional}. Ask for the partner mapping; do not emit a ready rule using one.
- Sensitive identifiers excluded from v1: {sensitive}. Do not embed raw values for these identifiers in IR.
- List categories (exact Title Case strings): {categories}.
- Built-in function examples supported in v1: {functions}.
- Event-count examples supported in v1: {events}. This is not the company's full event list.
- Comparators (exact strings): {comparators}.
- History metrics: count, amount, refundAmount. Supported window forms are within N hours/minutes, same day, same month, and after the last declined transaction.

STRICT DOCUMENTED-CONSTRAINT RULES:
1. If a threshold or time window is vague, use needs_clarification; never invent a value.
2. A history rule with a 'where' filter must also specify grouping ('from same <attribute>' or 'to different <attribute>'). If missing, use needs_clarification.
3. Do not mix 'and' and 'or' in one condition chain. If the requested logic cannot be represented without changing its meaning, use cannot_express.
4. Quoted strings and list names cannot contain spaces. For v1, allow only ASCII letters, digits, underscore, dot, asterisk, and hyphen in emitted string literals. Never silently sanitize values.
5. Unknown catalog items and partner-unmapped slots must not be emitted as ready rules.
6. Every field in the JSON schema is required. Emit every key; use explicit null for fields that do not apply. A ready output must include a non-null rule_ir. Non-ready outputs must have rule_ir=null.
7. Use needs_clarification with at least one clarification question; use cannot_express with a concise reason.
8. Return valid JSON only. A schema-valid object may still be semantically wrong; be conservative.
9. Think carefully through every requested condition, value, comparator, and rule shape before choosing an outcome. Do not simplify the request by dropping or merging conditions.
10. Return only the four schema fields: outcome, rule_ir, clarification_questions, and unrepresentable_reason. Do not add extra keys or free-form explanation. The full nullable-key structure is required.

LIMITATION: You are generating a candidate rule from a curated PDF subset, not verifying it against the company's private IUCA parser.
"""



SYSTEM_PROMPT = build_system_prompt()



PROMPT_TRAINING_EXAMPLES = [
    ("Apply this to the current payment: its amount must exceed 50,000.", "sec9_01_single_condition"),
    ("For the current payment, require both an amount above 50,000 and the P2P method.", "sec9_02_and_chain"),
    ("Match when the current response code is either 00 or U30.", "sec9_03_or_chain"),
    ("The payer account IFSC must be on BlockedAccounts, and the amount must be at least 25,000.", "sec9_04_list_membership"),
    ("Require the payer VPA count on HighRiskVpa to be three or more.", "sec9_05_list_count"),
    ("Match when the WatchList cumulative amount for the payer account is above 100,000.", "sec9_06_list_amount"),
    ("The payer bank IFSC prefix check for HDFC must evaluate to true.", "sec9_07_builtin_function"),
    ("Match if today's payment is more than double the previous transaction amount.", "sec9_08_multiply_by_number"),
    ("Match when the payment is above 150 percent of the merchant monthly limit.", "sec9_09_multiply_by_percentage"),
    ("Over a 24-hour lookback, the number of transactions must exceed five.", "sec9_10_history_simple_count"),
    ("Across the past 24 hours, total amount must exceed 100,000 and count must exceed five.", "sec9_11_history_two_cumulative"),
    ("In the previous 24 hours, count CREDIT transactions from the same payerId and require more than three.", "sec9_12_history_with_filter"),
    ("Match when the customer has had more than two mobile number change events.", "sec9_13_customer_event_count"),
    ("Match if the current device OS matches the wildcard Android*.", "sec9_14_glob_match"),
    ("Both must hold: current payment exceeds 50,000 and the 24-hour transaction count exceeds three.", "sec9_15_nested_shape_c"),
]


def build_pdf_examples_prompt() -> str:
    """Optional prompt with all 15 patterns; use larger context if the model needs it."""
    seed_by_id = {seed["id"]: seed for seed in GOLDEN_SEEDS}
    blocks = []
    for request, seed_id in PROMPT_TRAINING_EXAMPLES:
        expected_ir = expand_ir_for_schema(seed_by_id[seed_id]["expected_ir"])
        blocks.append(
            "User request: " + request + "\nExpected IR JSON: "
            + json.dumps(expected_ir, separators=(",", ":"), ensure_ascii=True)
        )
    return SYSTEM_PROMPT + "\n\nREFERENCE EXAMPLES (learn the mapping; do not reuse values unless requested):\n" + "\n".join(blocks)


def build_fewshot_prompt() -> str:
    """Expanded few-shot prompt focused on errors observed in the last benchmark.

    Examples are authored separately from evaluation prompts. We include representative positive
    patterns and negative/clarification cases so the model sees condition preservation, lists,
    glob-vs-contains, scaled comparisons, history grouping, nesting, and refusal behaviour.
    """
    seed_by_id = {seed["id"]: seed for seed in GOLDEN_SEEDS}
    selected_ids = [
        "sec9_02_and_chain",
        "sec9_04_list_membership",
        "sec9_05_list_count",
        "sec9_06_list_amount",
        "sec9_08_multiply_by_number",
        "sec9_09_multiply_by_percentage",
        "sec9_10_history_simple_count",
        "sec9_11_history_two_cumulative",
        "sec9_12_history_with_filter",
        "sec9_14_glob_match",
        "sec9_15_nested_shape_c",
    ]
    request_by_seed = {seed_id: request for request, seed_id in PROMPT_TRAINING_EXAMPLES}
    blocks: List[str] = []
    for seed_id in selected_ids:
        seed = seed_by_id[seed_id]
        envelope = {
            "outcome": "ready",
            "rule_ir": expand_ir_for_schema(seed["expected_ir"]),
            "clarification_questions": None,
            "unrepresentable_reason": None,
        }
        blocks.append(
            "User request: " + request_by_seed[seed_id] + "\nExpected JSON: "
            + json.dumps(envelope, separators=(",", ":"), ensure_ascii=True)
        )

    negative_examples = [
        {
            "request": "Flag transfers that are unusually expensive.",
            "response": {
                "outcome": "needs_clarification",
                "rule_ir": None,
                "clarification_questions": ["What numeric transaction-amount threshold should be used?"],
                "unrepresentable_reason": None,
            },
        },
        {
            "request": "Match when unlistedRiskScore is less than 400.",
            "response": {
                "outcome": "cannot_express",
                "rule_ir": None,
                "clarification_questions": None,
                "unrepresentable_reason": "unlistedRiskScore is not in the documented v1 catalog.",
            },
        },
        {
            "request": "Flag payments above 50000 and P2P payments, or transactions with response code U30, without specifying how the AND/OR logic is grouped.",
            "response": {
                "outcome": "cannot_express",
                "rule_ir": None,
                "clarification_questions": None,
                "unrepresentable_reason": "The requested mixed AND/OR logic is ambiguous and cannot be safely represented as a single documented condition chain.",
            },
        },
    ]
    for example in negative_examples:
        blocks.append(
            "User request: " + example["request"] + "\nExpected JSON: "
            + json.dumps(example["response"], separators=(",", ":"), ensure_ascii=True)
        )

    return SYSTEM_PROMPT + (
        "\n\nFEW-SHOT MAPPING EXAMPLES (follow the structure and exact DSL distinctions; do not copy values unless requested):\n"
        + "\n\n".join(blocks)
        + "\n\nFor the actual request, preserve every explicitly requested condition and value. "
          "Emit every required key, including explicit nulls for unused fields. Complete the full rule_ir and all closing braces. "
          "Do not simplify two conditions into one, do not replace a list check with an attribute comparison, "
          "do not replace 'like' wildcard matching with 'contains', and do not convert a percentage/Times "
          "construct into an ordinary number. Do not add explanatory fields outside the schema. "
          "Return exactly one schema-conforming JSON object, with no Markdown or text outside it."
    )


PROMPT_VARIANTS = {"fewshot": build_fewshot_prompt()}

# --- v2: same contract, plus the three patterns the fewshot prompt never showed ---
# The 2026-10-25 NIM runs scored 0/3 on built-in functions and 0/3 on event counts for
# every model, and refused valid `or` chains, because no example demonstrates them.
_V2_RULE3_OLD = (
    "3. Do not mix 'and' and 'or' in one condition chain. If the requested logic cannot "
    "be represented without changing its meaning, use cannot_express."
)
_V2_RULE3_NEW = (
    "3. Do not mix 'and' and 'or' in one condition chain. A pure chain is supported: set "
    "current.combinator to \"and\" or to \"or\" when every condition uses it. Only a chain "
    "that mixes the two is unrepresentable; use cannot_express only for the mixed case."
)

_V2_FIELD_GUIDE = (
    "REQUIRED FIELDS BY CONDITION KIND (every other ConditionNode field must be null):\n"
    "- ATTRIBUTE_CMP: attribute, comparator, value\n"
    "- LIST_CHECK: category, listName, mode, comparator, value; mode is MEMBERSHIP, COUNT, or AMOUNT\n"
    "- FUNCTION_CALL: functionName, argument, comparator, value\n"
    "- SCALED_CMP: attribute, comparator, multiplier, scaleUnit, target; scaleUnit is \"Times\" or \"Percentage\"; value is null\n"
    "- EVENT_COUNT: eventName, comparator, value; value is a bare integer and no history block is used\n"
    "- GLOB_MATCH: attribute, pattern, comparator, value\n"
    "The kind strings are exactly: ATTRIBUTE_CMP, LIST_CHECK, FUNCTION_CALL, SCALED_CMP, EVENT_COUNT, GLOB_MATCH."
)

_V2_EXTRA_EXAMPLES = [
    (
        "Match when the response code is 00 or U30.",
        {
            "shape": "CURRENT_TXN",
            "current": {
                "combinator": "or",
                "conditions": [
                    {"kind": "ATTRIBUTE_CMP", "attribute": "responseCode", "comparator": "equal to", "value": {"type": "STRING", "value": "00"}},
                    {"kind": "ATTRIBUTE_CMP", "attribute": "responseCode", "comparator": "equal to", "value": {"type": "STRING", "value": "U30"}},
                ],
            },
            "history": None,
        },
        '(Current transaction where responseCode equal to "00" or responseCode equal to "U30")',
    ),
    (
        "Match when the payer bank IFSC starts with HDFC.",
        {
            "shape": "CURRENT_TXN",
            "current": {
                "combinator": None,
                "conditions": [
                    {"kind": "FUNCTION_CALL", "functionName": "isPayerBankIFSCStartsWith", "argument": "HDFC", "comparator": "equal to", "value": {"type": "BOOLEAN", "value": True}},
                ],
            },
            "history": None,
        },
        '(Current transaction where isPayerBankIFSCStartsWith "HDFC" equal to true)',
    ),
    (
        "Match when the mobile_number_change event count is greater than 2.",
        {
            "shape": "CURRENT_TXN",
            "current": {
                "combinator": None,
                "conditions": [
                    {"kind": "EVENT_COUNT", "eventName": "mobile_number_change", "comparator": "greater than", "value": 2},
                ],
            },
            "history": None,
        },
        "(Current transaction where event mobile_number_change count greater than 2)",
    ),
]


_SCALED_EXAMPLES = [
    (
        "Match if today's payment is more than double the previous transaction amount.",
        {
            "shape": "CURRENT_TXN",
            "current": {
                "combinator": None,
                "conditions": [
                    {"kind": "SCALED_CMP", "attribute": "txnAmount", "comparator": "greater than", "multiplier": 2, "scaleUnit": "Times", "target": "previousTxnAmount"},
                ],
            },
            "history": None,
        },
        "(Current transaction where txnAmount greater than 2 Times previousTxnAmount)",
    ),
    (
        "Match when the payment is above 150 percent of the merchant monthly limit.",
        {
            "shape": "CURRENT_TXN",
            "current": {
                "combinator": None,
                "conditions": [
                    {"kind": "SCALED_CMP", "attribute": "txnAmount", "comparator": "greater than", "multiplier": 150, "scaleUnit": "Percentage", "target": "merchantMonthlyLimit"},
                ],
            },
            "history": None,
        },
        "(Current transaction where txnAmount greater than 150 Percentage merchantMonthlyLimit)",
    ),
]


def _render_examples(examples) -> str:
    blocks = []
    for request, ir, expected_dsl in examples:
        expanded = expand_ir_for_schema(ir)
        errors = validate_rule_ir(expanded)
        assert not errors, f"example invalid ({request}): {errors}"
        assert render_dsl(expanded) == expected_dsl, f"example renders {render_dsl(expanded)!r}, expected {expected_dsl!r}"
        response = {
            "outcome": "ready",
            "rule_ir": expanded,
            "clarification_questions": None,
            "unrepresentable_reason": None,
        }
        blocks.append(
            "User request: " + request + "\nExpected JSON: "
            + json.dumps(response, separators=(",", ":"), ensure_ascii=True)
        )
    return "\n\n".join(blocks)


def build_fewshot_prompt_v2(
    guide_position: str = "top", scaled_reminder: bool = False, dedupe_hint: bool = False
) -> str:
    """Fewshot prompt plus the three undocumented-in-prompt patterns.

    guide_position="end" moves the per-kind field guide to the last block, which
    matters for small models that lose the middle of a long prompt.
    scaled_reminder=True repeats the two SCALED_CMP examples right before the request,
    for models that ignore them in the middle of the prompt.
    dedupe_hint=True warns against emitting the same key twice (bolt writes eventName
    with its value, then repeats it as null, and last-key-wins erases the value).
    """
    prompt = PROMPT_VARIANTS["fewshot"]
    prompt = prompt.replace(_V2_RULE3_OLD, _V2_RULE3_NEW)
    final_anchor = "For the actual request, preserve every explicitly requested condition and value."
    assert final_anchor in prompt
    guide = _V2_FIELD_GUIDE
    if dedupe_hint:
        guide += (
            "\nWrite each field of one object exactly once. Never repeat a field you already "
            "set as null later in the same object."
        )
    if guide_position == "top":
        prompt = prompt.replace("\nLIMITATION:", "\n" + guide + "\n\nLIMITATION:")
    elif guide_position == "end":
        prompt = prompt.replace(final_anchor, guide + "\n\n" + final_anchor)
    else:
        raise ValueError(guide_position)
    anchor = "User request: Flag transfers that are unusually expensive."
    assert anchor in prompt
    prompt = prompt.replace(anchor, _render_examples(_V2_EXTRA_EXAMPLES) + "\n\n" + anchor)
    if scaled_reminder:
        reminder = (
            "SCALED_CMP REMINDER (multiplier, scaleUnit, and target are never null; copy this shape):\n"
            + _render_examples(_SCALED_EXAMPLES)
        )
        prompt = prompt.replace(final_anchor, reminder + "\n\n" + final_anchor)
    return prompt


PROMPT_VARIANTS["v2"] = build_fewshot_prompt_v2()
PROMPT_VARIANTS["v3"] = build_fewshot_prompt_v2("end")
PROMPT_VARIANTS["v4"] = build_fewshot_prompt_v2("end", scaled_reminder=True)
PROMPT_VARIANTS["v5"] = build_fewshot_prompt_v2("top", scaled_reminder=True)
PROMPT_VARIANTS["v6"] = build_fewshot_prompt_v2("top", scaled_reminder=True, dedupe_hint=True)
