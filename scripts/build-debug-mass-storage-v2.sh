#!/usr/bin/env bash
# Rebuild a standalone Android boot-v2 image with an optional UFS-LUN0 USB
# mass-storage gadget. The original kernel, DTB, addresses, and command line
# are extracted and passed back to mkbootimg unchanged; only ramdisk changes.
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ANDROID_BOOT_DIR="${ANDROID_BOOT_DIR:-$ROOT_DIR/debug-android}"
KERNEL_DIR="${KERNEL_DIR:-$ROOT_DIR/debug-kernel}"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/debug-artifacts}"
MASS_STORAGE_RO="${MASS_STORAGE_RO:-0}"
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
[[ "$MASS_STORAGE_RO" == 0 || "$MASS_STORAGE_RO" == 1 ]] || die 'MASS_STORAGE_RO must be 0 or 1'
[[ -d "$ANDROID_BOOT_DIR" && -d "$KERNEL_DIR" ]] || die 'ANDROID_BOOT_DIR and KERNEL_DIR are required'
# actions/download-artifact preserves the artifact's internal directory. Run
# 36816302734, for example, unpacked v3/boot-components and v3/kernel-artifacts.
# Locate files recursively, then normalize KERNEL_DIR to the artifact root.
mapfile -d "" -t BOOT_IMAGES < <(find "$ANDROID_BOOT_DIR" -type f -name "boot.img" -print0)
if [[ ${#BOOT_IMAGES[@]} -eq 0 ]]; then
  mapfile -d "" -t BOOT_IMAGES < <(find "$ANDROID_BOOT_DIR" -type f -iname "*boot*.img" -print0)
fi
if [[ ${#BOOT_IMAGES[@]} -eq 0 ]]; then
  mapfile -d "" -t BOOT_IMAGES < <(find "$ANDROID_BOOT_DIR" -type f -iname "*.img" -print0)
fi
[[ ${#BOOT_IMAGES[@]} -eq 1 ]] || die "expected exactly one Android boot image in artifact, found ${#BOOT_IMAGES[@]}"
BOOT_IMAGE="${BOOT_IMAGES[0]}"
BOOT_IMAGE_DIR="$(dirname "$BOOT_IMAGE")"
mapfile -d "" -t KERNEL_RELEASES < <(find "$KERNEL_DIR" -type f -name kernelrelease -print0)
[[ ${#KERNEL_RELEASES[@]} -eq 1 ]] || die "expected exactly one recursive kernelrelease, found ${#KERNEL_RELEASES[@]}"
KERNEL_ARTIFACT_DIR="$KERNEL_DIR"
KERNEL_DIR="$(dirname "${KERNEL_RELEASES[0]}")"
KERNEL_PAYLOAD=""
for candidate in Image Image.gz; do
  if [[ -s "$KERNEL_DIR/$candidate" ]]; then KERNEL_PAYLOAD="$KERNEL_DIR/$candidate"; break; fi
done
[[ -n "$KERNEL_PAYLOAD" ]] || die "missing kernel payload Image or Image.gz in $KERNEL_DIR"
for name in kernelrelease modules.tar.gz; do
  [[ -s "$KERNEL_DIR/$name" ]] || die "missing kernel artifact in $KERNEL_DIR: $name"
done
# Checksums may live beside the nested artifact directory or at its parent.
find_checksum() {
  local dir="$1" candidate parent
  while :; do
    candidate="$dir/SHA256SUMS"
    if [[ -s "$candidate" ]]; then printf '%s\n' "$candidate"; return 0; fi
    parent="$(dirname "$dir")"
    [[ "$parent" == "$dir" ]] && break
    dir="$parent"
  done
  return 1
}
BOOT_SUMS="$(find_checksum "$BOOT_IMAGE_DIR" || true)"
[[ -n "$BOOT_SUMS" ]] || die "missing SHA256SUMS beside Android boot artifact"
python3 "$ROOT_DIR/scripts/verify-split-artifact.py" \
  "$ANDROID_BOOT_DIR" "$BOOT_SUMS" "$BOOT_IMAGE"
KERNEL_SUMS="$(find_checksum "$KERNEL_DIR" || true)"
[[ -n "$KERNEL_SUMS" ]] || die "missing SHA256SUMS beside kernel artifact"
python3 "$ROOT_DIR/scripts/verify-split-artifact.py" \
  "$KERNEL_ARTIFACT_DIR" "$KERNEL_SUMS" \
  "$KERNEL_PAYLOAD" "$KERNEL_DIR/kernelrelease" "$KERNEL_DIR/modules.tar.gz"
KVER="$(<"$KERNEL_DIR/kernelrelease")"
[[ "$KVER" == 7.1.3-piano ]] || die "unexpected kernelrelease: $KVER"
command -v cpio >/dev/null || die 'cpio is required'
command -v unmkinitramfs >/dev/null || die 'initramfs-tools-core (unmkinitramfs) is required'
command -v depmod >/dev/null || die 'kmod/depmod is required'
command -v gzip >/dev/null || die 'gzip is required'
if [[ -x "$ROOT_DIR/mkbootimg" ]]; then
  MKBOOTIMG="$ROOT_DIR/mkbootimg"
elif command -v mkbootimg >/dev/null 2>&1; then
  MKBOOTIMG="$(command -v mkbootimg)"
else
  die 'mkbootimg is required in checkout or PATH to rebuild complete boot.img'
fi
mkdir -p "$OUTPUT_DIR"
rm -rf "$OUTPUT_DIR/work"
mkdir -p "$OUTPUT_DIR/work" "$OUTPUT_DIR/work/modules"
python3 "$ROOT_DIR/scripts/unpack-android-boot-v2.py" "$BOOT_IMAGE" "$OUTPUT_DIR/work/android"
python3 - "$OUTPUT_DIR/work/android/metadata.json" <<'PYMETA'
import json, sys
m = json.load(open(sys.argv[1]))
if m["header_version"] != 2 or not m["ramdisk_size"] or not m["dtb_size"]:
    raise SystemExit("expected Android boot v2 with embedded ramdisk and DTB")
PYMETA
cmp -s "$OUTPUT_DIR/work/android/kernel" "$KERNEL_PAYLOAD" || \
  die "Android boot kernel does not match downloaded kernel artifact $(basename "$KERNEL_PAYLOAD")"
# Ubuntu initramfs images commonly contain an uncompressed early CPIO archive
# followed by a compressed main archive. gzip -t is therefore incorrect and
# rejects valid images. unmkinitramfs understands all early-CPIO/compression
# layers and merges them into one tree for the rebuilt debug image.
unmkinitramfs "$OUTPUT_DIR/work/android/ramdisk" "$OUTPUT_DIR/work/initrd"
INITRD="$OUTPUT_DIR/work/initrd"
# A boot-v2 ramdisk can contain Android init rather than initramfs-tools.
# In that case an init-premount hook would never run; refuse to build it.
[[ -f "$INITRD/init" ]] || die 'Android boot ramdisk has no /init'
grep -q 'run_scripts /scripts/init-premount' "$INITRD/init" || \
  die 'boot ramdisk is not initramfs-tools with init-premount dispatch; cannot safely hook it'
[[ -e "$INITRD/sbin/modprobe" || -L "$INITRD/sbin/modprobe" || \
   -e "$INITRD/bin/modprobe" || -L "$INITRD/bin/modprobe" || \
   -e "$INITRD/usr/sbin/modprobe" || -L "$INITRD/usr/sbin/modprobe" ]] || \
  die 'boot ramdisk has no modprobe'
install -d "$INITRD/scripts/init-premount" "$INITRD/etc/piano"
install -m 0755 "$ROOT_DIR/scripts/initramfs/00-piano-mass-storage" \
  "$INITRD/scripts/init-premount/00-piano-mass-storage"
printf '%s\n' "$MASS_STORAGE_RO" > "$INITRD/etc/piano/mass-storage-ro"
# Extract the matching modules archive; the helper below copies only the
# gadget/USB PHY dependency closure needed by this debug hook.
tar -xzf "$KERNEL_DIR/modules.tar.gz" -C "$OUTPUT_DIR/work/modules"
[[ -d "$OUTPUT_DIR/work/modules/$KVER" ]] || die "modules.tar.gz lacks $KVER"
install -d "$INITRD/lib/modules"
rm -rf "$INITRD/lib/modules/$KVER"
# Keep the initramfs small: copy the gadget/PHY dependency closure and the
# kmod indexes, rather than the complete (often >1 GiB) kernel modules tree.
python3 "$ROOT_DIR/scripts/select-initramfs-modules.py" \
  "$OUTPUT_DIR/work/modules" "$INITRD/lib/modules" "$KVER"
depmod -b "$INITRD" "$KVER"
for module in \
  "$INITRD/lib/modules/$KVER/kernel/drivers/usb/gadget/libcomposite.ko" \
  "$INITRD/lib/modules/$KVER/kernel/drivers/usb/gadget/function/usb_f_mass_storage.ko" \
  "$INITRD/lib/modules/$KVER/kernel/drivers/usb/gadget/legacy/g_mass_storage.ko"; do
  [[ -f "$module" || -f "$module.xz" || -f "$module.gz" || -f "$module.zst" ]] || \
    die "kernel artifact is missing required gadget module: $module"
done
# Build a complete Android boot image from the original header metadata. The
# original kernel, DTB, second stage, and recovery DTBO (if any) are reused.
(cd "$INITRD"; find . -print | LC_ALL=C sort | cpio -o -H newc --quiet) | gzip -n > "$OUTPUT_DIR/work/ramdisk-debug.gz"
python3 "$ROOT_DIR/scripts/repack-android-boot-v2.py" \
  "$MKBOOTIMG" "$OUTPUT_DIR/work/android" \
  "$OUTPUT_DIR/work/ramdisk-debug.gz" "$OUTPUT_DIR/boot.img"
cp "$BOOT_IMAGE" "$OUTPUT_DIR/boot.img.original"
cat > "$OUTPUT_DIR/README.debug-mass-storage.txt" <<EOF
Standalone Android boot-v2 debug image for piano UFS LUN0.

boot.img is rebuilt from the downloaded Android boot artifact. The hook exports
whole /dev/sda only after proving it is SCSI LUN 0 attached to ufshcd, then
stays in the initramfs in both success and failure paths; it never mounts root.
Read-only policy: $MASS_STORAGE_RO (0 means controlled read/write export).
Source run: ${SOURCE_RUN_ID:-unknown}

This artifact has only static and synthetic-image validation. It has NOT been
booted on piano hardware, and USB host enumeration, UFS identity, AVB signing,
and recovery behavior remain unverified.
EOF
rm -rf "$OUTPUT_DIR/work"
(cd "$OUTPUT_DIR"; sha256sum boot.img boot.img.original README.debug-mass-storage.txt > SHA256SUMS)
printf 'complete Android debug boot image ready: %s/boot.img (kernel %s, ro=%s)\n' "$OUTPUT_DIR" "$KVER" "$MASS_STORAGE_RO"
