# User blueprint inventory

Generated: 2026-05-09T16:46:56Z
Sources scanned: blueprint-storage-2.dat (5 reachable), library/personal/ (0), library/external/ (3)

## Summary
- Total blueprints: 8
- Fully decoded: 3 (envelope-only: 5, unparseable: 0)
- Vanilla / DLC only: 3
- Space Age required: 2
- Other-mod required: 0
- Has unknown / legacy entities: 1

## By mod requirement
- base + space-age: 2
- base: 1

## Per-blueprint detail

### user_dat_001 -- (no label) (envelope-only (body in in-game binary format))
- source: `/home/gabriel/.factorio/blueprint-storage-2.dat#slot-0`
- kind: envelope-only; size: 8,181 bytes
- classifier reasons: blueprint-storage-2.dat body bytes are NOT a blueprint string; we only have label + size + kind
- NOTE: Header reports 79 total objects in the file; we walked 5 entries.
- NOTE: Body decoding is not yet implemented for the binary .dat format. Export this blueprint from inside Factorio via Library -> the blueprint -> 'Export to string', save into library/personal/, and re-run inventory to get full details.
- VALIDATE:
  - Slot 0: label='', kind=blueprint, content_size=8181. Confirm you can find it in your in-game library?
  - Do you want to manually export this blueprint so we can inventory its entities?

### user_dat_002 -- (no label) (envelope-only (body in in-game binary format))
- source: `/home/gabriel/.factorio/blueprint-storage-2.dat#slot-1`
- kind: envelope-only; size: 3,043 bytes
- classifier reasons: blueprint-storage-2.dat body bytes are NOT a blueprint string; we only have label + size + kind
- NOTE: Header reports 79 total objects in the file; we walked 5 entries.
- NOTE: Body decoding is not yet implemented for the binary .dat format. Export this blueprint from inside Factorio via Library -> the blueprint -> 'Export to string', save into library/personal/, and re-run inventory to get full details.
- VALIDATE:
  - Slot 1: label='', kind=blueprint, content_size=3043. Confirm you can find it in your in-game library?
  - Do you want to manually export this blueprint so we can inventory its entities?

### user_dat_003 -- (no label) (envelope-only (body in in-game binary format))
- source: `/home/gabriel/.factorio/blueprint-storage-2.dat#slot-2`
- kind: envelope-only; size: 1,159 bytes
- classifier reasons: blueprint-storage-2.dat body bytes are NOT a blueprint string; we only have label + size + kind
- NOTE: Header reports 79 total objects in the file; we walked 5 entries.
- NOTE: Body decoding is not yet implemented for the binary .dat format. Export this blueprint from inside Factorio via Library -> the blueprint -> 'Export to string', save into library/personal/, and re-run inventory to get full details.
- VALIDATE:
  - Slot 2: label='', kind=blueprint, content_size=1159. Confirm you can find it in your in-game library?
  - Do you want to manually export this blueprint so we can inventory its entities?

### user_dat_004 -- DEF 1 (envelope-only (body in in-game binary format))
- source: `/home/gabriel/.factorio/blueprint-storage-2.dat#slot-3`
- kind: envelope-only; size: 1,796 bytes
- classifier reasons: blueprint-storage-2.dat body bytes are NOT a blueprint string; we only have label + size + kind
- NOTE: Header reports 79 total objects in the file; we walked 5 entries.
- NOTE: Body decoding is not yet implemented for the binary .dat format. Export this blueprint from inside Factorio via Library -> the blueprint -> 'Export to string', save into library/personal/, and re-run inventory to get full details.
- VALIDATE:
  - Slot 3: label='DEF 1', kind=blueprint, content_size=1796. Confirm you can find it in your in-game library?
  - Do you want to manually export this blueprint so we can inventory its entities?

### user_dat_005 -- Fleet (envelope-only (body in in-game binary format))
- source: `/home/gabriel/.factorio/blueprint-storage-2.dat#slot-4`
- kind: envelope-only; size: 0 bytes
- classifier reasons: blueprint-storage-2.dat body bytes are NOT a blueprint string; we only have label + size + kind
- NOTE: Header reports 79 total objects in the file; we walked 5 entries.
- NOTE: Body decoding is not yet implemented for the binary .dat format. Export this blueprint from inside Factorio via Library -> the blueprint -> 'Export to string', save into library/personal/, and re-run inventory to get full details.
- VALIDATE:
  - Slot 4: label='Fleet', kind=blueprint-book, content_size=None. Confirm you can find it in your in-game library?
  - Do you want to manually export this blueprint so we can inventory its entities?

### ext_006 -- Green Circuit 2400/m (Vulcanus foundry block, recipe=casting-iron)
- source: `external/factorio_school/-OsBJMo7P-2oKxsEc3oB.bp (external: factorio_school)`
- kind: blueprint; size: 1,529 bytes
- 75 entities, 15x25
- top entities: turbo-transport-belt x19, beacon x15, bulk-inserter x10, pipe x8, constant-combinator x7
- required mods: base, space-age
- throughput estimate: ~16.00 electronic-circuit/s (electromagnetic-plant, vanilla baseline)
- classifier reasons: 3 foundry; also has electromagnetic-plant
- VALIDATE:
  - Is this 'Green Circuit 2400/m' actually used as a Vulcanus foundry block, recipe=casting-iron? If not, what's its real purpose?
  - Is the throughput target ~16.00 electronic-circuit/s (electromagnetic-plant, vanilla baseline)? Different by how much?

### ext_007 -- Example Book (assembler block, 2 machines (recipe=iron-gear-wheel))
- source: `external/factoriobin/demo.bp (external: factoriobin)`
- kind: blueprint-book; size: 5,073 bytes
- 156 entities, 1465x1121
- top entities: substation x40, transport-belt x33, straight-rail x22, textplate-small-gold x12, underground-belt x11
- required mods: base, space-age
- UNKNOWN entity: `textplate-small-gold` x12 (no source mod found)
- LEGACY rename: `logistic-chest-passive-provider` x1 -> `passive-provider-chest` (game auto-migrates)
- LEGACY rename: `logistic-chest-requester` x1 -> `requester-chest` (game auto-migrates)
- throughput estimate: ~7.50 iron-gear-wheel/s (assembling-machine-3, vanilla baseline)
- classifier reasons: 2 assembling-machines
- VALIDATE:
  - Is this 'Example Book' actually used as a assembler block, 2 machines (recipe=iron-gear-wheel)? If not, what's its real purpose?
  - Is the throughput target ~7.50 iron-gear-wheel/s (assembling-machine-3, vanilla baseline)? Different by how much?
  - This blueprint uses 1.x-era entity names (logistic-chest-passive-provider -> passive-provider-chest, logistic-chest-requester -> requester-chest). OK to leave as-is (game migrates them) or do you want the blueprint rewritten to the 2.0 names?
  - Unknown entity names found (textplate-small-gold). Do these come from a mod you uninstalled? Should the inventory drop them or wait for you to re-enable the mod?

### ext_008 -- Auto Mall (assembler block, 4 machines)
- source: `external/factorioprints/-OsBpTa4QO8SyAlvD8m2.bp (external: factorioprints)`
- kind: blueprint; size: 5,677 bytes
- 47 entities, 15x10
- top entities: decider-combinator x13, arithmetic-combinator x11, bulk-inserter x4, small-lamp x4, active-provider-chest x2
- required mods: base
- classifier reasons: 4 assembling-machines
- VALIDATE:
  - Is this 'Auto Mall' actually used as a assembler block, 4 machines? If not, what's its real purpose?

## Open questions for the user

1. (user_dat_001) Slot 0: label='', kind=blueprint, content_size=8181. Confirm you can find it in your in-game library?
2. (user_dat_001) Do you want to manually export this blueprint so we can inventory its entities?
3. (user_dat_002) Slot 1: label='', kind=blueprint, content_size=3043. Confirm you can find it in your in-game library?
4. (user_dat_002) Do you want to manually export this blueprint so we can inventory its entities?
5. (user_dat_003) Slot 2: label='', kind=blueprint, content_size=1159. Confirm you can find it in your in-game library?
6. (user_dat_003) Do you want to manually export this blueprint so we can inventory its entities?
7. (user_dat_004) Slot 3: label='DEF 1', kind=blueprint, content_size=1796. Confirm you can find it in your in-game library?
8. (user_dat_004) Do you want to manually export this blueprint so we can inventory its entities?
9. (user_dat_005) Slot 4: label='Fleet', kind=blueprint-book, content_size=None. Confirm you can find it in your in-game library?
10. (user_dat_005) Do you want to manually export this blueprint so we can inventory its entities?
11. (ext_006) Is this 'Green Circuit 2400/m' actually used as a Vulcanus foundry block, recipe=casting-iron? If not, what's its real purpose?
12. (ext_006) Is the throughput target ~16.00 electronic-circuit/s (electromagnetic-plant, vanilla baseline)? Different by how much?
13. (ext_007) Is this 'Example Book' actually used as a assembler block, 2 machines (recipe=iron-gear-wheel)? If not, what's its real purpose?
14. (ext_007) Is the throughput target ~7.50 iron-gear-wheel/s (assembling-machine-3, vanilla baseline)? Different by how much?
15. (ext_007) This blueprint uses 1.x-era entity names (logistic-chest-passive-provider -> passive-provider-chest, logistic-chest-requester -> requester-chest). OK to leave as-is (game migrates them) or do you want the blueprint rewritten to the 2.0 names?
16. (ext_007) Unknown entity names found (textplate-small-gold). Do these come from a mod you uninstalled? Should the inventory drop them or wait for you to re-enable the mod?
17. (ext_008) Is this 'Auto Mall' actually used as a assembler block, 4 machines? If not, what's its real purpose?
