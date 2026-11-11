# Windows setup

Install Python 3.12+ and Git. In PowerShell, enter the checkout and run:

```powershell
.\run.ps1
# Optional practice profile:
.\run.ps1 --demo
```

Run without administrator privileges. The launcher checks the existing venv or looks for
`py`, `python`, or `python3`. If it picks the wrong interpreter, set
`$env:HOMELIMITER_PYTHON` to the full path of a compatible Python executable before
creating a fresh venv. Rename an incompatible `.venv` before rerunning.

If PowerShell blocks the script, inspect `Get-ExecutionPolicy -List`. A downloaded copy
may have an Internet zone marker. After verifying the checkout and script, you can remove
the marker for this file only with `Unblock-File -LiteralPath .un.ps1`. If an
organization policy disallows scripts, use the [manual venv commands](INSTALLATION.md)
or ask your administrator. No machine-wide policy change is needed.

The app restricts its state and token using Windows ACLs. Keep backups and credentials
private. Setup reads the Windows neighbor cache and shows route/interface information;
it sends no scan probes. A Windows or VMware client cannot limit unrelated LAN traffic.

## Connect to a provisioned Linux agent

Use **Network → Setup wizard → Existing authorized gateway agent**. Choose a reviewed
HTTPS deployment with a trusted certificate, or a verified SSH tunnel to the agent's
loopback listener:

```powershell
ssh -N -L 8788:127.0.0.1:8788 authorized-user@your-linux-gateway
```

Verify the SSH host fingerprint through a trusted channel. In the wizard, use the origin
`http://127.0.0.1:8788` for the tunnel and the path to the separate private agent token
file. For HTTPS, enter the `https://` origin and a CA certificate file when required.
TLS verification stays enabled. Do not put credentials in URLs.