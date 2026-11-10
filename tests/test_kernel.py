import json

import httpx
import pytest
from fastapi.testclient import TestClient

from homelimiter.adapters import AdapterError, LinuxGatewayAdapter
from homelimiter.agent import create_agent
from homelimiter.config import Settings
from homelimiter.kernel import AgentConfig, LinuxEngine
from homelimiter.models import Device, Effective, Snapshot


@pytest.fixture
def config():
    return AgentConfig(
        lan="lan0",
        wan="wan0",
        authorized_cidrs=["192.0.2.0/24", "2001:db8::/64"],
        protected_addresses=["192.0.2.254"],
        topology_authorized=True,
        exclusive_interfaces=True,
    )


@pytest.fixture
def item():
    return Effective(
        device=Device(
            id="target",
            source="neighbor-cache",
            interface="lan0",
            confirmed=True,
            status="online",
            mac="02:00:00:00:00:02",
            addresses=["192.0.2.2", "2001:db8::2"],
        ),
        download_mbps=2,
        upload_mbps=1,
        blocked=True,
    )


def test_firewall_is_isolated_and_dual_stack(config, item, tmp_path):
    engine = LinuxEngine(config, tmp_path)
    script = engine.firewall_script([item], exists=True)
    assert "flush ruleset" not in script
    assert script.startswith("delete table inet homelimiter")
    assert "ip saddr 192.0.2.2" in script and "ip6 daddr 2001:db8::2" in script
    assert 'iifname "lan0" oifname "wan0"' in script
    commands = engine.shaping_commands([item])
    filters = [c for c in commands if "flower" in c]
    assert len(filters) == 4
    assert all("skip_hw" in c for c in filters)
    assert any("src_ip" in c and "hlifb0" in c for c in filters)
    assert any("dst_ip" in c and "lan0" in c for c in filters)
    assert all(isinstance(c, list) for c in commands)


def test_rollback_and_lease_watchdog(config, item, tmp_path, monkeypatch):
    engine = LinuxEngine(config, tmp_path)
    monkeypatch.setattr(engine, "preflight", lambda: None)
    monkeypatch.setattr(engine, "validate_targets", lambda _: None)
    operations = []

    def install(items):
        operations.append(items)
        if items and items[0].blocked:
            raise AdapterError("injected kernel failure")

    monkeypatch.setattr(engine, "_install", install)
    with pytest.raises(AdapterError, match="previous owned snapshot restored"):
        engine.apply(Snapshot(policies=[item]))
    assert operations[-1] == [] and engine.policies == []
    item.blocked = False
    engine.apply(Snapshot(policies=[item]))
    assert engine.policies and engine.deadline > 0
    recovered = []
    monkeypatch.setattr(engine, "recover", lambda: recovered.append(True))
    engine.deadline = 1
    assert engine.watchdog() and recovered


def test_rollback_failure_is_visible(config, item, tmp_path, monkeypatch):
    engine = LinuxEngine(config, tmp_path)
    monkeypatch.setattr(engine, "preflight", lambda: None)
    monkeypatch.setattr(engine, "validate_targets", lambda _: None)
    monkeypatch.setattr(engine, "_install", lambda _: (_ for _ in ()).throw(AdapterError("fault")))
    with pytest.raises(AdapterError, match="rollback failed"):
        engine.apply(Snapshot(policies=[item]))


def test_ownership_refuses_foreign_table(config, tmp_path):
    class Runner:
        def json(self, args):
            return {
                "nftables": [{"table": {"family": "inet", "name": "homelimiter", "comment": "someone-else"}}]
            }

    engine = LinuxEngine(config, tmp_path, Runner())
    with pytest.raises(AdapterError, match="not owned"):
        engine._table()


def test_live_neighbor_binding_and_exclusions(config, item, tmp_path, monkeypatch):
    class Runner:
        def json(self, args):
            if "address" in args:
                return [{"addr_info": [{"local": "192.0.2.1"}]}]
            return [{"dev": "lan0"}]

    engine = LinuxEngine(config, tmp_path, Runner())
    observed = item.device.model_copy(deep=True)
    monkeypatch.setattr(engine, "discover", lambda: [observed])
    engine.validate_targets([item])
    observed.mac = "02:00:00:00:00:03"
    with pytest.raises(AdapterError, match="matching neighbor"):
        engine.validate_targets([item])
    item.device.addresses = ["192.0.2.254"]
    with pytest.raises(AdapterError, match="Protected"):
        engine.validate_targets([item])
    item.device.addresses = ["198.51.100.2"]
    with pytest.raises(AdapterError, match="outside"):
        engine.validate_targets([item])


@pytest.mark.parametrize(
    "url", ["http://192.0.2.1:8788", "https://u:pass@example.com", "https://example.com/?token=x"]
)
def test_insecure_agent_configuration_refused(url):
    with pytest.raises(ValueError):
        Settings(adapter="gateway", agent_url=url, agent_token_file="not-read")


def test_agent_transport_authenticated(config, item, tmp_path, monkeypatch):
    engine = LinuxEngine(config, tmp_path)
    monkeypatch.setattr(engine, "recover", lambda: None)
    monkeypatch.setattr(engine, "preflight", lambda: None)
    monkeypatch.setattr(engine, "discover", lambda: [item.device])
    monkeypatch.setattr(engine, "apply", lambda _: {"installed": True})
    token = "t" * 43
    app = create_agent(engine, token)
    with TestClient(app) as client:
        assert client.get("/v1/devices").status_code == 401
        headers = {"Authorization": "Bearer " + token}
        assert client.get("/v1/devices", headers=headers).status_code == 200
        assert client.put(
            "/v1/policies", json=Snapshot(policies=[item]).model_dump(mode="json"), headers=headers
        ).json()["installed"]
        assert client.get("/v1/devices", headers={**headers, "Origin": "http://evil"}).status_code == 403


def test_controller_agent_protocol(config, tmp_path, item):
    secret = tmp_path / "agent.token"
    secret.write_text("t" * 43)
    adapter = LinuxGatewayAdapter(
        Settings(adapter="gateway", agent_url="https://gateway.example", agent_token_file=str(secret))
    )
    calls = []

    def handler(request):
        assert request.headers["authorization"] == "Bearer " + "t" * 43
        calls.append(request)
        if request.url.path == "/v1/capabilities":
            return httpx.Response(
                200, json={"adapter": "gateway", "mode": "PARTIAL CONTROL", "reason": "test"}
            )
        if request.method == "PUT":
            assert json.loads(request.content)["lease_seconds"] == 90
            return httpx.Response(200, json={"installed": True})
        return httpx.Response(200, json=[item.device.model_dump(mode="json")])

    adapter.client.close()
    adapter.client = httpx.Client(
        base_url="https://gateway.example",
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer " + "t" * 43},
    )
    assert adapter.get_capabilities().mode == "PARTIAL CONTROL"
    assert adapter.discover_devices()[0].id == "target"
    adapter.reconcile([item])
    assert len(calls) == 3
    adapter.close()
