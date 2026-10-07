#!/bin/bash
# Host-side runner. Never runs the installer on the CI host.
set -euo pipefail
release=$1
case "$release" in bookworm) version=12 ;; trixie) version=13 ;; *) exit 2 ;; esac
root=$(cd "$(dirname "$0")/../.." && pwd)
work=$(mktemp -d)
qemu_pid=''
trap '[[ -z "$qemu_pid" ]] || kill "$qemu_pid" 2>/dev/null || true; rm -rf "$work"' EXIT
image="debian-$version-generic-amd64.qcow2"
url="https://cloud.debian.org/images/cloud/$release/latest"
curl --location --fail --retry 3 "$url/$image" -o "$work/disk.qcow2"
curl --location --fail --retry 3 "$url/SHA512SUMS" -o "$work/SHA512SUMS"
checksum=$(awk -v file="$image" '$2 == file || $2 == "*"file {print $1}' "$work/SHA512SUMS")
[[ "$checksum" =~ ^[a-fA-F0-9]{128}$ ]]
printf '%s  %s\n' "$checksum" "$work/disk.qcow2" | sha512sum --check
qemu-img resize "$work/disk.qcow2" 20G
ssh-keygen -t ed25519 -N '' -f "$work/key"
cat > "$work/user-data" <<EOF
#cloud-config
ssh_pwauth: false
disable_root: false
users:
  - name: root
    ssh_authorized_keys:
      - $(cat "$work/key.pub")
write_files:
  - path: /etc/paimenos-integration-vm
    content: 'disposable test VM'
runcmd:
  - [mkdir, -p, /source]
  - [mount, -t, 9p, -o, 'trans=virtio,version=9p2000.L', source, /source]
EOF
printf 'instance-id: paimenos-test\nlocal-hostname: paimenos-test\n' > "$work/meta-data"
cloud-localds "$work/seed.iso" "$work/user-data" "$work/meta-data"
qemu-system-x86_64 -machine accel=kvm:tcg -cpu max -m 3072 -smp 2 -nographic -monitor none \
    -drive file="$work/disk.qcow2",if=virtio -drive file="$work/seed.iso",format=raw,if=virtio \
    -netdev user,id=ssh,hostfwd=tcp:127.0.0.1:2222-:22 -device virtio-net-pci,netdev=ssh,addr=3 \
    -netdev user,id=uplink -device virtio-net-pci,netdev=uplink,addr=4 \
    -virtfs local,path="$root",mount_tag=source,security_model=none,readonly=on \
    > "$root/vm-$release.log" 2>&1 &
qemu_pid=$!
ssh_vm() { ssh -i "$work/key" -p 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=5 root@127.0.0.1 "$@"; }
wait_ssh() {
    for attempt in {1..120}; do
        if ssh_vm true 2>/dev/null; then return; fi
        kill -0 "$qemu_pid" || { cat "$root/vm-$release.log"; return 1; }
        sleep 2
    done
    return 1
}
wait_ssh
ssh_vm cloud-init status --wait
ssh_vm bash /source/tests/integration/wifi-guest.sh install
boot_before=$(ssh_vm cat /proc/sys/kernel/random/boot_id)
ssh_vm systemctl reboot || true
for attempt in {1..120}; do
    boot_after=$(ssh_vm cat /proc/sys/kernel/random/boot_id 2>/dev/null || true)
    if [[ -n "$boot_after" && "$boot_after" != "$boot_before" ]]; then break; fi
    sleep 2
 done
[[ -n "$boot_after" && "$boot_after" != "$boot_before" ]]
ssh_vm 'mkdir -p /source 2>/dev/null; mountpoint -q /source || mount -t 9p -o trans=virtio,version=9p2000.L source /source'
ssh_vm bash /source/tests/integration/wifi-guest.sh reboot
