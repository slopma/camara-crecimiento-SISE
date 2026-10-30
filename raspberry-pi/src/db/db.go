package db

import (
	"encoding/json"
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

	maps.Copy(store.data, incoming)
}

func (store *Store) Snapshot() map[string]any {
	store.mutex.RLock()
	defer store.mutex.RUnlock()

	out := make(map[string]any, len(store.data))
	maps.Copy(out, store.data)
	return out
}

func (store *Store) Save() error {
	store.mutex.RLock()
	defer store.mutex.RUnlock()

	text, err := json.MarshalIndent(store.data, "", "\t")
	if err != nil {
		return err
	}

	return os.WriteFile(store.file, text, 0644)
}

func PeriodicSave(subStore *Store, interval time.Duration) {
	t := time.NewTicker(interval)
	for range t.C {
		if err := subStore.Save(); err != nil {
			log.Error().Err(err).Msg("Failed to save state")
		}
	}
}
