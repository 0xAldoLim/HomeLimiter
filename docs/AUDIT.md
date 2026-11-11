# Repository audit

Baseline: `18e623e` on `main`. This is a source and test review of the controller,
SQLite state, policy resolution, diagnostics, privileged gateway, packaging and CI.
The existing CI record proves behavior in disposable namespaces. It does not certify
a physical gateway, an arbitrary VM, or full traffic coverage.

| Severity | Finding | Remediation |
|---|---|---|
| High | The dashboard lifespan owns policy ticks and agent lease renewal. Closing its server can interrupt schedules. | Extract a controller runtime; give it an explicit headless entry point and reuse it for local terminal sessions. |
| High | A failed remove/resume restores rows but does not attempt to restore the previous effective snapshot. Multi-row writes are separate transactions. | Use one policy replacement transaction per change and one shared reconciliation/rollback path. Test both edit and removal failures. |
| High | One stale or unsuitable IPv6 address can make the whole desired gateway snapshot fail. Refresh failures can leave the previous inventory marked online. | Keep per-address validation at the agent. Project only fresh eligible routed bindings, report partial coverage, and stop lease renewal on failed discovery. |
| Medium | The gateway adapter silently falls back to monitor capabilities on protocol failure; the UI can confuse stored policy count with applied restrictions. | Report the latest acknowledged snapshot, lease state and errors separately from desired policy. Never treat acknowledgements as throughput verification. |
| Medium | Unchanged renewals write an audit entry every tick, and changing a nickname or ordering can cause needless kernel installs. | Compare enforcement-relevant fields and record transitions rather than every successful renewal. |
| Medium | Monitor configuration needs manual CIDR editing; Windows interface indexes and aliases are not presented together. | Make scope selection explicit in first-run setup and show actual interfaces/routes. Monitor never scans or applies restrictions. |
| Medium | Launchers rebuild/reinstall every run; onboarding requires a separate credential lookup and browser. | Bootstrap a local venv only as needed, validate configuration, and launch the terminal. Keep separate credentials for the optional headless API and agent. |
| Medium | UI setup cannot edit a policy atomically; recurring windows have no upcoming-action preview. | Add shared replace validation, preserve policy IDs, and calculate next window transitions in the policy layer. |
| Medium | Gateway ownership assumes exclusively delegated qdiscs; abrupt process death cannot execute the watchdog. | Preserve refusal of foreign objects, documented recovery, and disposable-kernel tests. Physical deployment and stronger privilege isolation remain follow-up work. |
| Low | Browser assets, fonts and browser automation add maintenance without serving the new terminal workflow. | Remove these from the package and CI after terminal and lifecycle tests pass. Keep the secured agent protocol and tested headless control API. |
| Low | Inventory records and audit history can grow; there are no reliable live per-device counters across all enforced paths. | Batch inventory updates, bound the default audit view and avoid inventing usage figures. Retention and counter validation remain follow-ups. |

The portable controller, scheduler math and local persistence are suitable for
monitoring and simulation. The managed routed Linux agent remains **experimental**:
its namespace tests exercise real IPv4/IPv6 shaping and recovery under controlled
conditions. Inline bridge enforcement, router integrations, per-device traffic
statistics and full-path verification are incomplete. MAC randomization creates a
new identity rather than transferring restrictions. Neighbor visibility remains
partial on switched networks and stale records are retained for history.