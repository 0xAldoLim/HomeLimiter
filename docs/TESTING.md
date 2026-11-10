# Testing

Run ordinary unit/protocol tests as an unprivileged user:

```sh
python -m pytest
python -m ruff check src tests
python -m ruff format --check src tests
python -m build
```

Opt into actual browser tests against a disposable local demo instance:

```sh
python -m playwright install chromium
HOMELIMITER_BROWSER_TESTS=1 python -m pytest tests/test_browser.py
```

On Windows PowerShell set `$env:HOMELIMITER_BROWSER_TESTS='1'` first. To use an existing
Chrome installation, set `HOMELIMITER_BROWSER_EXE` to its full executable path.
The test launches a loopback server on a free port, uses a temporary state directory,
and terminates it afterward. Optional `HOMELIMITER_SCREENSHOT` saves a desktop preview
and sibling mobile screenshot. No tokens are stored in screenshots.

## Actual Linux kernel integration

Only in an explicitly authorized disposable Linux development environment, with
iproute2, nftables, iperf3 and ping installed and IFB/HTB/fq_codel/flower/mirred support:

```sh
sudo env HOMELIMITER_NET_TESTS=1 .venv/bin/python -m pytest tests/test_network.py -q -s
```

The integration test constructs three uniquely named namespaces (client, gateway,
server). Veth links are created directly inside them. Forwarding sysctls, nft tables,
qdiscs and addresses are changed only inside the disposable gateway. It tests IPv4
and IPv6 upload/download shaping with iperf3, pause/resume with ping, idempotent updates
and preservation of an unrelated table. Cleanup removes only the namespaces it created.
It must never use the live home network as a test target.

CI runs the controller suite/build on Windows and Ubuntu with Python 3.12 and 3.14,
a Chromium browser workflow, and a privileged disposable namespace job. Inspect the
actual Actions result before claiming the kernel integration passed. Tests cannot
certify an operator's household wiring, alternate paths or hardware offload behavior.
