"""Documented v1 catalog: the single source of truth for names the validator accepts."""

import re

from typing import Any, Dict

# ===========================================================================
# SINGLE SOURCE OF TRUTH: DOCUMENTED CATALOG + SEMANTIC IR VALIDATION
# ===========================================================================

# This is deliberately a *curated v1 catalog*, not a claim that it covers the
# company's complete grammar. Keep provenance visible and add entries only when
# supported by the supplied PDF or clearly labeled external/inferred evidence.
PARTNER_PROVISIONAL_ATTRIBUTES = (
    [f"attribute{i}" for i in range(1, 11)]
    + [f"measure{i}" for i in range(1, 11)]
    + [f"time{i}" for i in range(1, 11)]
    + [f"bool{i}" for i in range(1, 11)]
    + ["merchantAttribute1", "merchantMeasure1", "merchantTime1"]
    + ["agentAttribute1", "agentMeasure1"]
    + ["customerAttribute1", "payeeAttribute1"]
)

SENSITIVE_ATTRIBUTES = ["pan", "aadhar"]
SUPPORTED_ATTRIBUTES = [
    "txnAmount", "paymentMethod", "payerAccountNumber", "payerBankIfsc",
    "payeeBankIfsc", "latitude", "longitude", "responseCode", "deviceOs",
    "xChannelId", "payerVpa", "payeeVpa", "custAccountNumber", "areaName",
    "stateName", "applicationID", "custCity", "custIncomeRange",
    "custAccountOpeningTimestamp", "custIfsc", "previousTxnAmount",
    "merchantMonthlyLimit", "txnType", "payerId", "custVulnerabilityScore",
]

CATALOG: Dict[str, Any] = {
    "schema_version": "1.0.0",
    "source": "IUCA Rule DSL Guide.pdf, dated 30 September 2026",
    "scope_note": "Curated subset only; absence does not prove the real IUCA engine lacks an item.",
    "attributes": {
        "documented_subset": SUPPORTED_ATTRIBUTES,
        "sensitive_excluded_from_v1": SENSITIVE_ATTRIBUTES,
        "partner_provisional_unmapped": PARTNER_PROVISIONAL_ATTRIBUTES,
    },
    "comparators": [
        "lesser than", "greater than", "equal to", "not equal to",
        "lesserThan equal to", "greaterThan equal to", "contains",
    ],
    "list_categories": [
        "Payer Account Number", "Payer VPA", "Device ID", "Payer Bank Ifsc",
        "Payer Account Ifsc", "Geo Coordinates",
    ],
    "list_modes": ["MEMBERSHIP", "COUNT", "AMOUNT"],
    "built_in_functions": ["isPayerBankIFSCStartsWith"],
    "event_examples": ["mobile_number_change", "pin_change", "kyc_change"],
    "history_metrics": ["count", "amount", "refundAmount"],
    "history_windows": ["WITHIN", "SAME_DAY", "SAME_MONTH", "AFTER_LAST_DECLINED"],
    "rule_shapes": ["CURRENT_TXN", "HISTORY_TXN", "NESTED_CURRENT_AND_HISTORY"],
    "string_literal_policy": {
        "source_constraint": "The PDF says quoted strings cannot contain spaces.",
        "additional_v1_allowlist": "ASCII letters, digits, underscore, dot, asterisk, and hyphen only.",
        "pattern": r"^[A-Za-z0-9_.*-]+$",
    },
}

COMPARATOR_SET = set(CATALOG["comparators"])
SUPPORTED_ATTRIBUTE_SET = set(CATALOG["attributes"]["documented_subset"])
PARTNER_ATTRIBUTE_SET = set(CATALOG["attributes"]["partner_provisional_unmapped"])
SENSITIVE_ATTRIBUTE_SET = set(CATALOG["attributes"]["sensitive_excluded_from_v1"])
LIST_CATEGORY_SET = set(CATALOG["list_categories"])
FUNCTION_SET = set(CATALOG["built_in_functions"])
EVENT_SET = set(CATALOG["event_examples"])
HISTORY_METRIC_SET = set(CATALOG["history_metrics"])
STRING_TOKEN_RE = re.compile(CATALOG["string_literal_policy"]["pattern"])
