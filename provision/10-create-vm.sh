#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$ROOT/provision/common.sh"
recreate=false
for arg in "$@"; do
  case $arg in --dry-run) DRY_RUN=true ;; --recreate) recreate=true ;; *) fail 'usage: 10-create-vm.sh [--recreate] [--dry-run]' ;; esac
done
load_config
require_local
lock_provision
if $recreate; then
  if $DRY_RUN; then "$ROOT/provision/99-destroy-vm.sh" --yes --dry-run; else "$ROOT/provision/99-destroy-vm.sh" --yes; fi
fi
run python3 "$ROOT/provision/lib/provision.py" ensure-pool
# Resume: a domain that verifiably belongs to this checkout (ownership record, UUID, disks) is reused.
if ! $recreate && ! $DRY_RUN && [[ -f "$PROVISION_STATE/vm.json" ]] && support check-domain >/dev/null 2>&1; then
  printf 'provision: replica %s already belongs to this checkout; skipping creation\n' "$VM_NAME"
  virsh --connect "$PROVISION_URI" domstate "$VM_NAME" | grep -qx running || virsh --connect "$PROVISION_URI" start "$VM_NAME"
  support wait-guest
  exit 0
fi
if $DRY_RUN; then
  show virsh --connect "$PROVISION_URI" dominfo "$VM_NAME"
  show python3 "$ROOT/provision/lib/provision.py" reserve
else
  # Reserve refuses an existing domain, volume or incomplete prior build.
  support reserve
fi
image_name=ubuntu-26.04-server-cloudimg-amd64.img
image_base=https://cloud-images.ubuntu.com/releases/26.04/release
image_dir="$PROVISION_STATE/image"
run install -d -m 0700 "$image_dir"
run curl --fail --location --proto '=https' --proto-redir '=https' --connect-timeout 30 --max-time 1800 --retry 3 --output "$image_dir/SHA256SUMS" "$image_base/SHA256SUMS"
run curl --fail --location --proto '=https' --proto-redir '=https' --connect-timeout 30 --max-time 1800 --retry 3 --output "$image_dir/$image_name.part" "$image_base/$image_name"
run python3 "$ROOT/provision/lib/provision.py" verify-image "$image_dir/$image_name.part" "$image_dir/SHA256SUMS" "$image_name"
run mv -- "$image_dir/$image_name.part" "$image_dir/$image_name"
run qemu-img convert -f qcow2 -O qcow2 "$image_dir/$image_name" "$image_dir/system.qcow2"
run qemu-img resize "$image_dir/system.qcow2" 40G
run python3 "$ROOT/provision/lib/provision.py" create-volumes "$image_dir/system.qcow2"
run ssh-keygen -q -t ed25519 -N '' -C "$VM_NAME" -f "$PROVISION_STATE/guest_host_ed25519"
run python3 "$ROOT/provision/lib/provision.py" cloud-init
if $DRY_RUN; then
  vm_uuid='<recorded UUID>'
else
  # Reload the UUID/volume names written by reserve.
  load_config
  vm_uuid=$PROVISION_VM_UUID
fi
run virt-install --connect "$PROVISION_URI" --name "$VM_NAME" --uuid "$vm_uuid" \
  --memory 16384 --vcpus 8 --arch x86_64 --virt-type kvm --osinfo detect=on,require=off \
  --import --boot hd --cloud-init "user-data=$PROVISION_STATE/user-data,meta-data=$PROVISION_STATE/meta-data" \
  --disk "vol=$PROVISION_STORAGE_POOL/$VM_NAME-system.qcow2,bus=virtio,format=qcow2" \
  --disk "vol=$PROVISION_STORAGE_POOL/$VM_NAME-data-a.qcow2,bus=virtio,format=qcow2" \
  --disk "vol=$PROVISION_STORAGE_POOL/$VM_NAME-data-b.qcow2,bus=virtio,format=qcow2" \
  --network "network=$PROVISION_NETWORK,model=virtio" --graphics none --noautoconsole
run python3 "$ROOT/provision/lib/provision.py" wait-guest
# The private host key is needed only to build the seed. Retain its public key
# for checked, repeatable SSH trust; remove plaintext private seed material.
run rm -f -- "$PROVISION_STATE/guest_host_ed25519" "$PROVISION_STATE/user-data"
