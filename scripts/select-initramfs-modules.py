#!/usr/bin/env python3
"""Copy only USB gadget/PHY module dependency closure into an initramfs."""
from __future__ import annotations
import argparse
import shutil
from pathlib import Path

REQUESTED = (
    "g_mass_storage", "usb_f_mass_storage", "libcomposite",
    "dwc3", "dwc3_qcom", "phy_qcom_qmp", "phy_qcom_qmp_usb",
    "usb_role_switch", "qcom_pmic_glink", "qcom_pmic_glink_altmode",
)

def stem(path: str) -> str:
    name = Path(path).name
    for suffix in (".xz", ".gz", ".zst", ".lz4"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    if name.endswith(".ko"):
        name = name[:-3]
    return name.replace("-", "_")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("destination", type=Path)
    ap.add_argument("kernelrelease")
    args = ap.parse_args()
    src = args.source / args.kernelrelease
    dst = args.destination / args.kernelrelease
    depfile = src / "modules.dep"
    if not depfile.is_file():
        raise SystemExit(f"missing {depfile}")
    deps: dict[str, list[str]] = {}
    by_stem: dict[str, list[str]] = {}
    for raw in depfile.read_text(errors="replace").splitlines():
        path, _, rest = raw.partition(":")
        path = path.strip()
        if not path:
            continue
        values = [x for x in rest.split() if x]
        deps[path] = values
        by_stem.setdefault(stem(path), []).append(path)
    selected: set[str] = set()
    pending = []
    for name in REQUESTED:
        pending.extend(by_stem.get(name, []))
    # The three gadget modules are mandatory; board PHY/role pieces can be
    # built in and therefore legitimately absent from modules.dep.
    for name in ("g_mass_storage", "usb_f_mass_storage", "libcomposite"):
        if not by_stem.get(name):
            raise SystemExit(f"kernel artifact lacks required module {name}")
    while pending:
        path = pending.pop()
        if path in selected:
            continue
        selected.add(path)
        pending.extend(deps.get(path, []))
    dst.mkdir(parents=True, exist_ok=True)
    for metadata in src.glob("modules.*"):
        shutil.copy2(metadata, dst / metadata.name)
    for rel in sorted(selected):
        src_file = src / rel
        if not src_file.is_file():
            raise SystemExit(f"module dependency is missing: {src_file}")
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, out)
    (dst / "selected-modules.txt").write_text("\n".join(sorted(selected)) + "\n")
    print(f"selected {len(selected)} USB/PHY module dependencies")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
