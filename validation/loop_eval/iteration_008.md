# Loop iteration 008

- **timestamp**: 2026-05-09T18:44:38Z
- **case**: `quality_legendary_iron_plate` (index 8/8)

## calculator: legendary stone-furnace (exit 0)

```
python3 tools/rate_cli.py compute --recipe iron-plate --machine stone-furnace --machine-quality legendary --count 1
```

```
effect           raw bonus  effective   
---------------  ---------  ------------
speed            +0.000     x1.000      
productivity     +0.000     +0.000      
consumption      +0.000     x1.000      
pollution        +0.000     x1.000      
quality cascade  +0.000     0.0000/craft

### Throughput
  crafts/s/machine: 0.7812   crafts/s total: 0.7812

### Inputs (per second, total)
item      rate    
--------  --------
iron-ore  0.7812/s

### Outputs (per second, total)
item        rate    
----------  --------
iron-plate  0.7812/s

### Power and pollution
  machine: 90.0 kW each   total: 90.0 kW
  beacon power: 0.0 kW
  pollution: 2.00/min/machine, 2.00/min total

```

## calculator: normal vs legendary compare (exit 2)

```
python3 tools/rate_cli.py compare --recipe iron-plate --machines stone-furnace,steel-furnace,electric-furnace --count 1
```

```

[stderr]
usage: rate_cli compare [-h] --recipe RECIPE --machine MACHINE
                        [--modules MODULES] [--use-modded]
rate_cli compare: error: the following arguments are required: --machine

```

## visual reviewer: render_blueprint --json (exit 0)

```
[no blueprint string or file path found to render]
```

## verdict: WARN
