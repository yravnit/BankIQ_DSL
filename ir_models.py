"""Pydantic IR schema: RuleIR + AssistantEnvelope (the LLM response contract)."""

from typing import Any, List, Literal, Optional, Dict

from pydantic import BaseModel, ConfigDict

# PART 1: PYDANTIC IR SCHEMA (Mirrors the Zod Schema for Grammar Constrained Decoding)

# ===========================================================================



class StrictModel(BaseModel):
    """Strict structural schema. Semantic restrictions are enforced separately below."""

    model_config = ConfigDict(extra="forbid", strict=True)


ComparatorLiteral = Literal[

    "lesser than",

    "greater than",

    "equal to",

    "not equal to",

    "lesserThan equal to",

    "greaterThan equal to",

    "contains",

]



class ValueNode(StrictModel):

    type: Literal["NUMBER", "STRING", "BOOLEAN"]

    value: Any



class ConditionNode(StrictModel):
    """Flat, llama.cpp-friendly condition schema.

    Every key is required, but fields irrelevant to the selected `kind` must be
    explicit nulls. Semantic validation checks which fields apply to each kind.
    """

    kind: Literal[
        "ATTRIBUTE_CMP",
        "LIST_CHECK",
        "FUNCTION_CALL",
        "SCALED_CMP",
        "EVENT_COUNT",
        "GLOB_MATCH",
    ]

    # Nullable but REQUIRED in the JSON output. Unused fields must be null.
    attribute: Optional[str]
    category: Optional[str]
    listName: Optional[str]
    mode: Optional[Literal["MEMBERSHIP", "COUNT", "AMOUNT"]]
    functionName: Optional[str]
    argument: Optional[str]
    multiplier: Optional[int]
    scaleUnit: Optional[Literal["Times", "Percentage"]]
    target: Optional[str]
    eventName: Optional[str]
    pattern: Optional[str]
    comparator: ComparatorLiteral
    value: Optional[Any]



class ConditionChain(StrictModel):
    # Required nullable key: a single condition uses null; multiple conditions need and/or.
    combinator: Optional[Literal["and", "or"]]
    conditions: List[ConditionNode]



class WindowSpec(StrictModel):
    kind: Literal["WITHIN", "SAME_DAY", "SAME_MONTH", "AFTER_LAST_DECLINED"]
    # Required nullable keys: only WITHIN uses a numeric value and unit.
    value: Optional[int]
    unit: Optional[Literal["hours", "minutes"]]



class GroupingSpec(StrictModel):

    direction: Literal["from same", "to different"]

    attribute: str



class AggregationCheck(StrictModel):

    metric: Literal["count", "amount", "refundAmount"]

    comparator: ComparatorLiteral

    value: int



class AggregationChain(StrictModel):
    # Required nullable key: null for one aggregation; and/or for multiple checks.
    combinator: Optional[Literal["and", "or"]]
    checks: List[AggregationCheck]



class HistoryBlock(StrictModel):
    window: WindowSpec
    # Both keys are required; use null when there is no filter or grouping.
    filter: Optional[ConditionChain]
    grouping: Optional[GroupingSpec]
    aggregations: AggregationChain



class RuleIR(StrictModel):
    shape: Literal["CURRENT_TXN", "HISTORY_TXN", "NESTED_CURRENT_AND_HISTORY"]
    # Required nullable keys eliminate the omission-vs-null ambiguity observed in v5.
    current: Optional[ConditionChain]
    history: Optional[HistoryBlock]



class AssistantEnvelope(StrictModel):
    """Compact structured result for reliable grammar-constrained decoding.

    Explanations are intentionally not generated inside the JSON payload. The application
    can explain a result from the validated IR and deterministic validator diagnostics.
    """

    outcome: Literal["ready", "needs_clarification", "cannot_express"]
    # These keys are REQUIRED; use explicit null when not applicable.
    rule_ir: Optional[RuleIR]
    clarification_questions: Optional[List[str]]
    unrepresentable_reason: Optional[str]
