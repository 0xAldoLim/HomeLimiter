# Testing

Run the unprivileged suite and package checks in the development venv:

```sh
python -m pytest
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m build
```

Textual's headless driver exercises the real keyboard workflows at 80×24 and 68×20:
inventory, protected devices, form validation, cancellation, policy creation and
removal, schedule editing, first-run scope selection and setup rerun. Use a temporary
state directory and the demo profile when testing an interactive launch. The API
suite uses in-process test clients; CI also checks that both launchers can create and
reuse a fresh environment.

Runtime tests verify renewal with no TUI client, graceful shutdown without deleting
desired policies, re-evaluation after restart and expiry, failed discovery, and
database/adapter rollback. They simulate agent failures. They do not measure traffic.

## Actual Linux kernel integration

Only in an explicitly authorized disposable Linux development environment, with
iproute2, nftables, iperf3 and ping installed and IFB/HTB/fq_codel/flower/mirred support:

```sh
sudo env HOMELIMITER_NET_TESTS=1 .venv/bin/python -m pytest tests/test_network.py -q -s
```

Three unique network namespaces contain the client, gateway and server. Veth links,
forwarding sysctls, nftables tables and qdiscs exist only inside these namespaces.
The test measures IPv4/IPv6 shaping, pause/restoration, repeat application, and
preservation of an unrelated table. Cleanup deletes only the namespaces it created.

CI runs the controller suite/build on Windows and Ubuntu with Python 3.12 and 3.14,
fresh launchers on both platforms, and the disposable namespace suite on Linux.
A passing suite is not certification of an operator's physical topology.