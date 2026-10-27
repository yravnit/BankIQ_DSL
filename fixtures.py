"""Golden seeds (PDF §9), negative and edge evaluation cases."""

from typing import Any, Dict, List

# ===========================================================================

# PART 3: GOLDEN SEEDS, COMBINATORIAL GENERATOR & NEGATIVE CASES

# ===========================================================================



GOLDEN_SEEDS: List[Dict[str, Any]] = [

    {

        "id": "sec9_01_single_condition",

        "pattern": "Single condition",

        "shape": "SHAPE_A",

        "expected_outcome": "ready",

        "expected_dsl": "(Current transaction where txnAmount greater than 50000)",

        "expected_ir": {

            "shape": "CURRENT_TXN",

            "current": {

                "combinator": None,

                "conditions": [

                    {

                        "kind": "ATTRIBUTE_CMP",

                        "attribute": "txnAmount",

                        "comparator": "greater than",

                        "value": {"type": "NUMBER", "value": 50000},

                    }

                ],

            },

        },

        "paraphrases": [

            "Flag the current transaction if the transaction amount is greater than 50000.",

            "Check if current txnAmount is strictly above 50000.",

            "Trigger when the current transaction's amount exceeds 50000.",

            "Rule for current txn where txnAmount > 50000.",

        ],

    },

    {

        "id": "sec9_02_and_chain",

        "pattern": "and chain",

        "shape": "SHAPE_A",

        "expected_outcome": "ready",

        "expected_dsl": '(Current transaction where txnAmount greater than 50000 and paymentMethod equal to "P2P")',

        "expected_ir": {

            "shape": "CURRENT_TXN",

            "current": {

                "combinator": "and",

                "conditions": [

                    {

                        "kind": "ATTRIBUTE_CMP",

                        "attribute": "txnAmount",

                        "comparator": "greater than",

                        "value": {"type": "NUMBER", "value": 50000},

                    },

                    {

                        "kind": "ATTRIBUTE_CMP",

                        "attribute": "paymentMethod",

                        "comparator": "equal to",

                        "value": {"type": "STRING", "value": "P2P"},

                    },

                ],

            },

        },

        "paraphrases": [

            "Current transaction where transaction amount is over 50000 and payment method is P2P.",

            "Match current transactions with txnAmount > 50000 and paymentMethod equal to P2P.",

            "Alert on P2P payments where the current transaction amount exceeds 50000.",

            "Check current txn: amount greater than 50000 and paymentMethod is P2P.",

        ],

    },

    {

        "id": "sec9_03_or_chain",

        "pattern": "or chain",

        "shape": "SHAPE_A",

        "expected_outcome": "ready",

        "expected_dsl": '(Current transaction where responseCode equal to "00" or responseCode equal to "U30")',

        "expected_ir": {

            "shape": "CURRENT_TXN",

            "current": {

                "combinator": "or",

                "conditions": [

                    {

                        "kind": "ATTRIBUTE_CMP",

                        "attribute": "responseCode",

                        "comparator": "equal to",

                        "value": {"type": "STRING", "value": "00"},

                    },

                    {

                        "kind": "ATTRIBUTE_CMP",

                        "attribute": "responseCode",

                        "comparator": "equal to",

                        "value": {"type": "STRING", "value": "U30"},

                    },

                ],

            },

        },

        "paraphrases": [

            "Current transaction where response code is either 00 or U30.",

            "Match if the current transaction responseCode equals 00 or equals U30.",

            "Trigger when responseCode is 00 or U30 on the current transaction.",

            "Check current txn for responseCode == 00 or responseCode == U30.",

        ],

    },

    {

        "id": "sec9_04_list_membership",

        "pattern": "List membership",

        "shape": "SHAPE_A",

        "expected_outcome": "ready",

        "expected_dsl": '(Current transaction where Payer Account Ifsc On "BlockedAccounts" equal to true and txnAmount greaterThan equal to 25000)',

        "expected_ir": {

            "shape": "CURRENT_TXN",

            "current": {

                "combinator": "and",

                "conditions": [

                    {

                        "kind": "LIST_CHECK",

                        "category": "Payer Account Ifsc",

                        "listName": "BlockedAccounts",

                        "mode": "MEMBERSHIP",

                        "comparator": "equal to",

                        "value": {"type": "BOOLEAN", "value": True},

                    },

                    {

                        "kind": "ATTRIBUTE_CMP",

                        "attribute": "txnAmount",

                        "comparator": "greaterThan equal to",

                        "value": {"type": "NUMBER", "value": 25000},

                    },

                ],

            },

        },

        "paraphrases": [

            "Current transaction where Payer Account Ifsc is on the BlockedAccounts list and transaction amount is at least 25000.",

            "Flag if Payer Account Ifsc is present in BlockedAccounts and txnAmount >= 25000.",

            "Check current txn: Payer Account Ifsc On BlockedAccounts is true and amount greater than or equal to 25000.",

            "Match when Payer Account Ifsc belongs to BlockedAccounts and txnAmount is 25000 or more.",

        ],

    },

    {

        "id": "sec9_05_list_count",

        "pattern": "List count",

        "shape": "SHAPE_A",

        "expected_outcome": "ready",

        "expected_dsl": '(Current transaction where Payer VPA On "HighRiskVpa" Count greaterThan equal to 3)',

        "expected_ir": {

            "shape": "CURRENT_TXN",

            "current": {

                "combinator": None,

                "conditions": [

                    {

                        "kind": "LIST_CHECK",

                        "category": "Payer VPA",

                        "listName": "HighRiskVpa",

                        "mode": "COUNT",

                        "comparator": "greaterThan equal to",

                        "value": {"type": "NUMBER", "value": 3},

                    }

                ],

            },

        },

        "paraphrases": [

            "Current transaction where Payer VPA appears on the HighRiskVpa list at least 3 times.",

            "Check if the count for Payer VPA on list HighRiskVpa is greater than or equal to 3.",

            "Flag when Payer VPA On HighRiskVpa Count >= 3.",

            "Trigger if the current transaction's Payer VPA has a count of 3 or more on HighRiskVpa.",

        ],

    },

    {

        "id": "sec9_06_list_amount",

        "pattern": "List amount",

        "shape": "SHAPE_A",

        "expected_outcome": "ready",

        "expected_dsl": '(Current transaction where Payer Account Number On "WatchList" Amount greater than 100000)',

        "expected_ir": {

            "shape": "CURRENT_TXN",

            "current": {

                "combinator": None,

                "conditions": [

                    {

                        "kind": "LIST_CHECK",

                        "category": "Payer Account Number",

                        "listName": "WatchList",

                        "mode": "AMOUNT",

                        "comparator": "greater than",

                        "value": {"type": "NUMBER", "value": 100000},

                    }

                ],

            },

        },

        "paraphrases": [

            "Current transaction where cumulative amount for Payer Account Number on WatchList is greater than 100000.",

            "Flag if Payer Account Number On WatchList Amount exceeds 100000.",

            "Check if the WatchList amount for Payer Account Number is strictly over 100000.",

            "Trigger when Payer Account Number on WatchList has an accumulated amount > 100000.",

        ],

    },

    {

        "id": "sec9_07_builtin_function",

        "pattern": "Built-in function",

        "shape": "SHAPE_A",

        "expected_outcome": "ready",

        "expected_dsl": '(Current transaction where isPayerBankIFSCStartsWith "HDFC" equal to true)',

        "expected_ir": {

            "shape": "CURRENT_TXN",

            "current": {

                "combinator": None,

                "conditions": [

                    {

                        "kind": "FUNCTION_CALL",

                        "functionName": "isPayerBankIFSCStartsWith",

                        "argument": "HDFC",

                        "comparator": "equal to",

                        "value": {"type": "BOOLEAN", "value": True},

                    }

                ],

            },

        },

        "paraphrases": [

            "Current transaction where the payer bank IFSC starts with HDFC.",

            "Check if isPayerBankIFSCStartsWith HDFC is true on the current transaction.",

            "Flag transactions where the payer's bank IFSC prefix is HDFC.",

            "Match current txn if payer bank IFSC begins with HDFC.",

        ],

    },

    {

        "id": "sec9_08_multiply_by_number",

        "pattern": "Multiply by a number",

        "shape": "SHAPE_A",

        "expected_outcome": "ready",

        "expected_dsl": "(Current transaction where txnAmount greater than 2 Times previousTxnAmount)",

        "expected_ir": {

            "shape": "CURRENT_TXN",

            "current": {

                "combinator": None,

                "conditions": [

                    {

                        "kind": "SCALED_CMP",

                        "attribute": "txnAmount",

                        "comparator": "greater than",

                        "multiplier": 2,

                        "scaleUnit": "Times",

                        "target": "previousTxnAmount",

                    }

                ],

            },

        },

        "paraphrases": [

            "Current transaction where transaction amount is greater than 2 times the previous transaction amount.",

            "Flag if current txnAmount exceeds 2x previousTxnAmount.",

            "Trigger when txnAmount is more than twice the previousTxnAmount.",

            "Check current txn: txnAmount > 2 Times previousTxnAmount.",

        ],

    },

    {

        "id": "sec9_09_multiply_by_percentage",

        "pattern": "Multiply by a percentage",

        "shape": "SHAPE_A",

        "expected_outcome": "ready",

        "expected_dsl": "(Current transaction where txnAmount greater than 150 Percentage merchantMonthlyLimit)",

        "expected_ir": {

            "shape": "CURRENT_TXN",

            "current": {

                "combinator": None,

                "conditions": [

                    {

                        "kind": "SCALED_CMP",

                        "attribute": "txnAmount",

                        "comparator": "greater than",

                        "multiplier": 150,

                        "scaleUnit": "Percentage",

                        "target": "merchantMonthlyLimit",

                    }

                ],

            },

        },

        "paraphrases": [

            "Current transaction where txnAmount is greater than 150 percent of merchantMonthlyLimit.",

            "Flag if the transaction amount exceeds 150% of the merchant monthly limit.",

            "Check if current txnAmount > 150 Percentage merchantMonthlyLimit.",

            "Trigger when current transaction amount is above 150 percent of merchantMonthlyLimit.",

        ],

    },

    {

        "id": "sec9_10_history_simple_count",

        "pattern": "History, simple count",

        "shape": "SHAPE_B",

        "expected_outcome": "ready",

        "expected_dsl": "(Transactions within 24 hours should have count greater than 5)",

        "expected_ir": {

            "shape": "HISTORY_TXN",

            "history": {

                "window": {"kind": "WITHIN", "value": 24, "unit": "hours"},

                "filter": None,

                "grouping": None,

                "aggregations": {

                    "combinator": None,

                    "checks": [{"metric": "count", "comparator": "greater than", "value": 5}],

                },

            },

        },

        "paraphrases": [

            "Transactions within the last 24 hours should have a count greater than 5.",

            "Flag if there are more than 5 transactions within 24 hours.",

            "Check transaction history: within 24 hours, count > 5.",

            "Trigger when the number of transactions in a 24 hour window exceeds 5.",

        ],

    },

    {

        "id": "sec9_11_history_two_cumulative",

        "pattern": "History, two cumulative checks",

        "shape": "SHAPE_B",

        "expected_outcome": "ready",

        "expected_dsl": "(Transactions within 24 hours should have amount greater than 100000 and count greater than 5)",

        "expected_ir": {

            "shape": "HISTORY_TXN",

            "history": {

                "window": {"kind": "WITHIN", "value": 24, "unit": "hours"},

                "filter": None,

                "grouping": None,

                "aggregations": {

                    "combinator": "and",

                    "checks": [

                        {"metric": "amount", "comparator": "greater than", "value": 100000},

                        {"metric": "count", "comparator": "greater than", "value": 5},

                    ],

                },

            },

        },

        "paraphrases": [

            "Transactions within 24 hours should have total amount greater than 100000 and count greater than 5.",

            "Check if transactions in the last 24 hours exceed 100000 in amount and have a count over 5.",

            "History rule: within 24 hours, cumulative amount > 100000 and transaction count > 5.",

            "Trigger when 24-hour transaction volume is over 100000 and count is above 5.",

        ],

    },

    {

        "id": "sec9_12_history_with_filter",

        "pattern": "History with filter",

        "shape": "SHAPE_B",

        "expected_outcome": "ready",

        "expected_dsl": '(Transactions within 24 hours where txnType equal to "CREDIT" from same payerId should have count greater than 3)',

        "expected_ir": {

            "shape": "HISTORY_TXN",

            "history": {

                "window": {"kind": "WITHIN", "value": 24, "unit": "hours"},

                "filter": {

                    "combinator": None,

                    "conditions": [

                        {

                            "kind": "ATTRIBUTE_CMP",

                            "attribute": "txnType",

                            "comparator": "equal to",

                            "value": {"type": "STRING", "value": "CREDIT"},

                        }

                    ],

                },

                "grouping": {"direction": "from same", "attribute": "payerId"},

                "aggregations": {

                    "combinator": None,

                    "checks": [{"metric": "count", "comparator": "greater than", "value": 3}],

                },

            },

        },

        "paraphrases": [

            "Transactions within 24 hours where txnType is CREDIT from the same payerId should have a count greater than 3.",

            "Check if there are more than 3 CREDIT transactions from the same payerId within 24 hours.",

            "Look back 24 hours: filter for txnType equal to CREDIT from same payerId, and check if count > 3.",

            "Flag when the same payerId has more than 3 CREDIT transactions in 24 hours.",

        ],

    },

    {

        "id": "sec9_13_customer_event_count",

        "pattern": "Customer event count",

        "shape": "SHAPE_A",

        "expected_outcome": "ready",

        "expected_dsl": "(Current transaction where event mobile_number_change count greater than 2)",

        "expected_ir": {

            "shape": "CURRENT_TXN",

            "current": {

                "combinator": None,

                "conditions": [

                    {

                        "kind": "EVENT_COUNT",

                        "eventName": "mobile_number_change",

                        "comparator": "greater than",

                        "value": 2,

                    }

                ],

            },

        },

        "paraphrases": [

            "Current transaction where the mobile_number_change event count is greater than 2.",

            "Flag if customer event mobile_number_change has fired more than 2 times.",

            "Check current txn: event mobile_number_change count > 2.",

            "Trigger when mobile_number_change event count exceeds 2.",

        ],

    },

    {

        "id": "sec9_14_glob_match",

        "pattern": "Glob match",

        "shape": "SHAPE_A",

        "expected_outcome": "ready",

        "expected_dsl": '(Current transaction where deviceOs like "Android*" equal to true)',

        "expected_ir": {

            "shape": "CURRENT_TXN",

            "current": {

                "combinator": None,

                "conditions": [

                    {

                        "kind": "GLOB_MATCH",

                        "attribute": "deviceOs",

                        "pattern": "Android*",

                        "comparator": "equal to",

                        "value": True,

                    }

                ],

            },

        },

        "paraphrases": [

            "Current transaction where deviceOs matches the wildcard pattern Android*.",

            "Check if deviceOs like Android* is equal to true on the current transaction.",

            "Flag when the current transaction's deviceOs starts with Android using glob match Android*.",

            "Match current txn where deviceOs glob matches Android*.",

        ],

    },

    {

        "id": "sec9_15_nested_shape_c",

        "pattern": "Nested (Shape C)",

        "shape": "SHAPE_C",

        "expected_outcome": "ready",

        "expected_dsl": "(Current transaction where txnAmount greater than 50000) AND (Transactions within 24 hours should have count greater than 3)",

        "expected_ir": {

            "shape": "NESTED_CURRENT_AND_HISTORY",

            "current": {

                "combinator": None,

                "conditions": [

                    {

                        "kind": "ATTRIBUTE_CMP",

                        "attribute": "txnAmount",

                        "comparator": "greater than",

                        "value": {"type": "NUMBER", "value": 50000},

                    }

                ],

            },

            "history": {

                "window": {"kind": "WITHIN", "value": 24, "unit": "hours"},

                "filter": None,

                "grouping": None,

                "aggregations": {

                    "combinator": None,

                    "checks": [{"metric": "count", "comparator": "greater than", "value": 3}],

                },

            },

        },

        "paraphrases": [

            "Current transaction where txnAmount is greater than 50000 AND transactions within 24 hours have a count greater than 3.",

            "Flag when the current transaction exceeds 50000 and there were more than 3 transactions in the last 24 hours.",

            "Combine: current txnAmount > 50000, plus 24-hour transaction history count > 3.",

            "Match if current transaction amount is over 50000 and transaction count within 24 hours is above 3.",

        ],

    },

]



NEGATIVE_AND_EDGE_CASES: List[Dict[str, Any]] = [

    {

        "id": "neg_vague_01_high_amount",

        "category": "vague_threshold",

        "expected_outcome": "needs_clarification",

        "prompt": "Flag the current transaction if the transaction amount is unusually large.",

        "expected_reason": "Missing numeric threshold for txnAmount.",

    },

    {

        "id": "neg_vague_02_recent_window",

        "category": "vague_window",

        "expected_outcome": "needs_clarification",

        "prompt": "Alert if a user performs too many transactions in a short time.",

        "expected_reason": "Missing specific time window and count threshold.",

    },

    {

        "id": "neg_vague_03_missing_history_grouping",

        "category": "missing_history_grouping",

        "expected_outcome": "needs_clarification",

        "prompt": "Transactions within 24 hours where txnType equal to CREDIT should have count greater than 3.",

        "expected_reason": "History rule with a 'where' filter must specify 'from same <attribute>' or 'to different <attribute>' before 'should have'.",

    },

    {

        "id": "neg_vague_04_partner_slot",

        "category": "partner_provisional_slot",

        "expected_outcome": "needs_clarification",

        "prompt": "Current transaction where attribute1 greater than 500.",

        "expected_reason": "Generic slot attribute1 is partner-configurable and unmapped by default.",

    },

    {

        "id": "neg_syntax_01_mixed_and_or",

        "category": "mixed_and_or",

        "expected_outcome": "cannot_express",

        "prompt": "Current transaction where txnAmount greater than 50000 and paymentMethod equal to P2P or responseCode equal to U30.",

        "expected_reason": "Grammar does not support mixing 'and' and 'or' in a single where clause.",

    },

    {

        "id": "neg_syntax_02_space_in_quoted_list",

        "category": "space_in_quotes",

        "expected_outcome": "cannot_express",

        "prompt": 'Current transaction where Payer Account Ifsc On "Blocked Accounts" equal to true.',

        "expected_reason": "Quoted strings and list names cannot contain spaces.",

    },

    {

        "id": "neg_syntax_03_space_in_string_literal",

        "category": "space_in_quotes",

        "expected_outcome": "cannot_express",

        "prompt": 'Current transaction where stateName equal to "Uttar Pradesh".',

        "expected_reason": "Quoted string literals cannot contain space characters in the IUCA DSL.",

    },

    {

        "id": "neg_syntax_04_cross_attribute_math",

        "category": "unrepresentable_math",

        "expected_outcome": "cannot_express",

        "prompt": "Current transaction where txnAmount plus custVulnerabilityScore greater than 10000.",

        "expected_reason": "Addition/subtraction across attributes is not supported in the DSL.",

    },

    {

        "id": "neg_catalog_01_unknown_attribute",

        "category": "unknown_catalog_item",

        "expected_outcome": "cannot_express",

        "prompt": "Current transaction where cibilScore lesser than 600.",

        "expected_reason": "Attribute 'cibilScore' is not in the documented catalog.",

    },

    {

        "id": "neg_catalog_02_unknown_function",

        "category": "unknown_catalog_item",

        "expected_outcome": "cannot_express",

        "prompt": "Current transaction where isTorExitNode equal to true.",

        "expected_reason": "Function 'isTorExitNode' is not in the documented catalog.",

    },

    {

        "id": "neg_privacy_01_raw_pan",

        "category": "privacy_sensitive_id",

        "expected_outcome": "cannot_express",

        "pre_llm_blocked": True,

        "prompt": 'Current transaction where pan equal to "ABCDE1234F".',

        "expected_reason": "Privacy policy prohibits embedding raw personal tax/identity literals.",

    },

]
