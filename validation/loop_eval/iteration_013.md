# Loop iteration 013

- **timestamp**: 2026-05-09T21:12:38Z
- **case**: `green_circuit_block_5ps_vanilla` (index 1/12)

## creator: master_synthesize (--kind required for non-smelter cases) (exit 0)

```
python3 -m harness.master_orchestrator master --target electronic-circuit --rate 5 --mod-set vanilla --kind green_circuit_block
```

```
# Master orchestrator report (PASS)

- target: `electronic-circuit` @ 5.0/s
- mod-set policy: `vanilla`
- iterations: 1 / 3

## Iteration trace
- attempt 1: status=PASS, struct=True, rate=True, mod=True, visual=True

## Mod compatibility
- required: ['base']
- missing: (none)
- disabled: (none)
- zip_only: (none)

## Blueprint string

0eNqdmuFumzAUhV8l4u+Syja2sfMCe4ipmgjxWjRiIiDToirvPpJGTdYCOYefgfJx7qdeXS7JW7KpDmHflLFL1m9J2YVdsr47tkyqfBOq/tj3JoS4KMqmOJTdYlPVxe/1Qi+KfFOFxbeF/TiVt23Y9Qebtr+6LOrYJusfb0lbvsS8Ot+kO+5DD7zca5nEfHf+FKpQdE0dy2J1BSWn/vK4DX+TtTwtHwKKer8PzeqS5+5SdXpeJiF2ZVeG9yCXD8ef8bDbhKZnfxC6Jo/tvm66VV/xufR93faX1fF8zx4llskxWa9UD9+WTR/3ckqfs31iKpYpHzNTkmkeIzWJlEBMAzMlrNOyTCBnRjIBnY5EIjo9zFSwTilYKBBUShIKCJWKZCJGJd5IKa5Us1AkqSGhiFJLMiGleDNpXKljoUhST0IBpUqQTESpwtvJ4GNJsVAkaUpCEaWaZEJK8XayuFLLQpGkGQlFlDqSCSnF2ymDlaaChSJPT5KEAkpTRTIRpSneTg5XqlkoktSQUESpJZmQUrydPK7UsVAkqSehyEO+IJmIUo23k8TXJq1oKpI1ZamIVc1CIa3E9oSvT9rSVCRrxlIRrY6FQlrxtpL4GmUETUX2Z8lSAa1GsVBo1ScaC1+ljKapSFbDUhGtloVCWonGwtcp42gqktWzVECrFSwU0WqJxsJXKqtoKpI1ZamIVs1CIa1EY+FrlbU0FcmasVREq2OhkFaisfDVKhM0FXmVKlkqoDVTLBTRmt0a6/o1RRlfVru8eC1jWMmxN7VntT233I9+U/H1Trduq+r+Hq953IbtqoxtaLr+D0ZesYv/a3BD5FvHbQ5NDM0EVF2hQ5hbi/3K224C8u5AD0Iy0qee7dORPlPYp8d9mnGfTqA+9bhPJ0mf2VyfTpE+LerTpbhPN+FToz6zCZ+G7XcxW6glhXpYaIYLvW5Fw0Yd3PFiQqlnlaZzlXpBKpUKdeol4VSPO/UKdpqOO/X0WLKznbJzSRrYKTGYrjN72Ck+meyE02zWqHf3Sj/9puDrPRw3Q+1gUGL+XN95DGqTQswaxlTFUkhuzNnhqAqvWU/WnM4amGTN5CgaqZloj2yyZjtvqJFFZ+S0GKnaEf/dYrLsW5+0h03b5Zcrvz5HP1337PTJDHLufv4wxZH2IUhSgaQa4ygu0DvoeZn8CU17OW+s8tp747RQQrvT6R/DR5a1

```

## calculator: belt-saturate (exit 0)

```
python3 tools/rate_cli.py belt-saturate --recipe electronic-circuit --machine assembling-machine-2 --belt-tier transport-belt
```

```
## Belt saturation report
  recipe   : electronic-circuit
  machine  : 1 x assembling-machine-2
  belt tier: transport-belt

item                items/s  belts (full)  lanes
------------------  -------  ------------  -----
electronic-circuit  1.500/s  0.050         0.100

```

## visual reviewer: render_blueprint --json (exit 0)

```
{
  "bbox": {
    "x_min": 0,
    "y_min": -4,
    "x_max": 17,
    "y_max": 13,
    "width": 18,
    "height": 18
  },
  "render_window": {
    "x_min": 0,
    "y_min": -4,
    "x_max": 17,
    "y_max": 13,
    "width": 18,
    "height": 18
  },
  "entity_counts": {
    "assembling-machine-1": 10,
    "burner-inserter": 10,
    "fast-inserter": 10,
    "long-handed-inserter": 6,
    "substation": 4,
    "transport-belt": 72
  },
  "by_category": {
    "crafting": 10,
    "logistics": 98,
    "power_distribution": 4
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
