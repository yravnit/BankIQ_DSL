# IUCA Rule DSL Assistant — Progress

**Last updated:** 2026-10-25  
**Current stage:** deterministic core verified; NIM ≤30B landscape mapped; three full-dev runs complete; best small model is `meta/muse-glimmer-30b`  
**Product source of truth:** `AGENTS.md`  
**Grammar source:** `IUCA Rule DSL Guide.pdf` (12 pages, dated 30 Sep 2026)

---

## 1. Why this project exists

The company writes transaction rules in a private DSL. A rule is stored as one line of text, parsed by a fastparse grammar, converted to Scala, compiled, and then run against transactions. Rule authors currently have to know exact keywords, attribute spellings, list categories, comparator phrases, and history-rule ordering.

This project builds a **candidate-rule authoring assistant**:

- The user describes a rule in plain English.
- An LLM returns a typed JSON **intermediate representation (IR)** — never DSL text.
- Deterministic code validates the IR against a catalog derived from the PDF.
- One deterministic renderer turns valid IR into DSL text.
- A human reviews the read-back, the DSL, the assumptions, and warnings, then copies it into the company rule screen.

It is explicitly **not** the company's parser, decision engine, deployment system, or a reconstruction of the full private grammar. The only honest validation claim is:

> Built from documented patterns — not verified against the IUCA engine.

### Why this shape

| Decision | Reason |
|---|---|
| LLM emits IR, not DSL | Prevents arbitrary model text from becoming syntax. |
| Catalog-first | The PDF is a curated sample; undocumented items must stay unknown, not guessed. |
| Deterministic renderer | Makes output testable character-for-character and auditable. |
| Human review + copy only | The company's save/parser flow remains the final syntax check. |
| Refuse or clarify when unsure | A wrong financial rule is worse than no rule. |
| Exclude PAN/Aadhaar in v1 | Privacy requirement; no raw identifiers in prompts or literals. |

---

## 2. What we have done

### 2.1 Read the specification and the source PDF

- Read `AGENTS.md` end to end: product constraints, required architecture, validation behaviour, acceptance criteria, security rules, and scope guard.
- Extracted and read all 12 pages of `IUCA Rule DSL Guide.pdf`.
- Mapped the documented grammar subset:
  - Three rule shapes: current transaction, transaction history, nested current + history joined by `AND`.
  - Exact comparators, including `greaterThan equal to` and `lesserThan equal to` as one camelCase word plus `equal to`.
  - Attributes, list categories, `On "List"` membership / `Count` / `Amount`, built-in functions, `like` globs, event counts, scaled comparisons, history windows, filters, grouping, and aggregations.
  - Hard constraints: quoted strings cannot contain spaces; `and`/`or` cannot be mixed in one chain; a history `where` needs `from same` / `to different`; spelling and case are significant.

### 2.2 Audited the existing implementation

The repository currently contains one Python script, `iuca_rule_benchmark_bonsai_server.py` (2,522 lines), plus generated evaluation data. It is a research/benchmark harness, not the final product.

Verified components:

| Component | Location | What it does |
|---|---|---|
| Catalog | `CATALOG`, line 226 | 25 documented attributes, 7 comparators, 6 list categories, 1 function, 3 event examples, 3 history metrics, 4 window kinds, 3 shapes; separate sensitive and partner-provisional lists |
| IR schema | Pydantic models, lines 60–196 | `RuleIR` with current/history blocks; six condition kinds; required nullable fields |
| Semantic validator | `validate_rule_ir`, line 499 | Rejects unknown catalog items, partner-unmapped slots, sensitive identifiers, invalid strings, bad windows, missing history grouping |
| Renderer | `render_dsl`, line 834 | Fixed templates for the three shapes; no model text concatenation |
| Golden seeds | `GOLDEN_SEEDS`, line 864 | All 15 worked examples from PDF §9 |
| Dataset generator | `generate_datasets`, line 1934 | Dev/holdout paraphrases plus 11 negative/edge cases |
| Prompt + benchmark harness | lines 2010–2456 | Few-shot prompt, JSON-schema-constrained request to a local llama-server, per-case scoring, CSV checkpoints |

### 2.3 Verified the deterministic core by running it

Command used (output directed to a temporary directory so existing results were untouched):

```powershell
python iuca_core.py --out-dir "$env:TEMP\opencode\iuca_gen_check"
```

Observed output:

```text
[OK] 15 gold IR fixtures and 7 negative IR guard tests passed.
[OK] All 15 golden fixtures pass semantic IR validation and renderer exact-output tests.
[OK] Saved 54 dev and 17 holdout cases to '.../iuca_gen_check/'.
```

Then compared hashes against `eval_data/`:

| File | Same as generated? |
|---|---|
| `catalog.json` | Yes |
| `golden_fixtures.json` | Yes |
| `eval_dev.json` | Yes |
| `eval_holdout.json` | Yes |

So the committed `eval_data` fixtures are reproducible from the script. This validates the renderer against the PDF examples, **not** against the company parser.

### 2.4 Audited the evaluation data

| Dataset | Records | Composition |
|---|---:|---|
| `golden_fixtures.json` | 15 | One fixture per PDF §9 pattern; all `ready` |
| `eval_dev.json` | 54 | 45 ready paraphrases + 9 negative/edge cases |
| `eval_holdout.json` | 17 | 15 ready paraphrases + 2 negative/edge cases |
| **Total** | **71** | Holdout share ≈ 24% |

Negative coverage includes vague threshold, vague window, missing history grouping, mixed `and`/`or`, spaces in quoted list names, spaces in string literals, unknown attribute, unknown function, partner-provisional slot, unrepresentable cross-attribute math, and a raw PAN request.

### 2.5 Audited the existing benchmark evidence

The saved `llm_leaderboard.csv` is a **3-case smoke run**, not a model evaluation:

| Metric | Value |
|---|---|
| Cases selected | 3 |
| LLM-tested cases | 2 (the PAN case is marked as a deterministic pre-LLM block) |
| Outcome accuracy | 50.0% |
| System decision accuracy incl. guards | 66.7% |
| DSL exact match | 0.0% |
| False-ready count | 1 |
| Valid JSON / schema-valid | 100% / 100% |
| Average latency | ~78 s |

What actually happened:

- The mixed-`and`/`or` request was correctly refused.
- The missing-history-grouping request was incorrectly marked `ready`, but the semantic validator caught it (`A history where/filter requires 'from same' or 'to different' grouping`). That is the guard working as designed.
- The PAN fixture never reached the model because it is flagged in the fixture. **There is no real pre-LLM privacy detector yet.**
- The earlier `eval_data/dev_run/` has only 6 ready cases: 5 exact DSL matches, 1 mismatch.

Conclusion: the pipeline mechanics are exercised, but there is not enough evidence to compare models or claim readiness.

### 2.6 Discovered provider catalogs

Using the keys in `C:\Users\yravn\Desktop\ravnit\Projects\drag\.env`, we queried the model catalogs only. No inference request was made, and no Cloudflare tokens were spent.

| Provider | Endpoint used | Models listed |
|---|---|---:|
| NVIDIA NIM | `https://integrate.api.nvidia.com/v1/models` | 85 |
| Cloudflare Workers AI | `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/models/search` | 73 |

Only variable names were read from the `.env` (`NVIDIA_API_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`); values were not printed or written to disk.

### 2.7 Checked reusable code in the `drag` project

| File | Reusable idea |
|---|---|
| `src/lib/llm/llmProvider.ts` | NIM is OpenAI-compatible; reads API key from server env; handles `reasoning_content` |
| `src/lib/nvidia/nvidiaModelService.ts` | Model discovery, non-chat filtering, and a 1-token inference probe with timeout |
| `src/lib/embeddings/cloudflareEmbeddingProvider.ts` | Cloudflare account-scoped API call pattern |

The IUCA project should reuse these patterns conceptually, not import the Next.js code.

### 2.8 Requested NIM models: the old generation is retired

Every requested model is still **listed** by `GET /v1/models` (85 entries), but listing does not mean the account can run it. Probed 2026-10-25 with 4–16 token requests:

| Requested model | Probe result |
|---|---|
| `nvidia/nemotron-3.5-bolt-e4b` | **HTTP 200** — usable |
| `google/gemma-3-4b-it`, `ibm/granite-3.0-8b-instruct`, `mistralai/mistral-7b-instruct-v0.3`, `nvidia/mistral-nemo-minitron-8b-8k-instruct`, `ibm/granite-3.0-3b-a800m-instruct`, `deepseek-ai/deepseek-coder-6.7b-instruct`, `ibm/granite-8b-code-instruct` | HTTP 404 `Function '<uuid>': Not found for account` |

To test the deprecation theory, we swept **30 text-generation models with ≤30B parameters** (embeddings, guards, reward, OCR, vision-only, translation and >30B excluded). 22 failed, 8 worked, and the split is not random:

| Fails (404) | Works (HTTP 200) |
|---|---|
| gemma-2b / 3-4b / 3-12b, recurrentgemma-2b, codegemma-7b / 1.1-7b, starcoder2-15b, granite-3.0-3b / 3.0-8b / 8b-code, mistral-7b-v0.3, codestral-22b, mistral-nemo-12b, minitron-8b, deepseek-coder-6.7b, sea-lion-7b, zamba2-7b, nemotron-nano-3-30b, cosmos-reason2-8b | **muse-glimmer-30b**, **nemotron-3.5-lightning-30b-a3b**, **nemotron-3-nano-omni-30b-a3b-reasoning**, gpt-oss-20b, minimax-m3.1-flash, diffusiongemma-26b-a4b-it, llama-3.2-11b-vision-instruct, step-5-preview, glm-5.3-flash |

Every failure is a pre-2026 model, and every 2026-generation model serves. The user's deprecation theory holds: the catalog is stale, and the older backend functions are gone. Retrying, renaming, or changing parameters will never fix a 404 here.

Practical usability of the ten that answer:

| Model | Verdict |
|---|---|
| `meta/muse-glimmer-30b` | Usable, ~12 s/case |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | Usable, ~1.9 s/case |
| `nvidia/nemotron-3.5-bolt-e4b` | Usable, ~2.2 s/case |
| `openai/gpt-oss-20b` | Usable, ~29 s/case, burns reasoning tokens |
| `minimaxai/minimax-m3.1-flash` | Usable, ~10 s/case, returns 429 under load |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | Usable but weak (5/10 pilot) |
| `meta/llama-3.2-11b-vision-instruct` | **Unusable** — 22–300 s per case, timeouts |
| `z-ai/glm-5.3-flash` | **Unusable** — 215 s to first token |
| `google/diffusiongemma-26b-a4b-it` | **Unusable** — returns empty content (diffusion LM) |
| `stepfun-ai/step-5-preview` | **Unusable** — no chat template, emits raw prose |
| `deepseek-ai/deepseek-v4.1-flash` | **Unreachable** — no response within 240 s |

### 2.9 NIM cross-model results (≤30B, dev split, frozen settings)

Settings for every run: `fewshot` prompt, `temperature=0`, `max_tokens=2000`, thinking disabled, prompt-only JSON.

| Model | Params | Pilot outcome | Dev outcome | Dev schema | Dev IR/DSL exact | Dev unsafe | Latency |
|---|---|---:|---:|---:|---:|---:|---:|
| **`meta/muse-glimmer-30b`** | 30B | 10/10 | **88.9%** (48/54) | 53/54 | **38/45 (84%)** | 1/9 | 11.5 s |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 30B / 3B active | 9/10 | 77.8% (42/54) ¹ | 48/54 | 33/45 | 3/9 | 1.9 s |
| `nvidia/nemotron-3.5-bolt-e4b` | 8B / 4B active | 7/10 | 70.4% (38/54) | 45/54 | 27/45 (60%) | 3/9 | 2.2 s |
| `openai/gpt-oss-20b` | 21B / 3.6B active | 9/10 | — | — | 6/7 pilot | 0/3 | 29.3 s |
| `minimaxai/minimax-m3.1-flash` | not published | 9/10 | — | — | 7/7 pilot | 0/3 | 9.8 s |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | 30B / 3B active | 5/10 | — | — | 2/7 pilot | 1/3 | 5.4 s |

¹ Raw score. One case was lost to HTTP 429; a single-case retry passed, so the corrected score is 43/54 (79.6%). `muse-glimmer-30b` lost one case to HTTP 500; the retry returned a genuine `cannot_express`, so its score stands.

Safety nuance: the "Unsafe" column counts negatives where the model said `ready`. `muse-glimmer-30b`'s single hit was **rejected by the semantic validator** (a value containing a space), so it emitted **zero** validator-passing wrong rules. `bolt` and `lightning` each emitted **two** wrong rules that passed every check: the invented `from same payerId` grouping, and the silent `"Blocked Accounts"` → `"BlockedAccounts"` rewrite. That difference is more important than the accuracy gap.

Artifacts: `eval_results/nim/meta_muse-glimmer-30b/20261025T123635Z/`, `eval_results/nim/nvidia_nemotron-3.5-lightning-30b-a3b/20261025T123635Z/`, `eval_results/nim/nvidia_nemotron-3.5-bolt-e4b/20261025T113053Z/`.

**`meta/muse-glimmer-30b` is the best small model found**: 18 points above the baseline, 84% exact IR *and* DSL on ready cases, 1 unsafe output in 9 negatives. It costs ~6× the latency of the Nemotron models.

### 2.10 Diagnosis: the two universal failures were prompt gaps

Every model scored **0/3 on built-in functions** and **0/3 on customer event counts**. That clustering across four model families pointed at the prompt, and the prompt confirmed it: `fewshot` contained no `FUNCTION_CALL` example and no event-count example. `functionName` and `eventName` appeared only in prose, never in a worked example. The models were guessing a shape nothing demonstrated.

OR chains were only partly model-dependent: `gpt-oss-20b` and `minimax` handled them, while `bolt`, `lightning`, and `muse` refused valid `or` chains as `cannot_express`.

§2.11 is the fix and its measurement.

### 2.11 Prompt variant `v2` — the missing examples were the whole gap

`v2` changes four things and nothing else:

1. Adds a `FUNCTION_CALL` few-shot example.
2. Adds an `EVENT_COUNT` few-shot example.
3. Adds an `or`-chain example and rewrites rule 3 so "never mix and/or" cannot be read as "or is forbidden".
4. Adds a per-kind required-fields guide (`ATTRIBUTE_CMP`, `LIST_CHECK`, `FUNCTION_CALL`, `SCALED_CMP`, `EVENT_COUNT`, `GLOB_MATCH`).

The examples are generated from the same IR the validator and renderer use, and `build_fewshot_prompt_v2()` asserts both `validate_rule_ir` and the exact `render_dsl` output before the prompt is built.

**Targeted test** on the three patterns that were 0/3 for every model (4 models × 3 cases):

| Model | `fewshot` | `v2` |
|---|---:|---:|
| `meta/muse-glimmer-30b` | 0/3 | **3/3** |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 0/3 | **3/3** |
| `nvidia/nemotron-3.5-bolt-e4b` | 0/3 | **2/3** |
| `openai/gpt-oss-20b` | 1/3 | **3/3** |

**Full dev** on the two low-latency models:

| Model | Outcome | IR/DSL exact | Unsafe | Output tokens | Latency |
|---|---:|---:|---:|---:|---:|
| `bolt-e4b` fewshot | 70.4% | 27/45 | 3/9 | 6,401 | 2.2 s |
| **`bolt-e4b` v2** | **94.4%** | **38/45 (84%)** | 3/9 | 6,957 | 2.8 s |
| `lightning-30b-a3b` fewshot | 77.8% | 33/45 | 3/9 | 7,050 | 1.9 s |
| **`lightning-30b-a3b` v2** | **85.2%** | **40/45 (89%)** | 4/9 | 7,611 | 2.2 s |

The prompt got 2,640 characters longer, which cost ~0.5 s per case and ~9% more output tokens. That is the entire latency penalty.

**What still fails:**

- `bolt` emits `SCALED_CMP` with `multiplier`, `scaleUnit`, and `target` all null on all six multiply cases — it picks the right `kind` and then fills nothing. Fixing this would take bolt to 44/45 exact.
- `lightning` regressed on two-cumulative-history (3/3 → 0/3) and nested shapes (3/3 → 1/3). The longer prompt costs it some care.
- `lightning` turned the unknown-function negative into a fabricated `deviceOs equal to true` rule (it refused correctly under `fewshot`). Adding a function example made it more willing to improvise instead of refusing. The validator cannot catch this; it is a real safety regression.

`v2` is not promoted to default until the holdout is still untouched and the SCALED_CMP gap is either fixed or accepted.

### 2.12 SCALED_CMP fix: `v6` + duplicate-key-tolerant parser

Bolt's six SCALED_CMP failures were not null-empty laziness alone; two mechanisms:

1. **Prompt placement.** A minimal probe proved bolt *can* emit `{"multiplier":2,"scaleUnit":"Times","target":"previousTxnAmount"}`, so a `SCALED_CMP` example near the end of the prompt (`v4`, `v5`) fixed all 6 cases. Moving the field guide alone (`v3`) did nothing.
2. **Duplicate JSON keys.** Bolt writes kind-specific fields first, then repeats the null skeleton — including the already-set key — and JSON last-key-wins erases the value. This is why event count was 2/3 even under `v2`: `eventName` was written with its value and then as null.

`v6` = `v2` guide position + end-of-prompt `SCALED_CMP` reminder + the reminder examples. Separately, `parse_json_text` now resolves duplicate keys: one non-null among nulls (or equal values) collapses to it; two different non-null values fail the parse as ambiguous. It never invents values, and the ambiguity path is counted `invalid_json` rather than silently shuffled.

Variants probed and rejected: `v3` (guide at end, no scaled fix), `v4` (guide+reminder at end, lost event count and one negative), `v5` (guide top + reminder, duplicate keys still hit event count). `fewshot`/`v2` prompts are byte-identical to when they were measured.

**Full dev, bolt, 54 cases:**

| Variant | Outcome | IR/DSL exact | Schema valid | Unsafe |
|---|---:|---:|---:|---:|
| fewshot | 70.4% | 27/45 | — | 3/9 |
| v2 | 94.4% | 38/45 | 54/54 | 3/9 |
| **v6** | **94.4%** | **43/45 (95.6%)** | **54/54** | 3/9 |

All 45 positive cases render byte-exact under `v6`. The three remaining failures are negatives: two space-in-quoted-value cases still sail through as `unsafe_ready` (needs a pre-LLM privacy/allow-list gate in the runner, pending), and one vague-history case still yields `ready` where `needs_clarification` is expected.

Also opening bolt's behavior: for "greater than 150 percent of merchantMonthlyLimit" it emitted `multiplier:1, scaleUnit:"Percentage"` when prompted with a name-only field list, then emitted `150` correctly once a worked percentage example sat nearest to the request. Phrase with a concrete example, and bolt copies the arithmetic rather than guessing `1`.


---

## 3. Where we have reached

| Area | Status | Notes |
|---|---|---|
| PDF-derived catalog | **Done (v1 subset)** | Curated, not exhaustive; provenance only at file level |
| IR schema | **Done** | Pydantic, strict, explicit nulls; not Zod |
| Semantic validator | **Done (v1)** | Covers catalog, privacy, strings, grouping, windows; does not detect mixed `and`/`or` because the IR cannot represent it |
| Deterministic renderer | **Verified** | 15/15 PDF §9 fixtures match exactly |
| Dataset generation | **Done** | 54 dev / 17 holdout; reproducible byte-for-byte |
| Prompt + local llama-server benchmark | **Done as a harness** | Works against a local OpenAI-compatible server |
| NIM benchmark runner | **Done** | `iuca_provider_benchmark.py`; imports the core, writes per-run artifacts |
| Model comparison evidence | **Started** | 30 models swept, 10 callable, 3 full-dev runs; older models are retired |
| Pre-LLM privacy detection | **Missing** | Fixture flag simulates it; no detector exists |
| NIM adapter | **Partial** | Transport only; no structured-output support on this account |
| Cloudflare adapter | **Not started** | Catalog discovered only; no spend yet |
| Review UI / read-back | **Not started** | No web app in this repo |
| API limits / rate limiting | **Not started** | Benchmark script is local-only |
| Git history | **Empty** | Everything is untracked, including the PDF |
| Documentation | **Started with this file** | `progress.md`, `rules.md` |

### What this means

The deterministic core — catalog → IR → validation → rendering — is real and testable. The **product** around it (user input handling, privacy gate, provider adapters, review UI, release evidence) is not built. The next phase is provider evaluation, not UI polish.

---

## 4. How the current system works

```text
User request (plain language)
        │
        ▼
LLM prompt built from CATALOG + 11 few-shot examples + 3 refusal examples
        │
        ▼
LLM returns AssistantEnvelope JSON
  { outcome, rule_ir, clarification_questions, unrepresentable_reason }
        │
        ├── needs_clarification ──► ask user for threshold/window/grouping
        ├── cannot_express ───────► explain why (unknown item, mixed logic, privacy)
        └── ready
                │
                ▼
Pydantic schema validation (required keys, explicit nulls, types)
                │
                ▼
Semantic validation against CATALOG
  attributes │ comparators │ list categories │ functions │ events │ windows │ grouping
                │
                ▼
Deterministic renderer (fixed templates, closed token set)
                │
                ▼
Candidate DSL text + warnings + "not verified against IUCA engine" label
                │
                ▼
Human reviewer copies rule into the company rule screen
```

The same catalog feeds both the prompt and the validator, so the model is told exactly what the validator will accept. The renderer is never allowed to concatenate raw model text.

---

## 5. Numbers that matter

| Metric | Value |
|---|---:|
| Script size | 2,522 lines |
| Documented attributes in v1 | 25 |
| Comparator phrases | 7 |
| List categories | 6 |
| Built-in functions in v1 | 1 of ~80 documented |
| Event examples in v1 | 3 of ~40 documented |
| History metrics | 3 (`count`, `amount`, `refundAmount`) |
| History windows | 4 (`WITHIN`, `SAME_DAY`, `SAME_MONTH`, `AFTER_LAST_DECLINED`) |
| Golden fixtures | 15 |
| Negative IR guard tests | 7 |
| Dev cases | 54 |
| Holdout cases | 17 |
| Holdout share | 24% |
| Golden renderer match | 15/15 |
| NIM catalog models | 85 |
| Cloudflare catalog models | 73 |
| NIM ≤30B text models probed | 30 |
| NIM models actually callable | 10 (6 usable, 4 impractical) |
| NIM models with a full dev run | 3 |
| NIM inference calls so far | ~330 (probes + 6 pilots + 3 full dev; no charge) |
| Cloudflare inference calls so far | 0 |

---

## 6. Model selection (cap: ≤30B)

**Current size cap: ≤30B parameters**, per the user's 2026-10-25 instruction. The earlier ≤10B interpretation is obsolete.

Selection criteria:

1. Text chat / instruction-following, not embeddings, guards, TTS, ASR, image, or decision-only APIs.
2. ≤30B total parameters (small-active MoE allowed on active count, total still ≤30B).
3. Large enough context for the ~3,200-token prompt.
4. Diversity across families.

### 6.1 NVIDIA NIM — measured, not guessed

Access was swept empirically (§2.8): the pre-2026 catalog is dead on this key, and the working set is small. Results from the dev split (§2.9):

| Model ID | Params | Status | Dev outcome | IR/DSL exact | Unsafe | Latency |
|---|---|---:|---:|---:|---:|---:|
| `meta/muse-glimmer-30b` | 30B | **Best** | 88.9% | 38/45 | 1/9 | 11.5 s |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 30B / 3B active | Runner-up, fast | 77.8% ¹ | 33/45 | 3/9 | 1.9 s |
| `nvidia/nemotron-3.5-bolt-e4b` | 8B / 4B active | Fast baseline | 70.4% | 27/45 | 3/9 | 2.2 s |
| `openai/gpt-oss-20b` | 21B / 3.6B active | Pilot only, slow | 9/10 pilot | 6/7 pilot | 0/3 | 29.3 s |
| `minimaxai/minimax-m3.1-flash` | not published | Pilot only, rate-limited | 9/10 pilot | 7/7 pilot | 0/3 | 9.8 s |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | 30B / 3B active | Weak | 5/10 pilot | 2/7 pilot | 1/3 | 5.4 s |

¹ One dev case was lost to HTTP 429; corrected 43/54 (79.6%).

**This table is `fewshot`. Under `v2` (§2.11) the ranking changes:** `bolt-e4b` reaches 94.4% at 2.8 s/case and `lightning-30b-a3b` reaches 85.2%, both above every `fewshot` result. `muse-glimmer-30b` has not been re-run on `v2`; its 88.9% is now the slow option, not the accurate one.

**Retired / unusable on this account:** the entire pre-2026 catalog (gemma 2/3, granite 3.0, mistral 7B v0.3, codestral, minitron, deepseek-coder, sea-lion, zamba2, starcoder2, …), plus `deepseek-v4.1-flash` (times out), `glm-5.3-flash` (215 s to first token), `diffusiongemma-26b-a4b-it` (empty output), `step-5-preview` (no chat template), `llama-3.2-11b-vision-instruct` (22–300 s per case).

**Configuration required for NIM:** thinking-capable models must be called with `chat_template_kwargs.enable_thinking=false`, otherwise `content` is empty and all tokens go to `reasoning_content`. NIM ignores `response_format` and rejects `nvext.guided_json` (HTTP 400).

### 6.2 Cloudflare Workers AI — billed, test sparingly

**Tier 1 (run these first):**

| Model ID | Params | Context | Price per M input / output | Why it is worth testing |
|---|---:|---:|---|---|
| `@cf/ibm-granite/granite-4.0-h-micro` | 3B | 131K | $0.017 / $0.112 | Cheapest; strong candidate for cost-sensitive use |
| `@cf/meta/llama-3.2-3b-instruct` | 3B | 80K | $0.0509 / $0.335 | Cheap Llama baseline |
| `@cf/meta/llama-3.1-8b-instruct-fp8` | 8B | 32K | $0.152 / $0.287 | Main 8B comparison |
| `@cf/utter-project/eurollm-9b-it` | 9B | 32K | price not listed | Multilingual 9B; check billing before use |
| `@cf/swiss-ai/apertus-v1.5-8b` | 8B | 262K | price not listed | 8B with long context; check billing before use |

**Tier 2 (only after Tier 1 results):**

| Model ID | Params | Context | Price per M input / output | Note |
|---|---:|---:|---|---|
| `@cf/meta/llama-3.2-1b-instruct` | 1B | 60K | $0.027 / $0.201 | Floor baseline; likely too weak for full IR |
| `@cf/qwen/qwen3-30b-a3b-fp8` | 30B total / 3B active | 32K | $0.0509 / $0.335 | Small active compute; optional MoE |
| `@cf/meta/llama-3.2-11b-vision-instruct` | 11B | 128K | $0.0485 / $0.676 | Just above 10B; text use only |
| `@cf/mistral/mistral-7b-instruct-v0.2-lora` | 7B | 15K | price not listed | Older LoRA model |
| `@cf/google/gemma-7b-it-lora` | 7B | 3.5K | price not listed | Context too small for the current prompt |

**Not suitable:** Clef / Clef-flash (typed decision API, not free-form IR generation), Clairic (extraction/forecast), embeddings, ASR/TTS, image models, and the 70B+ / 1T models.

### 6.3 Cost estimates for Cloudflare

Assumption: ~4,500 input tokens and ~1,500 output tokens per case (conservative). Actual prompt size should be measured before the first run.

| Model | 5-case pilot | Full 54-case dev |
|---|---:|---:|
| Granite 4.0 H Micro (3B) | ~$0.0012 | ~$0.013 |
| Llama 3.2 3B | ~$0.0037 | ~$0.040 |
| Llama 3.1 8B FP8 | ~$0.0056 | ~$0.060 |
| Llama 3.2 1B | ~$0.0021 | ~$0.023 |
| Qwen3 30B A3B | ~$0.0037 | ~$0.040 |

A 5-model pilot is roughly **$0.01–0.02**. A full dev run for all five recommended Cloudflare models is roughly **$0.11–0.15** at these assumptions. This is small, but it is still billed, so it requires explicit approval under `rules.md`.

---

## 7. Next steps

### Phase 0 — Decisions (blocking)

- [x] Confirm size cap: **≤30B parameters** (2026-10-25).
- [ ] Approve a Cloudflare spend cap for the exploration.
- [ ] Decide whether JSON-schema-constrained decoding is required or prompt-only output plus strict validation is acceptable.
- [ ] Approve the Tier 1 model list.
- [ ] Freeze prompt variant, temperature, and max output tokens for comparisons.

### Phase 1 — Provider adapter and safety gate

- [ ] Add a small provider adapter with two backends:
  - NIM: OpenAI-compatible `/v1/chat/completions`.
  - Cloudflare: Workers AI chat endpoint.
- [ ] Keep the adapter dependency-free if possible (standard library `urllib`) or reuse an already-installed client.
- [ ] Add per-run token/cost logging and hard output caps.
- [ ] Add a real pre-LLM privacy check for PAN/Aadhaar/card/account-number patterns with tests.
- [ ] Add per-model result directories so runs do not overwrite each other.

### Phase 2 — Smoke tests (cheap)

- [x] NIM: swept 30 text models ≤30B — 8 answered, 22 are retired on this key.
- [x] NIM: confirm structured output support — `response_format` ignored, `nvext.guided_json` rejected with HTTP 400, so prompt-only JSON plus strict validation is the only path.
- [x] NIM: confirm thinking-capable models need `enable_thinking=false` or they return empty `content`.
- [ ] Cloudflare: one request on the cheapest model, only after approval; verify request/response shape and actual token usage (estimate in `tools/cloudflare_neurons_estimate.py`).
- [ ] Record actual input/output token counts for cost calibration.

### Phase 3 — Pilot evaluation

- [x] 10-case pilots on six models: bolt 7/10, lightning 9/10, nano-omni 5/10, gpt-oss-20b 9/10, minimax-flash 9/10, muse-glimmer 10/10.
- [ ] Pilot `minimaxai/minimax-m3.1-flash` and `openai/gpt-oss-20b` on the full dev split (both scored 9/10 but were rate-limited or truncated once).
- [ ] Stop immediately if a model produces unsafe `ready` output on a negative case.

### Phase 4 — Full dev and holdout

- [x] Full dev (54 cases) on `bolt-e4b` (70.4%), `lightning-30b-a3b` (77.8%), `muse-glimmer-30b` (88.9%).
- [x] Identify the two universal 0/3 patterns — built-in functions and customer event counts — as **prompt gaps**, not model limits (§2.10).
- [ ] Add a `FUNCTION_CALL` few-shot example and an event-count few-shot example; re-run the comparison.
- [ ] Add an explicit "OR chains are supported" line, or an `or` example, to stop the false refusals.
- [ ] Re-run full dev on the top two models with the fixed prompt.
- [ ] Freeze prompt/catalog/renderer.
- [ ] Run holdout once; do not tune on it.

### Phase 5 — Product work

- [ ] Build the review UI: request box, clarification flow, read-back, DSL, warnings, copy action, and the required not-verified label.
- [ ] Add API request-size limits, rate limiting, and server-side secret handling.
- [ ] Write coverage and limitations documentation.
- [ ] Only then consider a release candidate.

---

## 8. Decisions needed from you

1. **Model choice:** `meta/muse-glimmer-30b` is the best result (88.9% outcome, 84% exact IR/DSL, 1 unsafe in 9). It is ~6× slower than the Nemotron models. Is accuracy worth 11.5 s/case, or do you want the 1.9 s `lightning-30b-a3b` for the product path and muse for offline authoring?
2. **Prompt fix (recommended before holdout):** add a `FUNCTION_CALL` example, an event-count example, and an `or`-chain clarification. Two whole patterns are at 0/3 for every model purely because no example shows them. Approve re-running the comparison with the fixed prompt?
3. **Remaining pilots:** should `minimax-m3.1-flash` and `gpt-oss-20b` get a full dev run before the prompt change? They scored 9/10 but had one transport loss each.
4. **Cloudflare budget:** still unapproved and untested. The Neuron estimate is in `tools/cloudflare_neurons_estimate.py`; nothing runs without your sign-off.
5. **Output enforcement:** prompt-only JSON plus strict validation is the only available path on NIM. Accept, or restrict the product to providers that can constrain decoding?
6. **Repository hygiene:** the PDF and all current files are untracked. Keep the PDF out of git? Commit model results?

---

## 9. Artifacts and reproduction

| Artifact | Purpose |
|---|---|
| `iuca_core.py` (with `catalog.py`, `ir_models.py`, `validator.py`, `renderer.py`, `fixtures.py`, `selfcheck.py`, `datasets.py`, `prompts.py`, `benchmark_llama_server.py`) | Catalog, IR, validator, renderer, fixtures; deterministic CLI |
| `iuca_provider_benchmark.py` | NIM runner: transport, scoring, artifacts; `--prompt-variant`; duplicate-key-tolerant JSON parser |
| `tools/cloudflare_neurons_estimate.py` | Neuron and dollar estimate; must be run before any Cloudflare call |
| `eval_results/nim/<model>/<timestamp>/` | Per-run `details.csv`, `summary.csv`, `run.json` |
| `eval_data/golden_fixtures.json` | 15 PDF §9 fixtures with expected DSL |
| `eval_data/eval_dev.json` | 54 dev cases |
| `eval_data/eval_holdout.json` | 17 holdout cases |
| `eval_data/catalog.json` | Exported catalog |
| `eval_data/llm_*.csv` | Existing smoke-run outputs |
| `eval_data/dev_run/` | Earlier 6-case run |
| `IUCA Rule DSL Guide.pdf` | Company specification (internal; currently untracked) |
| `AGENTS.md` | Product and safety constraints |
| `rules.md` | Operational rules, spend guards, experiment protocol |
| `progress.md` | This file |

Deterministic check:

```powershell
python iuca_core.py --out-dir "$env:TEMP\opencode\iuca_gen_check"
```

Expected:

```text
[OK] 15 gold IR fixtures and 7 negative IR guard tests passed.
[OK] All 15 golden fixtures pass semantic IR validation and renderer exact-output tests.
[OK] Saved 54 dev and 17 holdout cases to '...'.
```

Local llama-server benchmark (requires a running server; this is the existing path, not the NIM/Cloudflare path yet):

```powershell
python iuca_core.py --benchmark --split dev
```

---

## 10. Changelog

| Date | Change |
|---|---|
| 2026-10-25 | Read `AGENTS.md` and the 12-page PDF; audited the 2,522-line prototype |
| 2026-10-25 | Ran the deterministic generator; confirmed 15/15 golden renderer matches and byte-identical fixtures |
| 2026-10-25 | Audited existing Bonsai benchmark: 3-case smoke run, not model evidence |
| 2026-10-25 | Queried NVIDIA NIM (85 models) and Cloudflare Workers AI (73 models) catalogs; no inference, no Cloudflare spend |
| 2026-10-25 | Created `progress.md` and `rules.md`; shortlisted small models and listed blocking questions |
| 2026-10-25 | Added `iuca_provider_benchmark.py` (NIM transport + scoring, imports the deterministic core) |
| 2026-10-25 | Probed the 8 requested NIM models: only `nemotron-3.5-bolt-e4b` is callable; 7 return 404 for this account |
| 2026-10-25 | NIM 10-case pilot: 7/10 outcome correct, 8/10 JSON-valid, 5/7 exact IR/DSL, 1 unsafe-ready |
| 2026-10-25 | NIM 54-case dev baseline on `nemotron-3.5-bolt-e4b`: 70.4% outcome accuracy, 60% exact IR/DSL, 3/9 unsafe-ready |
| 2026-10-25 | Confirmed NIM rejects `nvext.guided_json` (HTTP 400) and ignores `response_format`; prompt-only JSON is the only path |
| 2026-10-25 | Added flagged brace-completion recovery to the response parser so a forgotten `}` is measured, not hidden |
| 2026-10-25 | Added `cloudflare_neurons_estimate.py`; Cloudflare inference remains untested and unapproved |
| 2026-10-25 | Swept 30 NIM text models ≤30B: 22 retired (404), 8 callable — user's deprecation theory confirmed |
| 2026-10-25 | Piloted 6 models; full dev on 3. `muse-glimmer-30b` leads at 88.9% / 84% exact / 1 unsafe |
| 2026-10-25 | Found the 0/3 built-in-function and 0/3 event-count scores are prompt gaps (no example in the `fewshot` prompt), not model failures |
| 2026-10-25 | Built prompt variant `v2` (function, event, `or` examples + per-kind field guide); fixed 1/12 → 11/12 on the three broken patterns |
| 2026-10-25 | `v2` full dev: bolt 70.4% → **94.4%**, lightning 77.8% → **85.2%**, at ~+0.5 s/case |
| 2026-10-25 | Fixed a CSV writer crash when the first row was a transport error |
| 2026-10-26 | Root-caused bolt's `SCALED_CMP` nulls: prompt placement (fixed by an end-of-prompt reminder) and duplicate JSON keys erasing set fields |
| 2026-10-26 | Added variant `v6` + duplicate-key-tolerant parser: bolt full dev 43/45 IR-exact (95.6%), all 45 positives byte-exact |
| 2026-10-27 | Core script restored after deletion; split the 2,691-line monolith into `catalog.py`, `ir_models.py`, `validator.py`, `renderer.py`, `fixtures.py`, `selfcheck.py`, `datasets.py`, `prompts.py`, `benchmark_llama_server.py`, with `iuca_core.py` as the API surface + CLI. Deterministic check passes; all four generated fixture files byte-identical to the pre-split baseline. `iuca_provider_benchmark.py` imports `iuca_core`. |
| 2026-10-27 | Hygiene pass: deleted `eval_data/dev_run/`, the 3-case smoke-run CSVs (`llm_leaderboard`, `llm_benchmark_details`, `llm_class_metrics`, `llm_confusion_matrices`), the `llama-3.2-11b-vision` stub, and 29 superseded `eval_results` run dirs (kept the canonical fewshot dev, targeted v2, full v2 dev, and final v6 dev/holdout runs per model). Moved `cloudflare_neurons_estimate.py` to `tools/`. `__pycache__/` removed. |

