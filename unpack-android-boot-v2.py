#!/usr/bin/env python3
"""Extract an Android boot image v0-v2 using the AOSP little-endian layout.

The repository's mkbootimg is the writer; this small reader keeps the original
header addresses, page size, DTB and command line available to the debug build.
It deliberately rejects v3/v4 because those images move the ramdisk to
vendor_boot and cannot safely be rewritten as a single boot.img here.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

PAGE = 4096
MAGIC = b"ANDROID!"

def align(value: int, page: int) -> int:
    return (value + page - 1) // page * page

def cstring(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", "replace")

def write_part(src, dst: Path, offset: int, size: int) -> None:
    with src:
        src.seek(offset)
        dst.write_bytes(src.read(size))

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    with args.image.open("rb") as src:
        header = src.read(PAGE)
        if len(header) < 44 or header[:8] != MAGIC:
            raise SystemExit(f"{args.image}: not an Android boot image")
        u32 = lambda off: struct.unpack_from("<I", header, off)[0]
        kernel_size, kernel_addr = u32(8), u32(12)
        ramdisk_size, ramdisk_addr = u32(16), u32(20)
        second_size, second_addr = u32(24), u32(28)
        tags_addr, page_size = u32(32), u32(36)
        header_version, os_version_patch = u32(40), u32(44)
        if page_size < 512 or page_size & (page_size - 1):
            raise SystemExit(f"invalid Android page size {page_size}")
        if header_version > 2:
            raise SystemExit(
                f"Android header v{header_version} uses vendor_boot; expected piano v2")
        if len(header) < page_size:
            src.seek(0)
            header = src.read(page_size)
        board = cstring(header[48:64])
        cmdline = header[64:576].split(b"\0", 1)[0] + header[608:1632].split(b"\0", 1)[0]
        recovery_size = recovery_offset = 0
        dtb_size = dtb_addr = 0
        if header_version >= 1:
            recovery_size = u32(1632)
            recovery_offset = struct.unpack_from("<Q", header, 1636)[0]
        if header_version == 1:
            header_size = u32(1644)
        elif header_version == 2:
            header_size = u32(1644)
            dtb_size = u32(1648)
            dtb_addr = struct.unpack_from("<Q", header, 1652)[0]
        else:
            header_size = page_size

        kernel_offset = page_size
        ramdisk_offset = align(kernel_offset + kernel_size, page_size)
        second_offset = align(ramdisk_offset + ramdisk_size, page_size)
        if header_version >= 1 and recovery_size:
            if recovery_offset == 0:
                recovery_offset = align(second_offset + second_size, page_size)
        elif header_version < 1:
            recovery_offset = 0
        dtb_offset = align(second_offset + second_size, page_size)
        if header_version >= 1 and recovery_size:
            dtb_offset = align(recovery_offset + recovery_size, page_size)

        with args.image.open("rb") as src:
            write_part(src, args.output / "kernel", kernel_offset, kernel_size)
        with args.image.open("rb") as src:
            write_part(src, args.output / "ramdisk", ramdisk_offset, ramdisk_size)
        with args.image.open("rb") as src:
            write_part(src, args.output / "second", second_offset, second_size)
        if recovery_size:
            with args.image.open("rb") as src:
                write_part(src, args.output / "recovery_dtbo", recovery_offset, recovery_size)
        else:
            (args.output / "recovery_dtbo").write_bytes(b"")
        if dtb_size:
            with args.image.open("rb") as src:
                write_part(src, args.output / "dtb", dtb_offset, dtb_size)
        else:
            (args.output / "dtb").write_bytes(b"")

    # Reject trailing AVB/signature data that mkbootimg cannot preserve.
    expected_end = align(dtb_offset + dtb_size, page_size)
    if args.image.stat().st_size > expected_end:
        raise SystemExit("boot image has trailing data (possibly AVB footer); cannot preserve it")
    metadata = {
        "header_version": header_version,
        "header_size": header_size,
        "page_size": page_size,
        "kernel_size": kernel_size,
        "kernel_addr": kernel_addr,
        "ramdisk_size": ramdisk_size,
        "ramdisk_addr": ramdisk_addr,
        "second_size": second_size,
        "second_addr": second_addr,
        "tags_addr": tags_addr,
        "recovery_size": recovery_size,
        "recovery_offset": recovery_offset,
        "dtb_size": dtb_size,
        "dtb_addr": dtb_addr,
        "board": board,
        "cmdline": cmdline.decode("utf-8", "replace"),
        "os_version_patch": os_version_patch,
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
