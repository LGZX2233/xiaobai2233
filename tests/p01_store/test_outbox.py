"""Outbox claim/ack with lease tokens against a real SQLite file."""
from __future__ import annotations

import pytest

from project_kernel.contracts.errors import KernelError
from project_kernel.data.store.uow import UnitOfWork

from .helpers import make_context, make_store


def _enqueue(store, ctx, consumer="c1", effect_id="e1"):
    uow = UnitOfWork(store, ctx, "test.command")
    uow.execute(lambda h: h.outbox.enqueue(consumer, effect_id, "export"))


def test_claim_then_ack(tmp_path):
    store = make_store(tmp_path)
    try:
        _enqueue(store, make_context(key="ob-1"))
        claim = store.conn.execute("SELECT outbox_id FROM outbox WHERE effect_id='e1'").fetchone()
        from project_kernel.data.store.outbox import Outbox
        ob = Outbox(store.conn)
        claimed = ob.claim("c1", "e1", "export")
        assert claimed["lease_token"]
        assert ob.ack(claimed["outbox_id"], claimed["lease_token"]) is True
        state = store.conn.execute("SELECT state FROM outbox WHERE outbox_id=?",
                                   (claimed["outbox_id"],)).fetchone()[0]
        assert state == "acked"
    finally:
        store.close()


def test_stale_lease_token_ack_does_not_advance(tmp_path):
    store = make_store(tmp_path)
    try:
        _enqueue(store, make_context(key="ob-2"))
        from project_kernel.data.store.outbox import Outbox
        ob = Outbox(store.conn)
        claimed = ob.claim("c1", "e1", "export", lease_seconds=0)  # instantly expired
        # second worker claims with a fresh token
        claimed2 = ob.claim("c1", "e1", "export")
        assert claimed2["lease_token"] != claimed["lease_token"]
        # the first worker's stale token cannot ack or fail the new owner
        assert ob.ack(claimed["outbox_id"], claimed["lease_token"]) is False
        state = store.conn.execute("SELECT state FROM outbox WHERE outbox_id=?",
                                   (claimed["outbox_id"],)).fetchone()[0]
        assert state == "leased"
        # the real owner acks successfully
        assert ob.ack(claimed2["outbox_id"], claimed2["lease_token"]) is True
    finally:
        store.close()
