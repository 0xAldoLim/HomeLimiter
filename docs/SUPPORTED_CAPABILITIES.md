# Supported capabilities

| Feature | Read-only Windows/Linux | Mock/demo | Experimental Linux routed agent | Inline bridge |
|---|---|---|---|---|
| Passive authorized neighbor inventory | Yes, configured CIDRs | Simulated | Managed LAN only | Read-only host observations |
| Nicknames / identity confirmation / protection | Yes | Yes | Yes | Yes |
| Per-device upload/download cap | No | Simulated | HTB/fq_codel, IFB ingress; kernel validation required | Disabled |
| Internet pause / resume | No | Simulated | IPv4/IPv6 forward rules LAN↔WAN | Disabled |
| Weekly / overnight / one-time / temporary policies | Stored controller state; restrictions refused | Simulated | Controller reconciliation + agent lease | Restrictions refused |
| Real throughput statistics / vendor lookup | Unavailable | Unavailable | Unavailable | Unavailable |
| Router-specific API | No | No | Unnecessary | No |

**DEMO MODE** is always simulated. **MONITOR ONLY** cannot apply restrictions.
**PARTIAL CONTROL** reports a configured experimental gateway after preflight checks;
available bandwidth/access controls remain subject to target-specific validation.
**FULL CONTROL** is modeled but is not emitted by this release: automated proof that
all of a real device's traffic uses the agent is not implemented. An API acknowledgement
means the owned kernel resources were installed, not that a measured rate was achieved.

Upload shaping happens before NAT on managed LAN ingress, download on LAN egress.
Caps cover matching target traffic on those managed interfaces, including traffic to
the gateway itself. Internet pause affects forwarding between configured LAN/WAN only,
preserving gateway-local administrative services. Alternate gateways/interfaces,
unobserved IPv6 privacy addresses, spoofed IP/MAC identities, VLAN encapsulation,
hardware offload, or client VPN/alternate physical links can invalidate traffic coverage.

Targets must be fresh, uniquely bound neighbor entries, confirmed by an administrator,
inside allowed CIDRs, and outside exclusions. MAC randomization produces a new identity;
there is no speculative merging. Unknown or stale observations suspend enforcement.
An inventory is not a complete household census. No active discovery, DHCP import,
managed router adapter implementation, or OUI database is included yet.

Intervals are half-open. Overnight weekly windows belong to their start day. Both
occurrences of an ambiguous DST hour follow the local time window; nonexistent local
times are skipped. A one-time policy uses explicit timezone-bearing instants. Conflicts
are surfaced on creation: pause wins and the lowest rate in each direction wins.
