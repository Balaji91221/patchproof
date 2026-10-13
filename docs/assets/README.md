# README visuals

[Back to the project](../../README.md)

`overview.svg` is an original explanatory workflow illustration, not a product screenshot.

`demo.png`: A screenshot of the actual HTML report from the authored regression fixture. Environment inventory and complete evidence panels remain collapsed.

The demo uses synthetic local data; it does not represent a production deployment or a live model evaluation.

## Reproduce the data

Run from the repository root after following the main README installation steps:

```bash
PYTHONPATH=src python3 examples/demo.py --output /tmp/patchproof-demo-001
# Open /tmp/patchproof-demo-001/report.html; use a fresh directory.
```

Timing values and generated paths may differ between runs. Screenshots show the relevant report view; complete artifacts stay in your selected output directory.
