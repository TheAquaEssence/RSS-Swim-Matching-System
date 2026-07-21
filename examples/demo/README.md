# Synthetic demonstration data

Everything in this directory is synthetic and safe to use in tests, demos,
screenshots, and public distributions. It is separate from both the canonical
public ranking resources in `data/source/` and private runtime data under the
application-data directory.

## `matching/`

Solver-ready first-run inputs: `classes.csv`, `swimmers.csv`,
`instructors.csv`, and `historical_pairings.csv`. Regenerate all four
deterministically with:

```powershell
python -m data_generation.generate_demo_matching --seed 42
```

The base seed drives instructors and historical pairings. Swimmers and classes
use base seed + 1000 (1042 for the committed dataset), preventing Faker name
streams from overlapping while preserving exact reproducibility.

## `database/`

Synthetic stand-ins for the private instructor and class-pairing imports used
by database tooling. Regenerate them deterministically with:

```powershell
python -m data_generation.generate_demo_source --seed 42
```

Neither generator writes into `data/source/`, application runtime storage, or
the retired and ignored `data/app_samples/` path.
