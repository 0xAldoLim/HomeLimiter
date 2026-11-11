# Security

Use only explicitly authorized networks. HomeLimiter does not use spoofing, covert
interception, telemetry, endpoint installation or firewall flushes. It does not
configure forwarding, routing or your router.

A standalone terminal session opens no listener. The optional headless API binds to
127.0.0.1 only, validates the Host and request body, and authenticates every administrative
operation. Its clients read a private local credential. Anyone with that credential and
local API access is an administrator. Do not expose the headless port to a LAN or public proxy.

The separate agent uses verified HTTPS or literal loopback through a verified SSH
tunnel. Keep agent tokens in private files; avoid URLs, public logs and command histories.
Do not reuse the headless credential for an agent.

Disruptive policy changes require explicit target confirmation. Targets must be
fresh, unambiguous and confirmed. The agent independently checks protected addresses,
current neighbor bindings, CIDRs, route and resource ownership. MAC and IP observations
are not cryptographic identities. A missing or stale binding is not eligible.

The routed Linux agent remains experimental. Validate in disposable namespaces and
review [capabilities](docs/SUPPORTED_CAPABILITIES.md) and [recovery](docs/LINUX_SETUP.md#recovery).
When the controller cannot renew its lease, the running agent restores after expiry.
Abrupt agent death requires restart or documented manual recovery.

Report vulnerabilities privately to the repository owner. Review logs before sharing:
they can contain device identifiers and addresses. Do not include tokens or household
inventory in public issues.