#!/usr/bin/env python3
"""Id-Vg transfer sweep of the nFET nanosheet with FOM extraction.

Equivalent CLI: cfet-tcad run configs/nsheet_nfet_2d.yaml
"""

import json
from pathlib import Path

from cfet_tcad.workflow import load_config, run_config

ROOT = Path(__file__).resolve().parent.parent


def main():
    cfg = load_config(ROOT / "configs" / "nsheet_nfet_2d.yaml")
    results = run_config(cfg)
    print(json.dumps(results["fom"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
