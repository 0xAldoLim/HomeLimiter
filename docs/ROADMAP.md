# Remaining development work

This release delivers the controller and an experimental routed Linux backend.
It does not claim deployment-grade coverage of every household topology.

1. Validate physical Ethernet gateways across distribution/kernel combinations, hardware
   offload, MTUs, link speeds, packet loss and multiple simultaneous clients.
2. Implement evidence of per-target traffic traversal and address coverage before
   reporting FULL CONTROL. Installed rules alone do not prove all traffic is controlled.
3. Validate native inline bridge enforcement, VLANs, software/hardware bridge offload,
   management preservation and L2-specific recovery before enabling bridge mutations.
4. Add measured per-device tc/nft counters and sampled throughput, with clear reset and
   interval semantics. Current statistics are deliberately unavailable.
5. Add authorized DHCP lease/client-table imports and optional RouterAdapter plugins;
   improve identity handling for randomized MAC and IPv6 privacy addresses without
   merging uncertain devices or targeting stale addresses.
6. Add multi-user administration, token rotation UI, reviewed remote controller hosting,
   platform credential-vault integration, signed releases and reproducible hash locks.
7. Add a distribution-reviewed service sandbox/capability deployment for the agent and
   an external recovery watchdog for abrupt agent termination. Current root launch is
   manual; agent-death recovery requires restart or the documented recovery command.
8. Add exception calendars, configurable presets and audit/inventory retention. Continue
   testing terminal workflows across screen readers, terminals and narrow windows.

No remaining task authorizes changes to a user's actual network without explicit
deployment/target approval. Spoofing, covert interception and global firewall resets
are outside the project scope permanently.
