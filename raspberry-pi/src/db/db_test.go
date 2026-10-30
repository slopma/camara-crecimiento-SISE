package db

import (
	"path/filepath"
	"testing"
)

func TestStoreOperations(t *testing.T) {
	tempDir := t.TempDir()
	storeFile := filepath.Join(tempDir, "substore.json")

	store, err := New(storeFile)
	if err != nil {
		t.Fatalf("failed to create store: %v", err)
	}

	// Initial save without changes should be a no-op
	if err := store.Save(); err != nil {
		t.Fatalf("initial save failed: %v", err)
	}

	// Apply data
	incoming := map[string]any{
		"temp_max1": 25.5,
		"hum_min1":  60.0,
	}
	store.Apply(incoming)

	snap := store.Snapshot()
	if snap["temp_max1"] != 25.5 {
		t.Errorf("expected 25.5, got %v", snap["temp_max1"])
	}

	// Save dirty store
	if err := store.Save(); err != nil {
		t.Fatalf("save failed: %v", err)
	}

	// Reload from disk
	reloaded, err := New(storeFile)
	if err != nil {
		t.Fatalf("reload failed: %v", err)
	}

	reloadedSnap := reloaded.Snapshot()
	if reloadedSnap["temp_max1"] != 25.5 || reloadedSnap["hum_min1"] != 60.0 {
		t.Errorf("unexpected reloaded snapshot: %v", reloadedSnap)
	}
}
