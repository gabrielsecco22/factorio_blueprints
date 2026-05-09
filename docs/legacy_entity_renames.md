# Legacy entity rename table (Factorio 1.x -> 2.0)

When the user inventories their blueprint library, some old blueprints
reference entity names that were renamed during the Factorio 2.0 release.
Loading those blueprints in-game generally still works (the engine has
migration shims) but our `specs/items.json` only knows the modern name,
so the mod-attribution layer reports them as "unknown_entity" unless we
remap them first.

This file is the canonical mapping. Keep it minimal: only entries that
the inventory tool actually trips over should land here.

## Rename map

| Legacy name (1.x)                  | Modern name (2.0)             | Notes                                            |
| ---------------------------------- | ----------------------------- | ------------------------------------------------ |
| `logistic-chest-active-provider`   | `active-provider-chest`       | Vanilla logistic chest tier rename in 2.0.       |
| `logistic-chest-passive-provider`  | `passive-provider-chest`      | Vanilla logistic chest tier rename in 2.0.       |
| `logistic-chest-storage`           | `storage-chest`               | Vanilla logistic chest tier rename in 2.0.       |
| `logistic-chest-buffer`            | `buffer-chest`                | Vanilla logistic chest tier rename in 2.0.       |
| `logistic-chest-requester`         | `requester-chest`             | Vanilla logistic chest tier rename in 2.0.       |
| `stack-inserter`                   | `bulk-inserter`               | 2.0 renamed; the old name still resolves in-game via migration. |
| `stack-filter-inserter`            | `bulk-inserter`               | The 1.x stack-filter-inserter became the bulk-inserter with a built-in filter slot. |
| `filter-inserter`                  | `fast-inserter`               | 2.0 collapsed the dedicated filter-inserter into fast-inserter (every inserter now has filters). |
| `straight-rail`                    | `straight-rail`               | Same name; geometry changed in 2.0 (2x2 -> stays 2x2). |
| `curved-rail`                      | `curved-rail-a` / `curved-rail-b` | 2.0 split into two pieces. We don't auto-resolve this; flag as `unknown_entity` if seen. |

## How the inventory tool uses it

`tools/inventory_user_blueprints.py` walks each entity in a decoded
blueprint. For any entity whose name is not present in
`specs/items.json` (the live dump):

1. Look up the name in this rename table. If matched, mark the entity as
   `legacy_renamed` and emit the modern equivalent in the `suggested_name`
   field of the inventory record.
2. Otherwise, mark it `unknown_entity` for the user to resolve manually.

The map lives as a dict in `tools/inventory_user_blueprints.py` so the
inventory tool stays stdlib-only. This document is the human-readable
mirror; if you change one, change the other.
