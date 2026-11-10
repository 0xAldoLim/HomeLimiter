# Security

Use only explicitly authorized networks. No ARP/NDP spoofing, DNS poisoning, packet
content capture, covert redirection, endpoint installation, or antivirus evasion.
No telemetry. The application never configures your router or enables host forwarding.

The controller binds to loopback by default, authenticates every administrative API,
requires same-origin JSON for browser writes, validates Host, and uses a strict content
security policy. Admin tokens are random, stored outside the repository with restricted
permissions, and kept in browser memory only. Do not expose the controller to a LAN
without a reviewed TLS/authentication deployment. Anyone with the token is an admin.

Remote agents require HTTPS with CA verification and a separate bearer token.
Plain HTTP is permitted only to literal loopback for an SSH tunnel. SSH host verification
is the operator's responsibility. Tokens must not appear in URLs or command histories.

Disruptive policy creation requires a target-specific confirmation. Targets must have
fresh, unambiguous identities. Protected hosts cannot receive policies. The agent
validates allowed CIDRs, exclusions, live neighbor binding, routing and ownership again.
MAC addresses and IP observations are not cryptographic identities; this is a trusted
household LAN management tool, not protection against malicious address spoofing.

Linux enforcement is experimental until the namespace suite is executed on the intended
kernel. Never run integration tests on the live home network. Start with a disposable
Linux VM and read [supported capabilities](docs/SUPPORTED_CAPABILITIES.md).

Report vulnerabilities privately to the repository owner through GitHub's available
private reporting/contact mechanisms; do not include credentials or household inventory
in public issues. Review logs before sharing: they contain device IDs and addresses.
