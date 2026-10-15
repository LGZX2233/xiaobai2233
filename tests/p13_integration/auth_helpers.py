"""Explicit test-only trusted entry configuration; every handle is project-bound."""
from project_kernel.bootstrap import build_server, build_human_server, InvocationContextRegistry
from project_kernel.contracts import ALL_CAPABILITIES
from project_kernel.interfaces.rpc.invocation import InteractionProof


def build_test_server(store, *, human=False, principal="user-1", **kwargs):
    registry = kwargs.pop("contexts", None)
    if registry is None:
        registry = InvocationContextRegistry(handle_factory=lambda: "ctx1")
        if human:
            registry.mint_human(principal, ALL_CAPABILITIES, project_id=store.project_id,
                                proof=InteractionProof("isolated-test-interaction", True))
        else:
            registry.mint(principal, ALL_CAPABILITIES, project_id=store.project_id)
    kwargs.setdefault("enable_corpus", True)
    return (build_human_server if human else build_server)(
        store, principal=principal, contexts=registry, **kwargs)
