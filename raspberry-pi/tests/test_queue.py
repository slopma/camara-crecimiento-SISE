import os
import json
import tempfile
import pytest
from src.queue_manager import PersistentQueue

def test_queue_push_peek_ack():
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "queue.json")
        q = PersistentQueue(filepath)

        assert len(q) == 0
        val, ok = q.peek()
        assert not ok
        assert val is None

        # Push items
        q.push('{"id": 1}')
        q.push('{"id": 2}')
        q.push('{"id": 3}')

        assert len(q) == 3

        # Peek
        val, ok = q.peek()
        assert ok
        assert val == '{"id": 1}'

        # Ack
        q.ack()
        assert len(q) == 2

        val, ok = q.peek()
        assert ok
        assert val == '{"id": 2}'

def test_queue_persistence_reload():
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "queue.json")
        q1 = PersistentQueue(filepath)
        q1.push('{"a": 100}')
        q1.push('{"b": 200}')
        q1.push('{"c": 300}')
        q1.ack()  # Ack {"a": 100}

        assert len(q1) == 2

        # Reload new instance
        q2 = PersistentQueue(filepath)
        assert len(q2) == 2

        val, ok = q2.peek()
        assert ok
        assert val == '{"b": 200}'

def test_queue_legacy_json_migration():
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "legacy_queue.json")
        legacy_data = ['{"legacy": 1}', '{"legacy": 2}']
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(legacy_data, f)

        q = PersistentQueue(filepath)
        assert len(q) == 2

        val, ok = q.peek()
        assert ok
        assert val == '{"legacy": 1}'

def test_queue_compaction_on_drain():
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "drain_queue.json")
        q = PersistentQueue(filepath, compact_threshold=10)

        for i in range(5):
            q.push(f'{{"val": {i}}}')

        for _ in range(5):
            q.ack()

        assert len(q) == 0

        # Reload should be clean and empty
        q_reloaded = PersistentQueue(filepath)
        assert len(q_reloaded) == 0
