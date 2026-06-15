---
name: homefinance-categorize
description: Use when the user wants to categorize transactions, asks why statement spending shows as "(uncategorized)", wants to build or review categorization rules, or asks Claude to suggest categories for unknown payees. Drives the hybrid rule + suggestion loop.
---

# homefinance — Categorize transactions

You help the user assign a canonical category to every transaction so cross-source spending analysis works. The canonical vocabulary **mirrors their YNAB category names**.

## How categorization works

- YNAB rows are already categorized; the system derives their `canonical_category` from the YNAB category name automatically.
- Statement-ingested rows start uncategorized. They get a category from **ordered rules** (deterministic) or a **manual assignment** (sticky).
- You assist only the **long tail** — payees no rule matches yet. You never touch amounts.

## The loop

1. **Run `apply_categorization`.** Report the counts (ynab / rule / manual / uncategorized).
2. If `uncategorized > 0`, call **`suggest_categories`**. It returns the uncategorized payees (with counts) and the user's existing YNAB category names.
3. **Propose a category for each payee — constrained to the YNAB category names** the tool returned. Only invent a new name if nothing fits, and say so explicitly.
4. For each, ask the user to choose. Then either:
   - **Promote to a rule** (preferred for recurring payees): `add_category_rule(priority, match_field='payee', pattern=<stable substring>, canonical_category=<choice>)`. Rules make future imports self-categorize.
   - **Pin one row** (for true one-offs): `set_transaction_category(transaction_id, canonical_category)`.
5. **Re-run `apply_categorization`** so new rules take effect, and report the improved counts.

## Rules

- **Suggest category labels only — never amounts.** Money is never inferred here.
- **Always get the user's confirmation** before writing a rule or a manual category.
- Prefer **rules over manual** for anything that will recur — coverage then compounds and the system converges to fully deterministic.
- Keep rule patterns **stable and specific** (a distinctive substring of the payee), so they don't over-match.
- Manual assignments are sticky: re-running `apply_categorization` never overwrites them.

## After categorization improves

Point the user at `/homefinance:analyze` (cash flow, trends, recurring, anomalies) or `summarize_spending(group_by='canonical_category')`.
