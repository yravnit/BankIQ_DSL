"""Deterministic IR-to-DSL renderer. Fixed templates only; never concatenates model text."""

from typing import Any, Dict

def render_condition(c: Dict[str, Any]) -> str:

    kind = c["kind"]

    cmp_str = c["comparator"]

    val = c.get("value")



    def fmt_val(v: Any) -> str:

        if isinstance(v, dict):

            vtype, raw = v["type"], v["value"]

            if vtype == "STRING":

                return f'"{raw}"'

            if vtype == "BOOLEAN":

                return "true" if raw else "false"

            return str(raw)

        if isinstance(v, bool):

            return "true" if v else "false"

        if isinstance(v, str):

            return f'"{v}"'

        return str(v)



    if kind == "ATTRIBUTE_CMP":

        return f"{c['attribute']} {cmp_str} {fmt_val(val)}"

    elif kind == "LIST_CHECK":

        mode = c.get("mode", "MEMBERSHIP")

        base = f'{c["category"]} On "{c["listName"]}"'

        if mode == "COUNT":

            return f"{base} Count {cmp_str} {fmt_val(val)}"

        elif mode == "AMOUNT":

            return f"{base} Amount {cmp_str} {fmt_val(val)}"

        return f"{base} {cmp_str} {fmt_val(val)}"

    elif kind == "FUNCTION_CALL":

        return f'{c["functionName"]} "{c["argument"]}" {cmp_str} {fmt_val(val)}'

    elif kind == "SCALED_CMP":

        return f'{c["attribute"]} {cmp_str} {c["multiplier"]} {c["scaleUnit"]} {c["target"]}'

    elif kind == "EVENT_COUNT":

        return f'event {c["eventName"]} count {cmp_str} {fmt_val(val)}'

    elif kind == "GLOB_MATCH":

        return f'{c["attribute"]} like "{c["pattern"]}" {cmp_str} {fmt_val(val)}'

    raise ValueError(f"Unknown condition kind: {kind}")



def render_current_block(current: Dict[str, Any]) -> str:

    conds = [render_condition(c) for c in current["conditions"]]

    joiner = f" {current['combinator']} " if current.get("combinator") else " "

    return f"(Current transaction where {joiner.join(conds)})"



def render_history_block(history: Dict[str, Any]) -> str:

    w = history["window"]

    if w["kind"] == "WITHIN":

        win_str = f"Transactions within {w['value']} {w['unit']}"

    elif w["kind"] == "SAME_DAY":

        win_str = "Transactions for the same day"

    elif w["kind"] == "SAME_MONTH":

        win_str = "Transactions for the same month"

    else:

        win_str = "Transactions after the last declined transaction"



    filter_str = ""

    if history.get("filter"):

        f_conds = [render_condition(c) for c in history["filter"]["conditions"]]

        f_join = f" {history['filter']['combinator']} " if history["filter"].get("combinator") else " "

        grp = history["grouping"]

        filter_str = f" where {f_join.join(f_conds)} {grp['direction']} {grp['attribute']}"



    aggs = history["aggregations"]

    agg_parts = [f"{a['metric']} {a['comparator']} {a['value']}" for a in aggs["checks"]]

    agg_join = f" {aggs['combinator']} " if aggs.get("combinator") else " "

    return f"({win_str}{filter_str} should have {agg_join.join(agg_parts)})"



def render_dsl(ir: Dict[str, Any]) -> str:

    shape = ir["shape"]

    if shape == "CURRENT_TXN":

        return render_current_block(ir["current"])

    elif shape == "HISTORY_TXN":

        return render_history_block(ir["history"])

    elif shape == "NESTED_CURRENT_AND_HISTORY":

        return f"{render_current_block(ir['current'])} AND {render_history_block(ir['history'])}"

    raise ValueError(f"Unknown shape: {shape}")
