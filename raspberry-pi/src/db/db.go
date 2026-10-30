package db

import (
	"encoding/json"
	"fmt"
	"maps"
	"os"
	"sync"
	"time"

	"github.com/rs/zerolog/log"
)

type Store struct {
	mutex sync.RWMutex
	data  map[string]any
	file  string
	dirty bool
}

func New(file string) (*Store, error) {
	store := &Store{
		data: make(map[string]any),
		file: file,
	}

	text, err := os.ReadFile(file)
	if err == nil && len(text) > 0 {
		_ = json.Unmarshal(text, &store.data)
	}

	return store, nil
}

func (store *Store) Apply(incoming map[string]any) {
	store.mutex.Lock()
	defer store.mutex.Unlock()

	if len(incoming) == 0 {
		return
	}

	maps.Copy(store.data, incoming)
	store.dirty = true
}

func (store *Store) Snapshot() map[string]any {
	store.mutex.RLock()
	defer store.mutex.RUnlock()

	out := make(map[string]any, len(store.data))
	maps.Copy(out, store.data)
	return out
}

func (store *Store) Save() error {
	store.mutex.Lock()
	defer store.mutex.Unlock()

	// Only write to disk if data has actually changed
	if !store.dirty {
		return nil
	}

	text, err := json.MarshalIndent(store.data, "", "\t")
	if err != nil {
		return err
	}

	tmpFile := store.file + ".tmp"
	f, err := os.OpenFile(tmpFile, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0644)
	if err != nil {
		return fmt.Errorf("failed to create temp file for store: %w", err)
	}

	if _, err := f.Write(text); err != nil {
		_ = f.Close()
		_ = os.Remove(tmpFile)
		return fmt.Errorf("failed to write store data: %w", err)
	}

	if err := f.Sync(); err != nil {
		_ = f.Close()
		_ = os.Remove(tmpFile)
		return fmt.Errorf("failed to sync store temp file: %w", err)
	}

	if err := f.Close(); err != nil {
		_ = os.Remove(tmpFile)
		return fmt.Errorf("failed to close store temp file: %w", err)
	}

	if err := os.Rename(tmpFile, store.file); err != nil {
		_ = os.Remove(tmpFile)
		return fmt.Errorf("failed to atomically rename store file: %w", err)
	}

	store.dirty = false
	return nil
}

func PeriodicSave(subStore *Store, interval time.Duration) {
	t := time.NewTicker(interval)
	for range t.C {
		if err := subStore.Save(); err != nil {
			log.Error().Err(err).Msg("Failed to save state")
		}
	}
}

