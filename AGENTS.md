# HomeLimiter contributor instructions

Keep policy validation and enforcement in shared services; terminal, CLI and API
handlers should call those services. Preserve explicit target confirmation, protected
infrastructure checks, bounded leases and rollback. Never invent throughput,
neighbor reachability or traffic-path verification.

Run the portable tests and Ruff before committing. Privileged tests must run only
in disposable Linux namespaces. Never test on a live household network. Update the
relevant setup and capability documentation when behavior changes.