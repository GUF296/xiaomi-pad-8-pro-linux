#!/usr/bin/env python3
"""Repack a v2 Android boot image, preserving original load addresses/DTB."""
import json
import subprocess
import sys
from pathlib import Path

mkbootimg, source_dir, ramdisk, output = map(Path, sys.argv[1:5])
m = json.loads((source_dir / "metadata.json").read_text())
if m["header_version"] != 2:
    raise SystemExit("only Android boot header v2 is supported")
patch = m["os_version_patch"] & 0x7ff
version = m["os_version_patch"] >> 11
os_version = f"{version >> 14}.{(version >> 7) & 127}.{version & 127}"
os_patch = f"{2000 + (patch >> 4):04d}-{patch & 15:02d}"
cmd = ["python3", str(mkbootimg), "--header_version", "2",
       "--pagesize", str(m["page_size"]), "--base", "0",
       "--kernel_offset", hex(m["kernel_addr"]),
       "--ramdisk_offset", hex(m["ramdisk_addr"]),
       "--tags_offset", hex(m["tags_addr"]),
       "--dtb_offset", hex(m["dtb_addr"]),
       "--board", m["board"], "--cmdline", m["cmdline"],
       "--kernel", str(source_dir / "kernel"),
       "--ramdisk", str(ramdisk), "--dtb", str(source_dir / "dtb"),
       "--output", str(output)]
if version:
    cmd += ["--os_version", os_version]
if patch:
    if patch & 15 not in range(1, 13):
        raise SystemExit("invalid Android OS patch month")
    cmd += ["--os_patch_level", os_patch]
if m["second_size"]:
    cmd += ["--second", str(source_dir / "second"),
            "--second_offset", hex(m["second_addr"])]
if m["recovery_size"]:
    cmd += ["--recovery_dtbo", str(source_dir / "recovery_dtbo")]
subprocess.run(cmd, check=True)
# Verify the generated image's metadata and unchanged binary components with
# the independent boot parser. A full byte identity is impossible because the
# ramdisk is deliberately different, and the boot ID checksum must change.
check = output.parent / "verified-boot"
subprocess.run(["python3", str(Path(__file__).with_name("unpack-android-boot-v2.py")),
                str(output), str(check)], check=True)
n = json.loads((check / "metadata.json").read_text())
keys = ("header_version", "header_size", "page_size", "kernel_addr", "ramdisk_addr",
        "second_addr", "tags_addr", "dtb_addr", "recovery_offset", "board", "cmdline",
        "os_version_patch")
for key in keys:
    if m[key] != n[key]:
        raise SystemExit(f"rebuilt boot.img changed {key}: {m[key]!r} -> {n[key]!r}")
for part in ("kernel", "dtb", "second", "recovery_dtbo"):
    if (source_dir / part).read_bytes() != (check / part).read_bytes():
        raise SystemExit(f"rebuilt boot.img changed {part}")
if (check / "ramdisk").read_bytes() != ramdisk.read_bytes():
    raise SystemExit("rebuilt boot.img ramdisk mismatch")
print(f"verified complete Android boot.img v2: {output}")
