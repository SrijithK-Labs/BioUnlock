"""Tests for the persistent replay store."""

from __future__ import annotations

from support import memory_replay_store


def test_check_and_record_dedupes():
    store = memory_replay_store()
    try:
        assert store.check_and_record("r1", "n1", now=10) is True
        assert store.check_and_record("r1", "n1", now=11) is False
        assert store.seen("r1", "n1") is True
    finally:
        store.close()


def test_nonce_is_globally_unique():
    store = memory_replay_store()
    try:
        assert store.check_and_record("r1", "shared", now=10) is True
        assert store.check_and_record("r2", "shared", now=10) is False
    finally:
        store.close()


def test_record_does_not_clobber_existing():
    store = memory_replay_store()
    try:
        store.record("r1", "n1", now=5)
        store.record("r1", "n1", now=999)
        assert store.seen("r1", "n1") is True
    finally:
        store.close()


def test_prune_removes_old_entries():
    store = memory_replay_store()
    try:
        store.check_and_record("old", "n", now=100)
        store.check_and_record("new", "n2", now=190)
        removed = store.prune(older_than_seconds=50, now=200)
        assert removed == 1
        assert store.seen("old", "n") is False
        assert store.seen("new", "n2") is True
    finally:
        store.close()
