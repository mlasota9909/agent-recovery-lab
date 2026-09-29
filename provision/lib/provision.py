"""Local provisioning support, invoked by the Bash entry points."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import pwd
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))
from lab_config import load_env, write_local_env

STATE = ROOT / "var/provision"
USER = pwd.getpwuid(os.getuid()).pw_name
USER_HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
ENV: dict[str, str] = {}


def call(argv, *, check=True, stdin=None, timeout=180):
    result = subprocess.run([str(a) for a in argv], input=stdin, capture_output=True,
                            text=True, timeout=timeout, check=False, cwd=ROOT)
    if check and result.returncode:
        raise RuntimeError(f"{shlex.join(map(str, argv))}: exit {result.returncode}: "
                           f"{result.stderr.strip()} {result.stdout.strip()}")
    return result


def virsh(*args, **kwargs):
    return call(["virsh", "--connect", ENV["PROVISION_URI"], *args], **kwargs)


def guest(*argv, stdin=None, check=True, timeout=180):
    return call(["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                 "-o", "ConnectTimeout=10", ENV["VM_SSH"], shlex.join(map(str, argv))],
                stdin=stdin, check=check, timeout=timeout)


def atomic(path: Path, text: str, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".provision-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def record(path, data):
    atomic(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def configured_paths():
    paths = [Path(ENV[k]).resolve() for k in
             ("EVIDENCE_ROOT", "ARCHIVE_ROOT", "BASEBACKUP_ROOT", "RESULTS_ROOT")]
    for path in paths:
        if not path.is_relative_to(ROOT) or path == ROOT:
            raise RuntimeError(f"Host output root must be below this checkout: {path}")
    if len(set(paths)) != len(paths):
        raise RuntimeError("Host output roots must be distinct")
    return paths


def validate():
    if Path(ENV["LAB_ROOT"]).resolve() != ROOT:
        raise RuntimeError("LAB_ROOT must identify this checkout")
    if USER == "root" or ENV["HOST_ARCHIVE_USER"] != USER or ENV["PROVISION_USER"] != USER:
        raise RuntimeError("Run as the host archive user, with passwordless sudo")
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9-]{0,62}", ENV["VM_NAME"]):
        raise RuntimeError("VM_NAME must be a hostname")
    for key in ("DB_NAME", "SLOT_NAME", "ROLE_APP", "ROLE_AGENT", "DDL_AUDIT_TABLE", "HEARTBEAT_TABLE"):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", ENV[key]):
            raise RuntimeError(f"Unsafe identifier: {key}")
    for key in ("PG_DATA", "ARCHIVE_MOUNT_IN_VM", "MNT_PROTECTED", "SANDBOX_MNT",
                "ZPOOL", "DS_PARENT", "DS_PGDATA", "DS_PROTECTED", "SANDBOX_DATASET"):
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", ENV[key]):
            raise RuntimeError(f"Unsafe guest path or dataset: {key}")
    devices = [ENV[key] for key in ("DEV_SYSTEM", "DEV_A", "DEV_B")]
    if ENV["PG_VERSION"] != "18" or len(set(devices)) != 3 or any(
            not re.fullmatch(r"/dev/vd[a-z]+", device) for device in devices):
        raise RuntimeError("Expected PostgreSQL 18 and three distinct configured virtio devices")
    for key in ("PG_PORT", "SANDBOX_PORT"):
        if not ENV[key].isdigit() or not 1 <= int(ENV[key]) <= 65535:
            raise RuntimeError(f"Invalid port: {key}")
    configured_paths()


PACKAGES = {
    "virsh": "libvirt-clients", "virt-install": "virtinst", "qemu-img": "qemu-utils",
    "cloud-localds": "cloud-image-utils", "genisoimage": "genisoimage", "curl": "curl",
    "python3": "python3", "ssh": "openssh-client", "ssh-keygen": "openssh-client",
    "pg_recvlogical": "postgresql-client-18", "psql": "postgresql-client-18",
    "pg_basebackup": "postgresql-client-18", "duckdb": "duckdb", "rg": "ripgrep",
    "ip": "iproute2", "flock": "util-linux", "sudo": "sudo", "systemctl": "systemd",
    "sha256sum": "coreutils", "rsync": "rsync",
}


def missing_packages():
    missing = {package for command, package in PACKAGES.items()
               if not shutil.which(ENV.get("DUCKDB_BIN", "duckdb") if command == "duckdb" else command)}
    for package in ("libvirt-daemon-system", "qemu-system-x86", "openssh-server"):
        installed = call(["dpkg-query", "-W", "-f=${Status}", package], check=False)
        if installed.stdout != "install ok installed":
            missing.add(package)
    return sorted(missing)


def host_install():
    if not shutil.which("sudo") or call(["sudo", "-n", "true"], check=False).returncode:
        raise RuntimeError("Missing passwordless sudo; package installation cannot proceed")
    call(["sudo", "-n", "apt-get", "update"], timeout=1800)
    missing = missing_packages()
    # Old installed PostgreSQL clients are insufficient even if they are on PATH.
    if shutil.which("pg_recvlogical") and not re.search(r"\b18\.", call(["pg_recvlogical", "--version"]).stdout):
        missing.append("postgresql-client-18")
    unavailable = []
    available = []
    for package in sorted(set(missing)):
        policy = call(["apt-cache", "policy", package], check=False).stdout
        candidate = re.search(r"Candidate:\s+(\S+)", policy)
        (available if candidate and candidate[1] != "(none)" else unavailable).append(package)
    if available:
        # apt only supplies packages from the host's configured repositories.
        call(["sudo", "-n", "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y", *available], timeout=1800)
    if unavailable:
        raise RuntimeError("Missing apt candidates: " + ", ".join(unavailable) +
                           "; install these prerequisites from your approved package source")


def version(text):
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not match:
        raise ValueError(f"Cannot parse version: {text!r}")
    return tuple(int(x or 0) for x in match.groups())


def host_check():
    problems = []

    def check(label, fn):
        try:
            detail = fn()
            print(f"OK: {label}" + (f": {detail}" if isinstance(detail, str) and detail else ""))
        except Exception as exc:
            problems.append(f"MISSING: {label}: {exc}")

    def require(condition, message):
        if not condition:
            raise RuntimeError(message)

    check("site configuration", lambda: require((ROOT / "etc/lab.local.env").is_file(), "etc/lab.local.env"))
    check("configuration", validate)
    for command, package in PACKAGES.items():
        executable = ENV.get("DUCKDB_BIN", "duckdb") if command == "duckdb" else command
        check(command, lambda e=executable, p=package: require(shutil.which(e), f"{e} (apt package {p})"))
    os_release = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
    check("Ubuntu 26.04", lambda: require(os_release.get("ID", "").strip('"') == "ubuntu" and
                                          os_release.get("VERSION_ID", "").strip('"') == "26.04", "/etc/os-release differs"))
    check("passwordless sudo", lambda: call(["sudo", "-n", "true"]))
    check("libvirt group", lambda: require("libvirt" in call(["id", "-nG"]).stdout.split(), "new login in libvirt group required"))
    check("KVM device", lambda: call(["sudo", "-n", "test", "-c", "/dev/kvm"]))
    check("libvirt KVM support", lambda: require(
        ET.fromstring(virsh("capabilities").stdout).find(".//guest/arch[@name='x86_64']/domain[@type='kvm']") is not None,
        "x86_64 KVM capability"))
    check("libvirt >= 11", lambda: require(version(call(["virsh", "--version"]).stdout) >= (11, 0, 0), "libvirt >= 11"))
    check("virt-install >= 5.1", lambda: require(version(call(["virt-install", "--version"]).stdout) >= (5, 1, 0), "virt-install >= 5.1"))
    for command in ("pg_recvlogical", "psql", "pg_basebackup"):
        check(command + " 18", lambda c=command: require(version(call([c, "--version"]).stdout)[0] == 18, "PostgreSQL client 18"))
    check("DuckDB version", lambda: call([ENV["DUCKDB_BIN"], "--version"]).stdout.strip())
    check("system libvirt access", lambda: virsh("list", "--all"))
    check("libvirt NAT network", network)
    check("storage pool and free space", pool)
    check("checkout free space", lambda: require(shutil.disk_usage(ROOT).free >= 8 * 1024**3, "at least 8 GiB for image and seed"))
    key = Path(ENV.get("PROVISION_SSH_KEY", str(USER_HOME / ".ssh/id_ed25519"))).expanduser()
    check("host SSH key", lambda: require(key.is_file() and Path(str(key) + ".pub").is_file(), f"private key and {key}.pub"))
    check("host SSH public key format", lambda: call(["ssh-keygen", "-l", "-f", str(key) + ".pub"]))
    check("host SSH service", lambda: call(["systemctl", "is-active", "ssh"]))
    check("host SSH public key", lambda: require(Path("/etc/ssh/ssh_host_ed25519_key.pub").is_file(), "sshd ed25519 host key"))
    if problems:
        print("\n".join(problems), file=sys.stderr)
        raise RuntimeError(f"Host preflight failed: {len(problems)} missing prerequisite(s)")


def network():
    net = ENV["PROVISION_NETWORK"]
    xml = ET.fromstring(virsh("net-dumpxml", net).stdout)
    if xml.find("forward") is None or xml.find("forward").get("mode") != "nat":
        raise RuntimeError(f"libvirt network {net} must use NAT")
    info = virsh("net-info", net).stdout
    if not re.search(r"^Active:\s+yes$", info, re.M):
        raise RuntimeError(f"libvirt network {net} is not active")
    for node in xml.findall("ip"):
        address = node.get("address", "")
        if address and ipaddress.ip_address(address).version == 4:
            return address
    raise RuntimeError(f"libvirt network {net} has no IPv4 gateway")


def pool():
    name = ENV.get("PROVISION_STORAGE_POOL", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise RuntimeError("Set PROVISION_STORAGE_POOL in etc/lab.local.env")
    if name not in virsh("pool-list", "--all", "--name").stdout.splitlines():
        target = storage_path()
        parent = target
        while call(["sudo", "-n", "test", "-d", parent], check=False).returncode:
            if parent == parent.parent:
                raise RuntimeError("Cannot find the pool's filesystem")
            parent = parent.parent
        available = int(call(["sudo", "-n", "df", "-B1", "--output=avail", parent]).stdout.splitlines()[-1])
        if available < 150 * 1024**3:
            raise RuntimeError(f"New pool at {target} needs at least 150 GiB available")
        return f"will create directory pool {name} at {target}"
    xml = ET.fromstring(virsh("pool-dumpxml", name).stdout)
    if xml.get("type") != "dir":
        raise RuntimeError("PROVISION_STORAGE_POOL must be an existing directory pool for qcow2 files")
    if not re.search(r"^State:\s+running$", virsh("pool-info", name).stdout, re.M):
        raise RuntimeError(f"Storage pool {name} is not active")
    available = xml.find("available")
    if available is None or available.get("unit", "bytes") != "bytes" or int(available.text) < 150 * 1024**3:
        raise RuntimeError(f"Storage pool {name} needs at least 150 GiB available")
    return str(Path(xml.findtext("target/path")).resolve())


def storage_path():
    name = ENV.get("PROVISION_STORAGE_POOL", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise RuntimeError("Set PROVISION_STORAGE_POOL")
    target = Path(ENV.get("PROVISION_STORAGE_PATH", f"/var/lib/libvirt/images/{name}"))
    if not target.is_absolute() or target == Path("/") or ".." in target.parts or "," in str(target):
        raise RuntimeError("PROVISION_STORAGE_PATH must be an absolute directory path without '..' or commas")
    return target


def ensure_pool():
    name = ENV.get("PROVISION_STORAGE_POOL", "")
    pool()  # Validate the pool or the capacity of the prospective target.
    if name in virsh("pool-list", "--all", "--name").stdout.splitlines():
        return
    target = storage_path()
    # A new pool must not adopt a directory belonging to another pool.
    for other in [line.strip() for line in virsh("pool-list", "--all", "--name").stdout.splitlines() if line.strip()]:
        xml = ET.fromstring(virsh("pool-dumpxml", other).stdout)
        if xml.findtext("target/path") == str(target):
            raise RuntimeError(f"Storage path already belongs to pool {other}")
    if call(["sudo", "-n", "test", "-e", target], check=False).returncode == 0:
        raise RuntimeError("New pool path already exists; define the intended pool explicitly before retrying")
    virsh("pool-define-as", name, "dir", "--target", str(target))
    virsh("pool-build", name)
    virsh("pool-start", name)
    virsh("pool-autostart", name)


def state():
    data = json.loads((STATE / "vm.json").read_text())
    expected = {"system": f"{ENV['VM_NAME']}-system.qcow2", "data_a": f"{ENV['VM_NAME']}-data-a.qcow2",
                "data_b": f"{ENV['VM_NAME']}-data-b.qcow2"}
    if (data["root"] != str(ROOT) or data["name"] != ENV["VM_NAME"] or
            data["pool"] != ENV.get("PROVISION_STORAGE_POOL") or data["uuid"] != ENV.get("PROVISION_VM_UUID") or
            data["volumes"] != expected):
        raise RuntimeError("Replica ownership record conflicts with etc/lab.local.env; refusing")
    for key, config_key in (("system", "PROVISION_SYSTEM_VOLUME"), ("data_a", "PROVISION_DATA_A_VOLUME"), ("data_b", "PROVISION_DATA_B_VOLUME")):
        if ENV.get(config_key) != data["volumes"][key]:
            raise RuntimeError(f"{config_key} differs from replica ownership record")
    return data


def volume_names(pool: str) -> list[str]:
    """Volume names in a pool, parsed from the plain table (vol-list has no --name option in libvirt 11)."""
    lines = virsh("vol-list", "--pool", pool).stdout.splitlines()
    return [line.split()[0] for line in lines[2:] if line.split()]


def domains():
    return [line.strip() for line in virsh("list", "--all", "--name").stdout.splitlines() if line.strip()]


def check_domain():
    validate()
    data = state()
    xml = ET.fromstring(virsh("dumpxml", data["name"]).stdout)
    if xml.findtext("uuid") != data["uuid"]:
        raise RuntimeError("Domain UUID differs from the recorded replica; refusing")
    disks = [node for node in xml.findall("devices/disk") if node.get("device") == "disk"]
    expected = {str(Path(data["pool_path"]) / name) for name in data["volumes"].values()}
    sources = {node.find("source").get("file") for node in disks if node.find("source") is not None}
    if len(disks) != 3 or sources != expected:
        raise RuntimeError("Domain disk attachments differ from the three recorded replica disks")
    targets = {node.find("target").get("dev"): node.find("source").get("file") for node in disks
               if node.find("target") is not None and node.find("source") is not None}
    if targets != {device: str(Path(data["pool_path"]) / data["volumes"][kind])
                   for device, kind in ((Path(ENV["DEV_SYSTEM"]).name, "system"),
                                        (Path(ENV["DEV_A"]).name, "data_a"),
                                        (Path(ENV["DEV_B"]).name, "data_b"))}:
        raise RuntimeError("Replica attachments differ from the configured system/data devices")
    return data


def check_scope():
    current = Path(ENV["ARCHIVE_CURRENT"])
    marker = STATE / "baseline.json"
    if current.exists() or current.is_symlink():
        if not marker.exists():
            raise RuntimeError("An archive scope exists without this checkout's provisioning record; refusing guest configuration")
        scope = json.loads(marker.read_text())
        if current.resolve() != Path(scope["archive_dir"]).resolve():
            raise RuntimeError("An experiment replaced the provisioning archive scope; refusing guest configuration")


def reserve():
    validate()
    target = pool()
    network()
    if ENV["VM_NAME"] in domains():
        raise RuntimeError("Domain already exists; explicit --recreate is required")
    if (STATE / "vm.json").exists():
        raise RuntimeError("Previous build record exists; use --recreate to remove only its recorded resources")
    volumes = {"system": f"{ENV['VM_NAME']}-system.qcow2", "data_a": f"{ENV['VM_NAME']}-data-a.qcow2",
               "data_b": f"{ENV['VM_NAME']}-data-b.qcow2"}
    existing = volume_names(ENV["PROVISION_STORAGE_POOL"])
    for name in volumes.values():
        if name in existing or (Path(target) / name).exists():
            raise RuntimeError(f"Refusing existing volume/path {name}")
    data = {"root": str(ROOT), "name": ENV["VM_NAME"], "uuid": str(uuid.uuid4()),
            "pool": ENV["PROVISION_STORAGE_POOL"], "pool_path": target, "volumes": volumes}
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    record(STATE / "vm.json", data)
    write_local_env({"PROVISION_VM_UUID": data["uuid"], "PROVISION_SYSTEM_VOLUME": volumes["system"],
                     "PROVISION_DATA_A_VOLUME": volumes["data_a"], "PROVISION_DATA_B_VOLUME": volumes["data_b"]})


def verify_image(path, sums, filename):
    rows = [line.split() for line in Path(sums).read_text().splitlines()]
    matches = [row[0] for row in rows if len(row) == 2 and row[1].lstrip("*") == filename]
    if len(matches) != 1 or not re.fullmatch(r"[0-9a-fA-F]{64}", matches[0]):
        raise RuntimeError("Published SHA256SUMS lacks one unambiguous image digest")
    with open(path, "rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest.lower() != matches[0].lower():
        raise RuntimeError("Cloud image SHA256 mismatch")
    print(f"SHA256 verified: {filename} {digest}")


def create_volumes(system):
    data = state()
    for kind, name in data["volumes"].items():
        virsh("vol-create-as", data["pool"], name, "40G" if kind == "system" else "50G",
              "--allocation", "0", "--format", "qcow2")
        if kind == "system":
            virsh("vol-upload", "--pool", data["pool"], name, system, timeout=1800)


def cloud_init():
    data = state()
    key = Path(ENV.get("PROVISION_SSH_KEY", str(USER_HOME / ".ssh/id_ed25519"))).expanduser().resolve()
    public = Path(str(key) + ".pub").read_text().strip()
    if len(public.splitlines()) != 1:
        raise RuntimeError("Host SSH public key must contain one key")
    call(["ssh-keygen", "-l", "-f", str(key) + ".pub"])
    document = {
        "hostname": data["name"], "manage_etc_hosts": True, "ssh_pwauth": False,
        "disable_root": True, "users": [{"name": USER, "shell": "/bin/bash", "lock_passwd": True,
            "sudo": "ALL=(ALL) NOPASSWD:ALL", "groups": ["sudo"], "ssh_authorized_keys": [public]}],
        "ssh_keys": {"ed25519_private": (STATE / "guest_host_ed25519").read_text(),
                     "ed25519_public": (STATE / "guest_host_ed25519.pub").read_text().strip()},
        "package_update": True,
        "packages": ["zfsutils-linux", "postgresql-18", "postgresql-18-wal2json", "python3", "rsync", "openssh-client", "openssl"],
    }
    # JSON is valid YAML and preserves arbitrary SSH key comments safely.
    atomic(STATE / "user-data", "#cloud-config\n" + json.dumps(document, indent=2) + "\n")
    atomic(STATE / "meta-data", json.dumps({"instance-id": data["uuid"], "local-hostname": data["name"]}) + "\n")


def managed_block(path: Path, marker: str, body: str):
    old = path.read_text() if path.exists() else ""
    start, end = f"# BEGIN {marker}\n", f"# END {marker}\n"
    if (start in old) != (end in old):
        raise RuntimeError(f"Incomplete managed block in {path}")
    pattern = re.escape(start) + r".*?" + re.escape(end)
    remainder = re.sub(pattern, "", old, flags=re.S)
    atomic(path, start + body + end + remainder)


def ssh_alias(data):
    return f"lab-provision-{data['name']}-{data['uuid'][:8]}"


def trust_guest(address, data):
    alias = ssh_alias(data)
    key = Path(ENV.get("PROVISION_SSH_KEY", str(USER_HOME / ".ssh/id_ed25519"))).expanduser().resolve()
    host_key = (STATE / "guest_host_ed25519.pub").read_text().split()
    known = STATE / "known_hosts"
    atomic(known, f"{alias} {host_key[0]} {host_key[1]}\n")
    ssh_dir = USER_HOME / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    os.chmod(ssh_dir, 0o700)
    quote = lambda v: '"' + str(v).replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"') + '"'
    body = (f"Host {alias}\n  HostName {address}\n  User {USER}\n  HostKeyAlias {alias}\n"
            f"  IdentityFile {quote(key)}\n  IdentitiesOnly yes\n  StrictHostKeyChecking yes\n"
            f"  UserKnownHostsFile {quote(known)}\n\nHost *\n\n")
    managed_block(ssh_dir / "config", "lab-provision-" + hashlib.sha256(str(ROOT).encode()).hexdigest()[:16], body)
    ENV["VM_SSH"] = alias


def wait_guest():
    data = check_domain()
    deadline = time.monotonic() + int(ENV.get("PROVISION_WAIT_SECONDS", "1800"))
    address = None
    while time.monotonic() < deadline:
        output = virsh("domifaddr", data["name"], "--source", "lease").stdout
        matches = re.findall(r"\bipv4\s+(\d+\.\d+\.\d+\.\d+)/\d+", output)
        if matches:
            address = str(ipaddress.IPv4Address(matches[0]))
            trust_guest(address, data)
            if guest("true", check=False).returncode == 0:
                break
        time.sleep(5)
    else:
        raise RuntimeError("Timed out waiting for the replica DHCP lease and SSH")
    remaining = max(1, int(deadline - time.monotonic()))
    guest("sudo", "-n", "cloud-init", "status", "--wait", timeout=remaining)
    route = json.loads(call(["ip", "-j", "-4", "route", "get", address]).stdout)[0]
    host_address = str(ipaddress.IPv4Address(route["prefsrc"]))
    write_local_env({"VM_ADDR": address, "VM_SSH": ENV["VM_SSH"], "LAB_HOST": host_address,
                     "HOST_PG_CIDR": host_address + "/32", "HOST_ARCHIVE_USER": USER})
    print(f"Guest ready: {ENV['VM_SSH']} ({address}); host source {host_address}")


def host_roots():
    validate()
    for path in configured_paths():
        path.mkdir(parents=True, exist_ok=True, mode=0o750)
        os.chmod(path, 0o750)
    readme = Path(ENV["EVIDENCE_ROOT"]) / "README-evidence.md"
    if not readme.exists():
        atomic(readme, "Evidence files are append-only while open and mode 0444 once closed.\n"
               "Only the capture commands write evidence; WAL enters through the restricted append channel.\n", 0o444)


def wal_channel():
    check_domain()
    # LAB_HOST is the actual route source recorded at guest creation, not an
    # assumed default NAT address or a hostname dependent on guest DNS.
    host_address = str(ipaddress.IPv4Address(ENV["LAB_HOST"]))
    host_key = Path("/etc/ssh/ssh_host_ed25519_key.pub").read_text().split()
    pin = f"{host_address} {host_key[0]} {host_key[1]}\n"
    result = guest("sudo", "-n", "bash", "-s", "--", ENV["ARCHIVE_MOUNT_IN_VM"], host_address,
                   stdin=r'''set -euo pipefail
endpoint=$1 host=$2
install -d -o postgres -g postgres -m 0700 "$endpoint"
key="$endpoint/wal_append_ed25519"
if [[ ! -f $key ]]; then
  sudo -n -u postgres ssh-keygen -q -t ed25519 -N '' -C lab-wal-append -f "$key"
fi
chown postgres:postgres "$key"
chmod 0600 "$key"
if [[ ! -s $key.pub ]]; then
  sudo -n -u postgres ssh-keygen -y -f "$key" >"$key.pub"
fi
cat "$key.pub"
''')
    public = result.stdout.strip()
    call([ROOT / "bin/lab-wal-receiver-key"], stdin=public + "\n")
    marker = "lab-wal-checkout-" + hashlib.sha256(str(ROOT).encode()).hexdigest()[:16]
    auth = USER_HOME / ".ssh/authorized_keys"
    auth.parent.mkdir(mode=0o700, exist_ok=True)
    os.chmod(auth.parent, 0o700)
    old = auth.read_text().splitlines() if auth.exists() else []
    retained = [row for row in old if not row.endswith(" " + marker)]
    key_blob = public.split()[1]
    if any(key_blob in row.split() for row in retained):
        raise RuntimeError("WAL key already has an unmanaged authorized_keys entry; refusing to widen its access")
    # Drop the arbitrary public-key comment so the checkout marker is unique.
    fields = public.split()
    line = call([ROOT / "bin/lab-wal-receiver-key"], stdin=" ".join(fields[:2]) + "\n").stdout.strip()
    atomic(auth, "\n".join([*retained, line + " " + marker]) + "\n")
    guest("sudo", "-n", "bash", "-s", "--", host_address, pin,
          stdin=r'''set -euo pipefail
host=$1 pin=$2
pg_home=$(getent passwd postgres | cut -d: -f6)
install -d -o postgres -g postgres -m 0700 "$pg_home/.ssh"
known="$pg_home/.ssh/known_hosts"
touch "$known"
# Replace only this endpoint; retain unrelated host pins.
python3 - "$known" "$host" "$pin" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
rows = [r for r in p.read_text().splitlines() if not r.startswith(sys.argv[2] + ' ')]
p.write_text('\n'.join(rows) + ('\n' if rows else '') + sys.argv[3])
PY
chown postgres:postgres "$known"
chmod 0600 "$known"
''')


def consumer_unit():
    validate()
    rendered = call([ROOT / "bin/lab-consumer-unit"]).stdout
    target = Path(f"/etc/systemd/system/{ENV.get('CONSUMER_UNIT', 'lab-consumer')}@.service")
    record = STATE / target.name
    ours = target.exists() and record.exists() and target.read_text() == record.read_text()
    if target.exists() and target.read_text() != rendered and not ours:
        # The legacy consumer has a single global template. Do not take it
        # away from a second checkout or interrupt its active experiments.
        raise RuntimeError(f"Existing {target.name} differs from this checkout; set a unique CONSUMER_UNIT or remove it; refusing to replace it")
    if not target.exists() or (ours and target.read_text() != rendered):
        # Install, or replace this checkout's own earlier rendering (recorded copy matches).
        source = STATE / target.name
        atomic(source, rendered, 0o644)
        call(["sudo", "-n", "install", "-m", "0644", source, target])
        call(["sudo", "-n", "systemctl", "daemon-reload"])


def baseline():
    data = check_domain()
    marker = STATE / "baseline.json"
    current = Path(ENV["ARCHIVE_CURRENT"])
    if marker.exists():
        scope = json.loads(marker.read_text())
        current_present = current.exists() or current.is_symlink()
        if current_present and current.resolve() != Path(scope["archive_dir"]).resolve():
            raise RuntimeError("Provisioning scope no longer active; refusing to repoint an experiment archive")
        if scope["vm_uuid"] != data["uuid"]:
            # Recreation preserves old evidence, stops only its own consumer,
            # and allocates a new archive scope for the new PostgreSQL timeline.
            call([ROOT / "bin/lab-consumer", "stop", scope["incident"]])
            current.unlink(missing_ok=True)
            marker.unlink()
        elif not current_present:
            raise RuntimeError("Provisioning archive pointer is absent for this VM; refusing to guess its state")
    if not marker.exists():
        if current.exists() or current.is_symlink():
            raise RuntimeError("archive/current already exists without a provisioning record; refusing to replace it")
        # lab-incident starts consumers for SC-01. This is a substrate smoke
        # scope only: no workload, injection, or study invocation takes place.
        result = call([ROOT / "bin/lab-incident", "--new", "--scenario", "SC-01"], check=False, timeout=300)
        # --new publishes the scope before starting the consumer. Record that
        # scope on consumer failure too, so fixing access permits a retry.
        scope = json.loads(call([ROOT / "bin/lab-incident", "--current"]).stdout)
        scope["vm_uuid"] = data["uuid"]
        scope["purpose"] = "provisioning-only"
        record(marker, scope)
        if result.returncode:
            raise RuntimeError(f"Provisioning scope recorded, but consumer start failed: {result.stderr}")
    call([ROOT / "bin/lab-consumer", "start", scope["incident"]], timeout=300)
    records = Path(scope["archive_dir"]) / "snapshots.json"
    rows = json.loads(records.read_text()) if records.exists() else []
    for key in ("SNAP_PRISTINE", "SNAP_PRE_INJECTION", "SNAP_POST_CAPTURE"):
        label = ENV[key]
        matches = [r for r in rows if r.get("label") == label and not r.get("invalidated")]
        if len(matches) > 1:
            raise RuntimeError(f"Ambiguous provisioning snapshot label: {label}")
        if not matches:
            row = json.loads(call([ROOT / "bin/lab-snapshot", "--label", label]).stdout)
            rows.append(row)
    # All three labels represent an undamaged baseline. Reset is installed in
    # bin/lab-reset; provisioning never silently rolls back an existing lab.
    print(json.dumps({"ok": True, "incident": scope["incident"], "snapshots": rows}, sort_keys=True))


def destroy():
    validate()
    if not (STATE / "vm.json").exists():
        if ENV["VM_NAME"] in domains():
            raise RuntimeError("No checkout ownership record for this domain; refusing deletion")
        print("Replica already absent; no resources removed")
        return
    data = state()
    names = domains()
    if data["name"] in names:
        check_domain()
    # Verify the storage pool has not been redirected since creation.
    pool_xml = ET.fromstring(virsh("pool-dumpxml", data["pool"]).stdout)
    if pool_xml.get("type") != "dir" or str(Path(pool_xml.findtext("target/path")).resolve()) != data["pool_path"]:
        raise RuntimeError("Storage pool target changed; refusing deletion")
    expected = {str(Path(data["pool_path"]) / name) for name in data["volumes"].values()}
    present = set(volume_names(data["pool"]))
    for name in data["volumes"].values():
        if name in present:
            xml = ET.fromstring(virsh("vol-dumpxml", "--pool", data["pool"], name).stdout)
            if xml.findtext("target/path") != str(Path(data["pool_path"]) / name):
                raise RuntimeError("Volume target differs from recorded path; refusing deletion")
    # Check every other domain before making any changes, including inactive
    # definitions and backing stores. Never delete shared storage.
    for name in names:
        if name == data["name"]:
            continue
        documents = [virsh("dumpxml", name).stdout]
        if re.search(r"^Persistent:\s+yes$", virsh("dominfo", name).stdout, re.M):
            documents.append(virsh("dumpxml", name, "--inactive").stdout)
        for document in documents:
            xml = ET.fromstring(document)
            for source in xml.findall(".//source"):
                file = source.get("file")
                if (file and str(Path(file).resolve()) in expected) or (
                        source.get("pool") == data["pool"] and source.get("volume") in data["volumes"].values()):
                    raise RuntimeError(f"Another domain references replica storage: {name}")
    marker = STATE / "baseline.json"
    if marker.exists():
        scope = json.loads(marker.read_text())
        if scope["vm_uuid"] == data["uuid"]:
            if not re.fullmatch(r"SC-01_[0-9]{8}T[0-9]{6}Z", scope["incident"]):
                raise RuntimeError("Invalid provisioning consumer instance")
            unit = Path(f"/etc/systemd/system/{ENV.get('CONSUMER_UNIT', 'lab-consumer')}@.service")
            if unit.exists():
                if unit.read_text() != call([ROOT / "bin/lab-consumer-unit"]).stdout:
                    raise RuntimeError("Consumer template belongs to another configuration; refusing cleanup")
                call(["sudo", "-n", "systemctl", "stop", f"{ENV.get('CONSUMER_UNIT', 'lab-consumer')}@{scope['incident']}.service"])
            current = Path(ENV["ARCHIVE_CURRENT"])
            if current.is_symlink() and current.resolve() == Path(scope["archive_dir"]).resolve():
                current.unlink()
    if data["name"] in names:
        active = virsh("list", "--name").stdout.splitlines()
        if data["name"] in active:
            virsh("destroy", data["name"])
        virsh("undefine", data["name"])
    for name in data["volumes"].values():
        if name in present:
            virsh("vol-delete", "--pool", data["pool"], name)
    # Retain evidence, archives and baseline ownership for safe scope rollover
    # if a replacement replica is subsequently configured in this checkout.
    for name in ("vm.json", "guest_host_ed25519", "guest_host_ed25519.pub", "user-data", "meta-data", "known_hosts"):
        (STATE / name).unlink(missing_ok=True)
    print(f"Removed only replica {data['name']} and its three recorded volumes")


def main():
    global ENV
    ENV = load_env(ROOT)
    os.environ["LC_ALL"] = "C"
    action, *args = sys.argv[1:]
    commands = {"host-check": host_check, "host-install": host_install, "reserve": reserve,
                "verify-image": verify_image, "create-volumes": create_volumes, "cloud-init": cloud_init,
                "wait-guest": wait_guest, "check-domain": check_domain, "check-scope": check_scope,
                "ensure-pool": ensure_pool, "host-roots": host_roots,
                "wal-channel": wal_channel, "consumer-unit": consumer_unit, "baseline": baseline, "destroy": destroy}
    commands[action](*args)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"provision: {exc}", file=sys.stderr)
        raise SystemExit(1)
