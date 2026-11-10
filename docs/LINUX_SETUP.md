# Linux controller and experimental gateway agent

Install Python 3.12+ and your distribution's venv support. Run `bash scripts/install-linux.sh`
as your ordinary user. On Kali, use the venv; do not use `--break-system-packages` or
`sudo pip`. The controller does not need root. The agent needs Linux networking privilege.

## Provisioning is separate

An operator must explicitly configure two routed interfaces, IPv4/IPv6 addressing,
forwarding, upstream routing/NAT where necessary, and household clients' gateway path.
HomeLimiter never does this. Test in disposable namespaces first. Inline bridge
enforcement is not enabled in this version.

Distribution tools: `iproute2` (`ip`, `tc`), `nftables`, kernel HTB, fq_codel, flower,
IFB, matchall and mirred support. Integration tests additionally need `iperf3` and ping.
Kernel modules must be supplied by your distribution; the agent does not load modules
automatically or change sysctls. Flowtable offload is refused. VLAN/VRF, multi-WAN,
policy routing and hardware bypass paths are not supported by this first backend.

Only explicitly dedicated LAN interfaces with unconfigured `0:` noqueue/pfifo_fast/
fq_codel roots are accepted. Existing custom roots, ingress or clsact cause refusal.
HomeLimiter owns a temporary root `1a10:`, ingress `ffff:`, IFB `hlifb0`, and the
`inet homelimiter` table. Never modify those while the agent is active. Ownership is
recorded in private agent state and the nft table/IFB comment/alias. The upstream WAN
qdiscs and unrelated nft tables are not modified. Removing the owned root restores the
kernel default, rather than reconstructing a previous custom shaper (custom roots are refused).

Copy `config/agent.example.json` to a private location and replace all documentation
addresses/interface names. Protect the management controller address, upstream gateway
and critical infrastructure. All local agent addresses are excluded automatically.
Only set `topology_authorized` and `exclusive_interfaces` to true after delegation.

```sh
# Manual opt-in launch on an already provisioned test gateway:
sudo .venv/bin/homelimiter-agent --config /absolute/path/agent.json --state /var/lib/homelimiter-agent
```

This binds to loopback port 8788. Read the separate token at the private agent state's
`admin.token` as its administrator and securely provision the controller's token file.
For non-loopback binding, `--tls-cert` and `--tls-key` are required. Use a certificate
trusted by the controller, restrict agent port access, and prefer a dedicated service
account/capability deployment reviewed for your distribution. A generic systemd/root
service is deliberately not installed automatically.

## Recovery

Graceful agent shutdown and agent restart remove owned resources. The running agent's
watchdog removes them on controller lease expiry (90 seconds, refreshed every 15 seconds).
If the agent is killed, kernel rules can remain until restart/manual recovery; no
watchdog can run inside a dead process. Do not delete the ownership journal.

```sh
# Stop the agent process first, then recover using the SAME config/state:
sudo .venv/bin/homelimiter-agent --config /absolute/path/agent.json --state /var/lib/homelimiter-agent --recover
# Remove desired policies too, with the controller stopped:
.venv/bin/homelimiter emergency-restore --yes
```

Do not use `nft flush ruleset`, broad tc cleanup, or network-manager reconfiguration
as a HomeLimiter recovery procedure. If recovery reports foreign ownership, investigate
the conflict instead of deleting resources owned by another administrator.
