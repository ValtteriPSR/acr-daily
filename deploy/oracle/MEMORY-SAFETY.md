# Oracle VM memory safety

The 2 GiB VM can become unresponsive during a short memory spike. Before the
19 October 2026 outage, monitoring recorded approximately 96% memory use and
100% CPU, followed by missing guest metrics. The process responsible must be
identified from host diagnostics; these measurements alone do not identify it.

Run the host configuration as root:

```sh
sudo bash deploy/oracle/configure-memory-safety.sh
```

The script adds a 2 GiB swap file on the existing boot disk only when no swap is
active. It requires at least 4 GiB free, refuses to overwrite an existing file,
preserves the original fstab in `/opt/acr/memory-safety/fstab.before`, and sets
`vm.swappiness=10`. Existing active swap is retained unchanged. It does not
restart application/database containers or change the VM shape.

Verify with `swapon --show`, `free -m`, and `sysctl vm.swappiness`.
Swap provides headroom for transient pressure; sustained memory growth still
requires investigating the responsible process.
