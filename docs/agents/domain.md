# Domain Docs

This repository uses a single-context layout:
- `GLOSSARY.md` at the repository root.
- Architecture decision records in `docs/adr/`.

## Before exploring

Read the root `GLOSSARY.md` and ADRs relevant to the area being explored.

If these files do not exist, proceed silently. Do not flag their absence
or suggest creating them upfront. The domain-modeling skill creates them
lazily when terms or decisions are resolved.

## Use the glossary's vocabulary

Use glossary terms when naming domain concepts in issues, proposals,
hypotheses, and tests. Avoid synonyms the glossary explicitly excludes.

If a needed concept is missing, reconsider whether the project uses it;
otherwise note the gap for domain-modeling.

## Flag ADR conflicts

Explicitly surface proposals that contradict an existing ADR, identifying
the decision and explaining why it may be worth reopening.
