# Xiaomi Pad 8 Pro (piano) Linux

This public repository builds Ubuntu 24.04 arm64 GNOME rootfs and Xiaomi Pad 8 Pro (piano) Linux kernel/DTB artifacts.

Current verified artifacts

- Android boot v2 candidate: [workflow artifact](https://github.com/GUF296/xiaomi-pad-8-pro-linux/actions/runs/36783396723/artifacts/11129235714)
- Kernel, DTB and modules: [workflow artifact](https://github.com/GUF296/xiaomi-pad-8-pro-linux/actions/runs/36773372124/artifacts/11127065953)
- GNOME rootfs, initramfs, Image and DTB: [workflow artifact](https://github.com/GUF296/xiaomi-pad-8-pro-linux/actions/runs/36783396723/artifacts/11128905819)
- Public generic firmware stage: [piano-firmware-stage.tar.xz](./piano-firmware-stage.tar.xz)

The kernel is pinned to BigfootACA/linux commit 469998695964bc26493861cd11f8c17aa764f2e5. The piano configuration is merged as an additive fragment over arm64 defconfig. The rootfs uses signed Ubuntu debootstrap, GNOME Initial Setup, initramfs, LABEL=linux, and strict firmware manifest verification.

The Android boot candidate uses the Android header v2 path from the Xiaomi Pad 6S Pro reference workflow, with Image.gz and piano.dtb passed separately to mkbootimg. It is not yet a hardware-tested 8 Pro image. The stock piano firmware uses Android header v4 boot/vendor_boot/init_boot, so a v4-compatible combination and AVB/ABL verification remain before flashing.

Device-specific 8 Pro adaptations are kept separate from the 6S Pro reference: piano DTS, WCN7860 firmware path, panel/touch/backlight, thermal, charger and sensor nodes must be validated independently. Do not flash any artifact until the exact partition layout and boot chain are confirmed.
