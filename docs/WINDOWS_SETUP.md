# Windows 11 and PowerShell

Install Python 3.12+ from a trusted source with `python` on PATH. From the repository:

```powershell
.\scripts\bootstrap.ps1 -Demo -Launch
# In a second terminal, get the demo credential:
.\.venv\Scripts\homelimiter --demo token
```

If local script execution is disallowed, run the manual venv commands in
[INSTALLATION.md](INSTALLATION.md). Do not change machine-wide security policy.

The controller runs without administrator privileges. State directories and token files
are restricted with Windows ACLs to the current SID; initialization fails if that cannot
be done. Protect backups and terminals that display `homelimiter token`.

For passive real inventory, edit `%LOCALAPPDATA%\HomeLimiter\config.json`, configure your
authorized CIDRs, launch without `--demo`, and refresh. Discovery reads Get-NetNeighbor;
it sends no probe packets. Windows, VMware NAT and ordinary bridged guests provide no
arbitrary household-device throttling.

## Connect to a provisioned Linux agent

Choose either a reviewed HTTPS deployment with a trusted agent certificate, or a verified
SSH tunnel to the agent's default loopback listener:

```powershell
ssh -N -L 8788:127.0.0.1:8788 authorized-user@your-linux-gateway
```

Verify the SSH host fingerprint through your normal trusted channel. Copy the separate
agent admin token through an authorized secure channel into a private local file, then
configure `adapter: "gateway"`, `agent_url: "http://127.0.0.1:8788"` and an absolute
`agent_token_file` path. For remote HTTPS use `https://...` and `agent_ca_file` for a
private CA. Certificate verification is always enabled; redirects and environment
proxy inheritance are disabled. Never put a token into a URL.
