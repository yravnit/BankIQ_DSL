# AGENTS.md — IUCA Rule DSL Assistant

## Mission
Build a standalone, human-reviewed assistant that turns a user's plain-language transaction-rule request into a **candidate IUCA DSL rule** from the subset documented in `IUCA Rule DSL Guide.pdf`.

The company PDF is the only company-provided specification. We do not have the private grammar source or the real IUCA parser.

## Non-negotiable constraints
- **Never claim a rule has been validated by the real IUCA engine.** Use the UI label: `Built from documented patterns — not verified against the IUCA engine.`
- Do not invent attributes, functions, list categories, permitted values, partner mappings, or runtime behaviour. Missing/unclear requirements must result in a clarification or refusal.
- Keep source-backed facts separate from engineering policy and inference. Add a PDF page/section reference to catalog entries where possible.
- Do not build a duplicate transaction engine or compile generated Scala. This product generates candidate DSL text only.
- A person must review and copy the rule into the company's rule screen. The company's save/parser flow is the final syntax check.

## Required design
1. **Catalog-first:** maintain a versioned JSON/TypeScript catalog for documented attributes, comparator phrases, list categories, functions, history windows, and supported rule shapes. Record provenance and confidence for each entry (`documented_example`, `documented_list`, `partner_specific_unknown`, etc.).
2. **LLM emits IR, never DSL:** use structured output matching a Zod schema. The intermediate representation (IR) is a typed JSON rule model; the deterministic renderer alone converts IR to DSL.
3. **Validate before rendering:** perform schema validation and semantic checks. Invalid, ambiguous, and unrepresentable requests must not produce a rule.
4. **One renderer:** generate DSL from validated IR using fixed templates and a closed set of grammar tokens. Never concatenate arbitrary model output into syntax.
5. **Human-readable review:** display (a) a read-back of the intended logic, (b) the generated DSL, (c) warnings/assumptions, and (d) the required not-verified label. Provide copy, not automatic submission.
6. **Provider boundary:** keep the LLM provider behind an adapter so the application is not tied to one vendor.

## PDF-derived syntax rules to encode
- Support the three documented shapes: current transaction; transaction history; nested current + history joined by `AND`.
- Use exact catalogued comparator phrases. In particular, `greaterThan equal to` and `lesserThan equal to` are single camelCase words followed by `equal to`.
- Do not mix `and` and `or` in a single condition chain. Use a nested shape only if it is logically equivalent; otherwise refuse or ask for clarification.
- A history rule with a `where` filter must include `from same <attribute>` or `to different <attribute>` before `should have`.
- The PDF says quoted strings cannot contain spaces. Reject these rather than silently rewriting them.
- Attribute names and list categories are different namespaces and must be catalogued separately; spelling/case are significant.
- The PDF is a curated sample, not the full grammar. Treat undocumented items as unknown, not automatically unsupported by the real engine.

## Security and privacy requirements
- Treat user descriptions and all model output as untrusted input.
- Before the LLM call, detect likely sensitive values and avoid sending raw PAN, Aadhaar, card numbers, or similar identifiers to the provider. Do not log raw descriptions or model payloads by default.
- For v1, do not support rules that require embedding a raw PAN/Aadhaar or other personal identifier in the prompt or emitted literal. Return a clear privacy-safe refusal/alternative.
- Enforce a conservative allow-list for quoted values. Reject unsupported characters or spaces with an explanation; never silently sanitize and change the user's intended value.
- Do not use `eval`, dynamic code execution, or compile generated Scala. Keep secrets server-side; validate request size and rate-limit the API.

## Validation behaviour
The validator must reject or route to clarification when:
- an attribute, function, list category, or syntax pattern is absent from the catalog;
- the request is vague (e.g. “large amount”, “recently”) and a numeric threshold/window is required;
- the rule mixes `and` and `or` in one chain;
- a history `where` has no required `from same` / `to different` clause;
- a quoted value contains spaces or characters outside the v1 allow-list;
- the user asks for logic that cannot be represented without changing its meaning;
- sensitive personal identifiers would need to be sent to the LLM or embedded as a literal.

Use explicit outcomes such as `ready`, `needs_clarification`, and `cannot_express`. Only `ready` may be rendered.

## Evaluation and acceptance criteria
- Encode every worked rule example in the PDF's §9 as a hand-authored IR fixture with an expected DSL string.
- Unit-test the renderer against those strings character-for-character. This validates our renderer against the examples, **not** against the company's parser.
- Build natural-language paraphrases for each supported pattern; keep about 25% unseen while tuning the prompt and use them as a holdout evaluation set.
- Include negative tests for mixed `and`/`or`, missing thresholds, unknown catalog entries, invalid strings, missing history grouping clauses, privacy-sensitive identifiers, and unrepresentable logic.
- Compare predicted IR semantics to expected IR, not only surface strings. Track correct generation, clarification, refusal, and unsafe-output rates.
- Do not release unless all deterministic tests pass and UI wording consistently communicates that real-engine validation is unavailable.

## Suggested implementation sequence
1. Read the PDF and hand-author IR fixtures for its worked examples.
2. Define IR types, catalog, semantic validator, and deterministic renderer; establish exact-output tests before adding an LLM.
3. Add LLM structured output with the catalog and examples in the prompt; support `needs_clarification` and `cannot_express` responses.
4. Add paraphrase/negative-case evaluation and privacy safeguards.
5. Build the simple web UI: request box, clarification flow, plain-language read-back, DSL result, warnings, copy action, and not-verified label.
6. Document supported coverage and limitations; run the complete test suite before each release.

## Scope guard
V1 is a candidate-rule authoring helper, not an official IUCA validator, rule-deployment system, fraud decision service, model-training project, or full reconstruction of the private DSL grammar. Expand coverage only when supported by the PDF or explicitly labeled external/inferred evidence and backed by tests.
