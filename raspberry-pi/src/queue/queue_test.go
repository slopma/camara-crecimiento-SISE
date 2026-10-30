package queue

import (
	"os"
	"path/filepath"
	"testing"
)

func TestQueueOperations(t *testing.T) {
	tempDir := t.TempDir()
	queueFile := filepath.Join(tempDir, "test_queue.json")

	q, err := New(queueFile)
	if err != nil {
		t.Fatalf("failed to create queue: %v", err)
	}

	if _, ok := q.Peek(); ok {
		t.Errorf("expected empty queue, but Peek returned true")
	}

	// Push 3 items
	items := []string{`{"id":1}`, `{"id":2}`, `{"id":3}`}
	for _, item := range items {
		if err := q.Push(item); err != nil {
			t.Fatalf("failed to push item: %v", err)
		}
	}

	if q.Len() != 3 {
		t.Errorf("expected len 3, got %d", q.Len())
	}

	// Peek first
	peeked, ok := q.Peek()
	if !ok || peeked != items[0] {
		t.Errorf("expected %s, got %s", items[0], peeked)
	}

	// Ack first
	if err := q.Ack(); err != nil {
		t.Fatalf("failed to ack: %v", err)
	}

	if q.Len() != 2 {
		t.Errorf("expected len 2, got %d", q.Len())
	}

	// Close and reload to test persistence
	q2, err := New(queueFile)
	if err != nil {
		t.Fatalf("failed to reload queue: %v", err)
	}

	if q2.Len() != 2 {
		t.Errorf("expected reloaded len 2, got %d", q2.Len())
	}

	peeked2, ok := q2.Peek()
	if !ok || peeked2 != items[1] {
		t.Errorf("expected %s, got %s", items[1], peeked2)
	}
}

func TestLegacyJSONMigration(t *testing.T) {
	tempDir := t.TempDir()
	queueFile := filepath.Join(tempDir, "legacy_queue.json")

	// Write legacy JSON array format
	legacyData := []byte(`["{\"legacy\":1}", "{\"legacy\":2}"]`)
	if err := os.WriteFile(queueFile, legacyData, 0644); err != nil {
		t.Fatalf("failed to write legacy file: %v", err)
	}

	q, err := New(queueFile)
	if err != nil {
		t.Fatalf("failed to load legacy queue: %v", err)
	}

	if q.Len() != 2 {
		t.Errorf("expected 2 items from legacy format, got %d", q.Len())
	}

	item, ok := q.Peek()
	if !ok || item != `{"legacy":1}` {
		t.Errorf("unexpected first item: %s", item)
	}
}

func TestQueueCompactionOnDrain(t *testing.T) {
	tempDir := t.TempDir()
	queueFile := filepath.Join(tempDir, "drain_queue.json")

	q, err := New(queueFile)
	if err != nil {
		t.Fatalf("failed to create queue: %v", err)
	}

	for i := 0; i < 5; i++ {
		if err := q.Push(`{"val":1}`); err != nil {
			t.Fatalf("push failed: %v", err)
		}
	}

	for i := 0; i < 5; i++ {
		if err := q.Ack(); err != nil {
			t.Fatalf("ack failed: %v", err)
		}
	}

	if q.Len() != 0 {
		t.Errorf("expected empty queue, got %d", q.Len())
	}

	// Reload to verify it's still clean and empty
	qReloaded, err := New(queueFile)
	if err != nil {
		t.Fatalf("reload failed: %v", err)
	}
	if qReloaded.Len() != 0 {
		t.Errorf("expected 0 after drain and reload, got %d", qReloaded.Len())
	}
}

