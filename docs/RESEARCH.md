# Research and design decisions

Reviewed 2026-11-10. Original implementation; no source code copied from these projects.
Licenses below describe referenced projects, not a license grant for their dependencies.

| Project | Architecture and limitations | License / decision |
|---|---|---|
| [EvilLimiter](https://github.com/bitbrute/evillimiter), [README](https://raw.githubusercontent.com/bitbrute/evillimiter/master/README.md) | ARP spoofing moves traffic through a Linux shaping host; depends on L2 reachability and privilege. | MIT. Reuse the inventory/policy concept only. Spoofing and global flushing are excluded. |
| [FireHOL / FireQOS](https://github.com/firehol/firehol), [README](https://raw.githubusercontent.com/firehol/firehol/master/README.md) | Declarative firewall and tc shaping configuration; Linux and privileged installation. | GPL-2.0 project. Learn declarative reconciliation and explicit direction; do not vendor scripts. |
| [qosify](https://github.com/openwrt/qosify), [README](https://raw.githubusercontent.com/openwrt/qosify/master/README), [license header](https://github.com/openwrt/qosify/blob/master/main.c) | eBPF DSCP classifier plus CAKE; integrates with OpenWrt ubus/netifd. Link fairness/priority is different from arbitrary per-device hard caps. | GPL-2.0-or-later header in main.c. No code copied; OpenWrt coupling unsuitable for the primary controller. |
| [AdGuard Home](https://github.com/AdguardTeam/AdGuardHome) | Cross-platform local web management of a managed DNS service. DNS filtering cannot ensure an internet pause when clients use alternate resolvers/IPs. | GPL-3.0 project. Adopt transparent local setup and diagnostics concepts, not DNS interception or code. |
| [LuCI](https://github.com/openwrt/luci), [license](https://github.com/openwrt/luci/blob/master/LICENSE) | Modular browser administration tied to OpenWrt configuration and RPC. | Apache-2.0 root license; individual package exceptions must be checked. Learn capability-aware views; no OpenWrt requirement. |

## Kernel references

- [tc](https://man7.org/linux/man-pages/man8/tc.8.html): egress qdisc hierarchy; ingress policing differs from queued shaping.
- [HTB](https://man7.org/linux/man-pages/man8/tc-htb.8.html): class rate/ceil and explicit classification support hard per-device caps.
- [CAKE](https://man7.org/linux/man-pages/man8/tc-cake.8.html): good aggregate fairness/AQM; host isolation is not a configurable hard cap per device. HTB plus fq_codel leaves chosen first.
- [flower](https://man7.org/linux/man-pages/man8/tc-flower.8.html): IPv4/IPv6 source/destination selectors; software-only filters avoid unverified hardware offload.
- [nftables upstream manual](https://www.netfilter.org/projects/nftables/manpage.html): inet handles both families; bridge hooks handle L2 forwarding; batch transactions and explicit table ownership avoid global ruleset replacement.
- [Linux bridge](https://docs.kernel.org/networking/bridge.html): a real inline bridge must lie in the forwarding path. VLANs and offload require additional validation.
- [network namespaces](https://man7.org/linux/man-pages/man7/network_namespaces.7.html) and [veth](https://man7.org/linux/man-pages/man4/veth.4.html): isolate interfaces, routes and firewall state for disposable integration tests.
- [Netlink](https://docs.kernel.org/userspace-api/netlink/intro.html): structured kernel interface. iproute2 JSON is used as the initial Netlink frontend, without a shell; native pyroute2 can replace it behind the same adapter.
- [IPv4/IPv6 forwarding sysctls](https://docs.kernel.org/networking/ip-sysctl.html): forwarding must be configured by the operator; IPv6 RA behavior needs deliberate gateway setup.

## Strategy comparison

| Strategy | Effectiveness / performance | Portability / privilege | Reliability / deployment / maintenance |
|---|---|---|---|
| Passive neighbor inventory | Local observations only; negligible overhead | Windows/Linux, often unprivileged | Incomplete/stale caches; no enforcement claim |
| Linux routed gateway | All correctly routed traffic; kernel HTB/nft performance depends on hardware | Linux CAP_NET_ADMIN/root agent | Two managed links, IPv4/IPv6 routes, careful ownership; chosen primary experimental backend |
| Inline Linux bridge | Only traversing frames; hardware offload may bypass software | Linux bridge + privileged agent | More topology/VLAN/offload risk; initial adapter reports unsupported rather than promising controls |
| Authorized router API | Depends on API and router capabilities | Brand dependent, admin credential | Future adapter abstraction; optional integration |
| Endpoint agent | Controls only installed endpoint | Per-OS privileged installation | Not implemented; explicit deployment permission required |
| Spoofing / covert redirection | Fragile, disruptive, often incomplete IPv6 coverage | Privileged L2 access | Forbidden by project constraints |

## Dependency/license policy

HomeLimiter original code is MIT. Python packages are installed through declared metadata,
not copied. `pip-audit`, a lock file from a tested environment, and CI cover dependency
review. Runtime tools iproute2/nftables are separately installed distribution packages.
Their licenses apply to those packages; invocation does not copy them into this project.
No vendor database is bundled, so vendor names remain unknown unless reliably supplied.
