#!/usr/bin/env python3
"""Id-Vd output characteristics of the nFET nanosheet.

Equivalent CLI: cfet-tcad run configs/nsheet_nfet_idvd_2d.yaml
"""

from pathlib import Path

from cfet_tcad.workflow import load_config, run_config

ROOT = Path(__file__).resolve().parent.parent


def main():
    cfg = load_config(ROOT / "configs" / "nsheet_nfet_idvd_2d.yaml")
    run_config(cfg)
    print(f"results in {cfg.output.directory}/")


if __name__ == "__main__":
    main()
