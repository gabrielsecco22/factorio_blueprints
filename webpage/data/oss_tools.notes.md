# OSS Factorio Blueprint Tooling Landscape (May 2026)

The OSS scene splits cleanly into five buckets: in-browser **calculators**, **in-game planning mods**, **blueprint codec libraries**, **renderers/visualizers**, and **compilers** that emit blueprints from another source language.

**Healthy and 2.0/Space Age-ready.** The calculator side is in good shape: FactorioLab and Kirk McDonald's calculator both ship vanilla 2.0 and Space Age datasets, YAFC-CE works with any 2.0+ mod set, and the in-game trio (Factory Planner, Helmod, Recipe Book via Codeberg) is being maintained against current Factorio. On the library side, redruin1's `factorio-draftsman` (Python) and demipixel's `factorio-blueprint` (TS) both have explicit 2.0 fixes in 2026 commits. JensForstmann's TS library and `fatul` round out the codec picture.

**Stagnant or partial.** The headline gap is **visual editing**: teoxoy's FBE remains the best browser editor, but its 2.0/Space Age tracking issue (#268) is still open and unassigned. The Rust crate `factorio-blueprint` and Clojure `factorio-blueprint-tools` predate 2.0. asheiduk's binary `.dat` decoder is stuck on the 1.1 format — a clear opportunity for a 2.0 successor.

**Surprises.** Renderer leadership has shifted to demodude4u's FBSR (the Discord BlueprintBot), not FBE's image export. The compiler niche is unexpectedly active: verilog2factorio (817 stars), Factompiler (401), and Miditorio all ship 2.0-valid output. alegnani's `verifactory` is the only OSS tool doing **formal verification** of blueprints — niche but unique.

**Net.** Calculation and codec are solved; visual editing for 2.0 is the conspicuous unmet need.
