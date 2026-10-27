# Rules — IUCA Rule DSL Project

Operational rules for this repository. `AGENTS.md` is the product specification; this file governs **how we work**, especially when a mistake costs money, leaks data, or produces a misleading result.

If this file conflicts with `AGENTS.md`, `AGENTS.md` wins.

---

## 1. The one rule that matters most

**Ask before any expensive API call or computational work.**

“Expensive” means any of:

- More than **20 inference requests** in one batch.
- An estimated provider cost above **$0.10**.
- More than **3 models** in one evaluation batch.
- A full dev split (54 cases) or any holdout run.
- A model download, a long local run (>2 minutes), or a new dependency.
- Any use of a paid Cloudflare feature beyond a small approved pilot.

Before spending, state:

1. Provider and exact model ID.
2. Number of cases and split.
3. Estimated input and output tokens per case.
4. Estimated cost, with the price source.
5. Hard cap for the run.
6. Why this run is necessary now.

Wait for approval. Do not “just try one more model” silently.

### Current standing approvals

| Permission | Status |
|---|---|
| NVIDIA NIM inference | Allowed by user; still log and cap batch size |
| Full dev split | Approved for NIM; multiple 54-case runs completed |
| Cloudflare Workers AI inference | **Not yet approved** — catalog listing and estimate only |
| Holdout split | **Approved 2026-10-26** by user, for the final `v6` evaluation (dev + holdout on the four main NIM models); consumed 2026-10-26. Never tune on it again. |
| Model downloads | **Not yet approved** |

---

## 2. Cloudflare safeguards (billed)

Cloudflare Workers AI is treated as billed, even if a free allocation exists.

**Hard gate: no Cloudflare inference call may be made until a written Neuron estimate exists and the user has approved it by name.** The estimate comes from `python tools/cloudflare_neurons_estimate.py` and must state, per model and per run: input/output tokens per case, Neurons consumed, percentage of the 10,000/day free tier, and the dollar equivalent.

- Default: **no inference requests** without explicit approval.
- First probe: **one** request on the cheapest suitable model (Granite 4.0 H Micro or Llama 3.2 1B/3B).
- Pilot: maximum **5 cases per model**, one model at a time.
- Hard cap per pilot: **$0.05** unless the user raises it.
- Hard cap for the whole exploration: **ask the user**; do not assume.
- Never fan out across all 73 catalog models.
- Cap `max_tokens` at the smallest value that can hold a complete IR (start with 2,000).
- Cache identical requests; never pay twice for the same prompt and model.
- Check actual token usage after the first call and re-estimate before continuing.
- Stop immediately on HTTP 402/429, budget exhaustion, or repeated provider errors.
- Do not use the Cloudflare token for anything except the Workers AI endpoints needed for this project.

### Neuron accounting

Billing unit is the **Neuron**, not the dollar. Free tier: **10,000 Neurons/day**, reset 00:00 UTC. Overage: **$0.011 per 1,000 Neurons**.

```text
neurons_per_case =
    (input_tokens  / 1_000_000) * input_neurons_per_million
  + (output_tokens / 1_000_000) * output_neurons_per_million
```

Measured NIM prompt size is ~3,100–3,200 tokens (the same `fewshot` prompt), so use **3,200 input tokens** for the estimate. Observed completions on a small model were 110–197 tokens; budget **200** as the likely case and **2,000** as the `max_tokens` worst case.

Official rates (Workers AI pricing page, fetched 2026-10-25):

| Model | Neurons / M input | Neurons / M output |
|---|---:|---:|
| Granite 4.0 H Micro | 1,542 | 10,158 |
| Llama 3.2 1B | 2,457 | 18,252 |
| Llama 3.2 3B | 4,625 | 30,475 |
| Qwen3 30B A3B | 4,625 | 30,475 |
| Llama 3.1 8B FP8 | 13,778 | 26,128 |
| Llama 3.2 11B Vision | 4,410 | 61,493 |

EuroLLM 9B and Apertus 8B have **no published Neuron rate**. Treat them as unknown, not free, and do not run them.

Reference totals at 3,200 input / 200 output tokens:

| Model | Per case | 5-case pilot | 54-case dev | % of daily free tier (dev) |
|---|---:|---:|---:|---:|
| Granite 4.0 H Micro | 7.0 | 35 | 376 | 3.8% |
| Llama 3.2 1B | 11.5 | 58 | 622 | 6.2% |
| Llama 3.2 3B | 20.9 | 104 | 1,128 | 11.3% |
| Qwen3 30B A3B | 20.9 | 104 | 1,128 | 11.3% |
| Llama 3.1 8B FP8 | 49.3 | 247 | 2,663 | 26.6% |
| Llama 3.2 11B Vision | 26.4 | 132 | 1,426 | 14.3% |

All six models on the full dev split: **~7,340 Neurons (73% of one day's free tier, ~$0.081)**. At the `max_tokens=2000` worst case the same sweep costs ~24,550 Neurons, i.e. it exceeds the daily free tier and is billed. Do not run a multi-model sweep in one day without planning for that.


### Cost formula (dollar view)

```text
estimated_cost =
    (input_tokens  / 1_000_000) * input_price_per_million
  + (output_tokens / 1_000_000) * output_price_per_million
```

Use the prices returned by the Cloudflare catalog. If a model has no listed price, treat it as **unknown**, not free, and ask before using it.

Reference estimates (4,500 input + 1,500 output tokens per case):

| Model | 5 cases | 54 cases |
|---|---:|---:|
| Granite 4.0 H Micro (3B) | ~$0.0012 | ~$0.013 |
| Llama 3.2 3B | ~$0.0037 | ~$0.040 |
| Llama 3.1 8B FP8 | ~$0.0056 | ~$0.060 |
| Llama 3.2 1B | ~$0.0021 | ~$0.023 |

---

## 3. NVIDIA NIM rules

NIM is the preferred exploration provider because the user has allowed its use.

- Still log every run: model ID, case count, tokens, latency, and result path.
- Use 1-token probes to confirm a model is callable before running real cases.
- Keep batches small; do not probe all 85 catalog models at once.
- Respect rate limits; back off on 429 instead of retrying aggressively.
- NIM model listing does not prove a model is enabled for the key; a successful probe does.
- This account cannot call any pre-2026 NIM model. Their IDs stay listed in `/v1/models`, but every call returns 404 `Function … not found for account`. Confirmed across 22 models; the 2026-generation models serve normally.
- NIM does not accept `nvext.guided_json` (HTTP 400) and ignores `response_format`. Prompt-only JSON plus strict validation is the only available path; score malformed JSON as a model failure, not a transport failure.
- Thinking-capable models return empty `content` unless `chat_template_kwargs.enable_thinking=false` is set.

---

## 4. Secrets

- Read keys only from `C:\Users\yravn\Desktop\ravnit\Projects\drag\.env`.
- Never print, log, commit, paste, or screenshot key values.
- Never copy the `.env` file into this repository.
- In docs and issues, write variable names only:
  - `NVIDIA_API_KEY`
  - `CLOUDFLARE_API_TOKEN`
  - `CLOUDFLARE_ACCOUNT_ID`
- Redact `Authorization` headers and full provider error bodies before showing them.
- If a key appears in output accidentally, stop, rotate it, and say so.

---

## 5. Privacy

- Never send raw PAN, Aadhaar, card number, account number, or similar identifiers to any provider.
- A real pre-LLM detector must exist before the product accepts real user descriptions. The current benchmark fixture flag is **not** a detector.
- Synthetic evaluation prompts may contain fake identifiers for testing the detector, but they must be clearly fake and never derived from real people.
- Do not log raw user descriptions by default.
- The v1 policy is refusal, not silent masking: do not rewrite a user’s value and pretend it is the same rule.
- Quoted values must pass the catalog allow-list; never silently sanitize.

---

## 6. Claim boundary

Never state or imply that a generated rule was validated by the company’s IUCA engine.

Required wording in any user-facing output:

> Built from documented patterns — not verified against the IUCA engine.

Allowed claims:

- “Matches the renderer’s output for the PDF §9 examples.”
- “Passed the local catalog and IR checks.”
- “Not parsed by the private IUCA parser.”

Forbidden claims:

- “Validated.”
- “Verified by IUCA.”
- “Production-ready rule.”
- “The engine will accept this.”

---

## 7. Experiment protocol

### Freeze before comparing

Hold these constant across models:

- Catalog version.
- IR schema and validator.
- Renderer.
- Prompt variant (`fewshot` unless the user approves another).
- Temperature (recommend `0.2`).
- Output token cap (recommend `2,000`).
- Dev split.

If a setting changes, start a new comparison; do not mix results.

### Split discipline

- **Dev:** use for smoke tests and model comparison.
- **Holdout:** run only after the prompt, model choice, and renderer are frozen.
- Never tune on holdout.
- Never claim holdout results from a dev run.
- **Holdout is spent (2026-10-26):** the prompt was frozen as `v6` first, then one holdout run per model. Any future prompt or scoring change makes the 2026-10-26 holdout numbers historical; a new holdout would need new cases.

### Run order

1. One-token probe (is the model reachable?).
2. One real case (does it emit valid JSON at all?).
3. Five-case pilot (3 ready + 2 negative).
4. Full dev for the top 2–3 models.
5. Holdout once.

Stop a model early if it:

- emits invalid JSON repeatedly;
- returns `ready` for a negative case;
- drops requested conditions or values;
- cannot fit the prompt in its context window;
- exceeds the approved budget.

### Record every run

Minimum fields:

```text
date
provider
model_id
prompt_variant
split
cases
temperature
max_tokens
input_tokens
output_tokens
estimated_cost
result_path
notes
```

Recommended result path:

```text
eval_results/<provider>/<model-slug>/<YYYY-MM-DD>/
  leaderboard.csv
  details.csv
  run.json
```

Do not overwrite the previous run; each run gets its own directory.

### Score the right things

Report at least:

- Outcome accuracy.
- Schema-valid rate.
- IR exact match.
- DSL exact match.
- Unsafe-ready rate on negatives.
- Valid JSON rate.
- Latency.
- Actual cost.

IR semantic equality matters more than surface DSL equality. A character-perfect DSL string from wrong logic is still wrong.

Three failure modes must be counted separately, because the validator alone cannot see them:

- **Silent value rewrite:** the model changed the user's literal (for example `"Blocked Accounts"` → `"BlockedAccounts"`) and returned `ready`. Count as unsafe.
- **Invented constraint:** the model added a catalogued condition or grouping the user never asked for. Count as unsafe.
- **False refusal:** the model returned `cannot_express` for a documented, representable pattern. Safe, but a coverage loss.

JSON that only needs a missing closing brace is recorded as `json_repaired`, never as valid JSON.

---

## 8. Code and data rules

- Keep the deterministic core single-source: one catalog, one validator, one renderer.
- Provider adapters translate transport only; they must not contain rule logic.
- Do not add a framework for a few HTTP calls. Prefer the standard library or an already-installed client.
- Do not compile generated Scala or call the company parser.
- Edit `GOLDEN_SEEDS` and negative cases, then regenerate; do not hand-edit generated JSON.
- After changing the core, re-run the generator and confirm the expected output still matches.
- Add one runnable check for any new non-trivial logic.
- Keep the PDF out of git unless the user explicitly approves committing an internal document.
- Keep secrets and raw provider errors out of git.
- Do not commit generated results without the user’s approval.

---

## 9. Model selection rules

- **Size cap: ≤30B total parameters** (user instruction, 2026-10-25). Small-active MoE is allowed only if the total stays ≤30B.
- Text chat / instruction-following only. Exclude embeddings, rerankers, guards, safety classifiers, translation-only models, reward models, image/audio models, and typed decision APIs (for example Clef).
- Diversity matters: do not test five near-identical Llama 7B/8B variants and call it a comparison.
- A model is “testable” only after a successful inference probe, not because it appears in `/v1/models`.
- **Retired models are a trap.** The NIM catalog advertises pre-2026 models that every call rejects with 404 `Function … not found for account`. Do not interpret that as a parameter, timeout, or prompt error, and do not report it as a model-quality result. Probe first, and keep the probe log.
- A model that needs more than ~30 s per case is not a candidate for the product path, regardless of accuracy.
- Thinking-capable models must be called with `chat_template_kwargs.enable_thinking=false`. Without it, `content` is empty and the whole budget goes to `reasoning_content`.
- Do not report a 429/500/timeout as a model failure. Retry that single case and label the correction.
- Do not compare scores across different prompts. A prompt change starts a new table.

---

## 10. Questions to answer before the first paid run

1. ~~Size definition~~ — resolved: **≤30B total parameters**.
2. ~~Schema enforcement~~ — resolved: prompt-only JSON plus strict validation (NIM has no constrained decoding on this account).
3. ~~Fairness settings~~ — resolved and frozen: `fewshot`, temperature `0`, `max_tokens=2000`, thinking disabled.
4. **Cloudflare cap:** what is the hard budget for this exploration? Is a 5-case pilot (≈ $0.002 on the cheapest model) approved?
5. **Prompt fix:** approve adding `FUNCTION_CALL`, event-count, and `or`-chain examples, and re-running the comparison?
6. **Git hygiene:** keep the PDF and generated results out of commits?

Until these are answered, do not run Cloudflare inference beyond catalog listing and estimation.

---

## 11. Stop conditions

Stop and ask if:

- the cost estimate exceeds the approved cap;
- a request would send raw personal identifiers;
- the requested change would require inventing catalog entries;
- the result would need a claim of real-engine validation;
- the holdout split would be used for tuning;
- a key or secret appears in output;
- the provider returns unexpected billing or authorization errors;
- the request cannot be represented without changing its meaning.

---

## 12. Current status

| Item | State |
|---|---|
| Catalog listing | Done: NIM 85, Cloudflare 73 |
| NIM inference | **Started**: 30 models swept, 10 callable, 6 usable |
| NIM full dev | Under `v6` (2026-10-26): bolt-e4b 94.4% (IR 43/45), lightning 90.7%, muse-glimmer and gpt-oss pending |
| NIM model comparison | `v6` promoted to default 2026-10-26; `fewshot`/`v2` kept for reproducing earlier runs |
| Cloudflare inference | Not started; **no spend yet** |
| Pre-LLM privacy detector | Missing; the two space-in-quoted-value cases still pass as `unsafe_ready` |
| Provider adapters | NIM transport only; no Cloudflare adapter |
| Holdout evaluation | **Consumed 2026-10-26** under frozen `v6`; bolt 17/17 outcome, 15/15 DSL exact, lightning 15/17 |
| Review UI | Not started |
| Git history | Empty; all files untracked |
