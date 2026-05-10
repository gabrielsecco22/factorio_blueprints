# Loop iteration 015

- **timestamp**: 2026-05-09T22:06:07Z
- **case**: `steel_smelter_array_run_only` (index 3/12)

## creator: example (exit 0)

```
python3 -m harness.examples.steel_smelter_array
```

```
# Synthesis report: smelter_array

## Plan
- 24 x `steel-furnace` -> `iron-plate` (0.6250 /s/machine, 15.0000 /s total)
  - fuel: coal
  - inputs: iron-ore @ 15.000/s
  - outputs: iron-plate @ 15.000/s

## Layout
- bounding box (tiles): NW=(0,-1) SE=(48,5)
- entity count: 192
- breakdown:
  - burner-inserter: 72
  - steel-furnace: 24
  - transport-belt: 96

## Rate calculator

- **24 x `steel-furnace` -> `iron-plate`** (0.6250 crafts/s/machine, 15.0000 crafts/s total)
  - outputs: iron-plate @ 15.000/s
  - inputs: iron-ore @ 15.000/s
  - effective: speed x1.000, prod +0.000, power 2160 kW, pollution 96.0/min

## Blueprint string

0eNq1m8Fu40YQRH9F4CkB5AW7e8iZ0T8EyGkvwWIh2+NEgEwZJL2IYejfQ8sbZ5GlZqoOc5RkPlEFPJdIu16b2+NzehoPw9zsXpvDnB6b3Q/PbZvj/jYdl+d++/z7ZppTOm6mx3Sc07jZj+P+ZfOLus3D8zjs79K03Ux/7cd0f7McMi/PLj/8kNL9rwvmcHcapmb3x2szHf4c9se3d5tfntJCvrzpthn2j5dH42m4eTru59Scl8OG+/R3s5Pztnjg5eRuvp/KD8fq+cu2ScN8mA/p/QwuD16+Ds+Pt2lc4B+IedwP09NpnC8fYEE/nablsNPw9qYLqt02L83uZjmb5v4wprv3l9zbyf2PqTBTYKbBTIWZDmYazOxgpoOZPczsYKaHmT3MDDDTw8wIMwPMlBaGRhyKmyS4SkK4hMskuE2C6yS4T4ILJbhRgisluFOCSyW4VYJrJbhXgosluFmCq6W4WoK7pbhbStQU7pbibinRVLhbiruluFuKu6W4W4q7pbhbiruluFuKu6W4W4q7pbhbhruluFuGu2W4W4a7ZcSXQNwtw90y4nsg7pbhbhnuluFuGe6W4W4Z7pbhbhnuluFuGe6Ww90y3C2Hu+VwtxzulsPdcrhbjrjEwt1yuFuOuMrC3XK4Ww53y+FuOdwth7vlcLdcvHJD4eebAZ/eE5BP3XntKvg/nW4XRBpvDsOUxnl57co9gHYVIyzGVjGKY9rvmG3zcHi70fN+0+TfOzEfnLvT/ti83Vt5ntLXj5+cx+e09v6GxqqFWB3+QSwTa8di1mPtcYzWiNWjsbpCrAH/IF0m1shiVmPtCXdchVh7QWPt87H2hHb+eqy9sZj1WAl3+hqxdmisoRAroV3MxOpZzHqshDuhRqxwZUmhszzTWZnS8kJzVpP1hD5So7Y8XFtS6C1PuCeZ4vIdzVmPllBIalSXh6tLCt3lCf8kU14+0pzVaANjUY36CnB9SaG/AiNgpsCC0Zz1aBmLalRYgCtMCh0WGAEzJRY8zVmPlrGoRo0FuMa0UGOREFAzNRaF5qxGGwmLtEaNRfzqq1BjkRBQMzUWO5qzHi1zAVajxiJcY1qosUgIqJkai5HmrEYrLaNRjR6TFi4yLRSZtIyDmSaT1mjQlXgZlfoq8cJlpqEUL+NhzMXradCVeBmdQpV44UKzQqGJECpaptFEhAatxyuET1aj00TgUjMtxcvcVLRcvB0NuhIv4ZNplXjhYjNXipdQ0bpcvJEGrcerjE9Vqk3harNStSmjYq7a1GjQlXgZn6pUm8LVZqVqU0bFXLWpp0FX4mV8qlJtClebK1WbMff6c9VmQoPW4zXCJ1el2gyuNleqNiNUdLlqs44GXYmX8MlVqTbD/2pWqjYjVHS5arNIg9bjdYxPVarNwdXmStXmGBVz1eaMBl2Jl/GpSrUR//nx/svJIf+33JODBQjqycUCBA3kZAGCRnKzgEC7lhwtQFAhVwsQVMnZAgQ1crcAQR25W4CgHbtbgKg9u1uAqJ7dLUDUwO4WIGpkdwsItW/Z3QJEFXa3AFGV3S1AVGN3CxDVsbsFiNqxuwWI2rO7BYjq2d0CRA3sbgGiRna3gFB9y+4WIKqwuwWIquxuAaIau1uAqI7dLUDUjt0tQNSe3S1AVM/uFiBqYHcLEDWyuwWEGlp2twBRhd0tQFRldwsQ1djdAkR17G4BonbsbgGi9uxuAaJ6drcAUQO7W4Cokd0tINTYsrsFiCrsbgGiKrtb+In6Zdt8S+N0edT1Gl2MXXCtti6cz/8Aj9LXkw==

```

## visual reviewer: render_blueprint --json (exit 0)

```
{
  "bbox": {
    "x_min": 0,
    "y_min": -1,
    "x_max": 47,
    "y_max": 4,
    "width": 48,
    "height": 6
  },
  "render_window": {
    "x_min": 0,
    "y_min": -1,
    "x_max": 47,
    "y_max": 4,
    "width": 48,
    "height": 6
  },
  "entity_counts": {
    "burner-inserter": 72,
    "steel-furnace": 24,
    "transport-belt": 96
  },
  "by_category": {
    "crafting": 24,
    "logistics": 168
  },
  "fluid_systems": [],
  "circuit_networks": [],
  "tiles": {},
  "mods_referenced": [
    "base"
  ],
  "mods_missing_in_user_install": [],
  "warnings": []
}

```

## verdict: PASS
