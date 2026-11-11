# Validation record

Run current checks using [Testing](TESTING.md) or inspect the
[HomeLimiter Actions runs](https://github.com/0xAldoLim/HomeLimiter/actions).
Portable tests exercise terminal workflows, settings, policy validation and rollback,
agent and controller authentication, lease renewal, restart, and expiry. Simulated
fixtures do not establish throughput or traffic coverage.

## Isolated gateway baseline

At code commit `31da725`, [the disposable namespace run](https://github.com/0xAldoLim/HomeLimiter/actions/runs/42741187914)
verified actual dual-stack traffic shaping at a 2 Mbps configured cap:

| Protocol and direction | iperf3 receiver Mbps |
|---|---:|
| IPv4 upload | 1.8864 |
| IPv4 download | 1.8874 |
| IPv6 upload | 1.8864 |
| IPv6 download | 1.8875 |

The fixture pinned dynamically observed bindings within the disposable namespaces
to avoid neighbor timer changes during measurements. IPv4 and IPv6 pause and recovery
worked, and an unrelated nftables table survived. That validation exposed and fixed
a collision between IPv4 and IPv6 traffic control filter priorities.

The current workflow retains the same isolated kernel test. The routed agent remains
experimental. The tests do not certify a physical gateway, an alternate network path,
inline bridge enforcement, or household hardware offload behavior.