# Network topologies

## Ordinary Windows PC and existing household router

```mermaid
flowchart LR
    PC[Windows controller / monitor] --- Router[Existing household router]
    Devices[Other devices] --- Router
    Router --- Internet
```

Device traffic does not traverse the PC. Local neighbor information and diagnostics
are possible; arbitrary bandwidth/access enforcement is not. Router brand is irrelevant.

## Authorized routed Linux gateway

```mermaid
flowchart LR
    Devices[Managed devices] --> LAN[Linux gateway LAN]
    LAN --> WAN[Linux gateway WAN]
    WAN --> Router[Existing router / upstream]
    Router --> Internet
    Windows[Windows controller] -. authenticated TLS / SSH tunnel .-> LAN
```

The operator explicitly provisions routes, forwarding, exclusions and delegated
interfaces. The existing router can remain upstream; it need not expose a proprietary API.
Both IPv4 and IPv6 must use this path. HomeLimiter manages its own rules only.

## Inline Linux bridge (future enforcement)

```mermaid
flowchart LR
    Devices[Managed network] --- PortA[Bridge port A]
    PortA --- Bridge[Linux software bridge]
    Bridge --- PortB[Bridge port B]
    PortB --- Router[Existing household router]
```

A real bridge must be physically inline; a VM merely using bridged mode is different.
The current bridge adapter is monitor-only. Native nft bridge hooks, VLAN filtering,
offload detection and physical-path tests are remaining work.

## Kali in VMware / unsupported environment

```mermaid
flowchart LR
    Kali[Kali controller in VM] --> Virtual[VMware NAT or bridged virtual NIC]
    Virtual --> Router[Household router]
    Other[Other household devices] --> Router
```

Neither VM mode guarantees household traffic crosses Kali. Use it for diagnostics,
development and isolated namespace tests. A deliberately routed VM with two delegated
interfaces is a separate operator-provisioned topology, subject to the gateway checks.
Wi-Fi isolation, shared public networks, unknown networks and alternate unmanaged
paths are unsupported enforcement environments.
