"""Evaluation datasets: deterministic generation + reproducible subset selection."""

import json
import random

from pathlib import Path

from typing import Any, Dict, List

from catalog import CATALOG
from fixtures import GOLDEN_SEEDS, NEGATIVE_AND_EDGE_CASES
from renderer import render_dsl
from validator import expand_ir_for_schema
from selfcheck import validate_static_invariants

RANDOM_SEED = 42

random.seed(RANDOM_SEED)

def generate_datasets(out_dir: str = "eval_data") -> Dict[str, List[Dict[str, Any]]]:

    # Check both halves of the non-LLM core before generating any benchmark data.
    validate_static_invariants()
    for seed in GOLDEN_SEEDS:
        rendered = render_dsl(seed["expected_ir"])
        assert rendered == seed["expected_dsl"], f"Mismatch on {seed['id']}:\nGot:  {rendered}\nWant: {seed['expected_dsl']}"
    print("[OK] All 15 golden fixtures pass semantic IR validation and renderer exact-output tests.")



    dev_records: List[Dict[str, Any]] = []

    holdout_records: List[Dict[str, Any]] = []



    for seed in GOLDEN_SEEDS:

        for idx, text in enumerate(seed["paraphrases"]):

            is_holdout = idx == len(seed["paraphrases"]) - 1

            rec = {

                "id": f"{seed['id']}_p{idx+1}",
                "pattern_id": seed["id"],
                "pattern": seed["pattern"],
                "split": "holdout" if is_holdout else "dev",
                "category": "golden_paraphrase",

                "prompt": text,

                "expected_outcome": seed["expected_outcome"],

                "expected_dsl": seed["expected_dsl"],

                "expected_ir": expand_ir_for_schema(seed["expected_ir"]),

            }

            (holdout_records if is_holdout else dev_records).append(rec)



    for idx, neg in enumerate(NEGATIVE_AND_EDGE_CASES):

        is_holdout = idx % 4 == 3

        rec = {**neg, "pattern_id": neg.get("category", "negative"), "pattern": neg.get("category", "negative"), "split": "holdout" if is_holdout else "dev", "expected_dsl": None, "expected_ir": None}

        (holdout_records if is_holdout else dev_records).append(rec)



    Path(out_dir).mkdir(parents=True, exist_ok=True)

    Path(out_dir, "catalog.json").write_text(json.dumps(CATALOG, indent=2))
    Path(out_dir, "golden_fixtures.json").write_text(json.dumps(GOLDEN_SEEDS, indent=2))

    Path(out_dir, "eval_dev.json").write_text(json.dumps(dev_records, indent=2))

    Path(out_dir, "eval_holdout.json").write_text(json.dumps(holdout_records, indent=2))

    print(f"[OK] Saved {len(dev_records)} dev and {len(holdout_records)} holdout cases to '{out_dir}/'.")

    return {"dev": dev_records, "holdout": holdout_records}



def _select_eval_subset(
    eval_items: List[Dict[str, Any]], max_samples: int, seed: int = RANDOM_SEED
) -> List[Dict[str, Any]]:
    """Reproducible screening subset with broad pattern and outcome coverage.

    Use max_samples=0 for the full split. Small subsets are smoke screens, not final model selection.
    """
    items = list(eval_items)
    if max_samples <= 0 or max_samples >= len(items):
        return items
    rng = random.Random(seed)
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        key = str(item.get("pattern_id") or item.get("category") or "unknown")
        buckets.setdefault(key, []).append(item)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    chosen: List[Dict[str, Any]] = []
    chosen_ids = set()
    # First take one case from each pattern/category where budget permits.
    for key in sorted(buckets):
        if len(chosen) >= max_samples:
            break
        candidate = buckets[key][0]
        chosen.append(candidate)
        chosen_ids.add(candidate["id"])
    # Then ensure outcome classes have representation if the budget permits.
    for outcome in ("ready", "needs_clarification", "cannot_express"):
        if len(chosen) >= max_samples:
            break
        if any(x.get("expected_outcome") == outcome for x in chosen):
            continue
        options = [x for x in items if x.get("expected_outcome") == outcome and x["id"] not in chosen_ids]
        if options:
            candidate = options[0]
            chosen.append(candidate)
            chosen_ids.add(candidate["id"])
    remainder = [x for x in items if x["id"] not in chosen_ids]
    rng.shuffle(remainder)
    chosen.extend(remainder[: max(0, max_samples - len(chosen))])
    chosen_ids = {x["id"] for x in chosen}
    return [x for x in items if x["id"] in chosen_ids]
