"""Real RPC regressions for project authority, receipts and historical reads."""
from pathlib import Path
import pytest
from project_kernel.bootstrap import build_server, build_human_server, InvocationContextRegistry
from project_kernel.data.store.store import Store
from project_kernel.interfaces.rpc.framing import encode_frame, decode_frame
from project_kernel.interfaces.rpc.invocation import current_machine_context


@pytest.fixture
def entry():
    store = Store.open_project(Path(":memory:"), "proj-a", "store-a")
    registry = InvocationContextRegistry()
    server = build_server(store, principal="deployment-owner", contexts=registry,
                          capabilities=frozenset({"design.write", "project.read"}))
    yield store, registry, server
    store.close()


def call(server, handle, name, payload, *, project="proj-a", key="key-1", query=False, **extra):
    params = {"protocol_version": "1.0.0", "invocation_context_id": handle,
              "selector": {"project_id": project}, "payload": payload}
    if query:
        params["query"] = name
    else:
        params.update(command=name, idempotency_key=key, expected_heads=[])
    params.update(extra)
    return decode_frame(server.handle_line(encode_frame({
        "jsonrpc": "2.0", "id": "r1", "method": "kernel.query" if query else "kernel.command",
        "params": params})))


def task(server, handle, **kwargs):
    return call(server, handle, "task.create", {"title": "test", "goal": "test",
                "requirement_refs": [], "mode": "test"}, **kwargs)


def error_code(response):
    return response.get("error", {}).get("data", {}).get("code")


@pytest.mark.parametrize("caps", [[], ["project.read"]])
def test_ungranted_write_is_refused(entry, caps):
    store, registry, server = entry
    handle = registry.mint("reader", caps, project_id="proj-a")
    assert error_code(task(server, handle)) == "PERMISSION_DENIED"
    assert store.next_commit_seq() == 1


@pytest.mark.parametrize("bound,selected", [("proj-b", "proj-a"), ("proj-a", "proj-b"), (None, "proj-a")])
def test_bound_project_and_selector_must_match_store(entry, bound, selected):
    store, registry, server = entry
    handle = registry.mint("writer", ["design.write", "project.read"], project_id=bound)
    assert error_code(task(server, handle, project=selected)) == "SCOPE_MISMATCH"
    assert error_code(call(server, handle, "project.overview", {}, query=True,
                           project=selected)) == "SCOPE_MISMATCH"
    assert store.next_commit_seq() == 1


def test_query_requires_explicit_read_permission(entry):
    _, registry, server = entry
    handle = registry.mint("writer", ["design.write"], project_id="proj-a")
    assert error_code(call(server, handle, "project.overview", {}, query=True)) == "PERMISSION_DENIED"
    assert current_machine_context() is None


def test_receipt_uses_resolved_principal_and_rejects_wrong_domain(entry):
    _, registry, server = entry
    owner = registry.mint("owner", ["design.write", "project.read"], project_id="proj-a")
    stranger = registry.mint("stranger", ["project.read"], project_id="proj-a")
    written = task(server, owner)["result"]["receipt"]
    payload = {"idempotency_key": "key-1", "receipt_domain": "project"}
    own = call(server, owner, "command.receipt", payload, query=True)
    assert own["result"]["data"]["receipt"] == written
    assert call(server, stranger, "command.receipt", payload, query=True)["result"]["data"] is None
    payload["receipt_domain"] = "identity"
    assert error_code(call(server, owner, "command.receipt", payload, query=True)) == "CAPABILITY_UNAVAILABLE"


def test_rpc_preserves_zero_and_refuses_future_watermarks(entry):
    _, registry, server = entry
    handle = registry.mint("writer", ["design.write", "project.read"], project_id="proj-a")
    task(server, handle)
    historical = call(server, handle, "project.overview", {}, query=True, as_of_seq="0")["result"]
    assert historical["as_of_seq"] == "0"
    assert historical["data"]["object_counts"].get("task", 0) == 0
    assert error_code(call(server, handle, "project.overview", {}, query=True,
                           as_of_seq="999999")) == "AS_OF_UNAVAILABLE"
    events = call(server, handle, "events.read", {"after": {"commit_seq": "0", "event_index": 0},
                  "limit": 10}, query=True, as_of_seq="0")["result"]
    assert events["as_of_seq"] == "0" and events["data"] == []


def test_rpc_rejects_bad_timeline_token(entry):
    _, registry, server = entry
    handle = registry.mint("reader", ["project.read"], project_id="proj-a")
    assert error_code(call(server, handle, "project.timeline", {}, query=True,
                           page_token="invalid-token")) == "INVALID_INPUT"


def test_entries_require_trusted_registry(entry):
    store, _, _ = entry
    for factory in (build_server, build_human_server):
        with pytest.raises(ValueError, match="InvocationContextRegistry"):
            factory(store, principal="user")


def test_optional_corpus_is_not_advertised_by_default(entry):
    _, _, server = entry
    result = server.initialize_result()
    assert "dataset.export" not in result["supported_commands"]
    assert "dataset.preview" not in result["supported_queries"]
