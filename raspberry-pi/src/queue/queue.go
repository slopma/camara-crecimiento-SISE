package queue

import (
	"encoding/json"
	"os"
	"sync"
)

type Queue struct {
	mu    sync.Mutex
	file  string
	lines []string
}

func New(file string) (*Queue, error) {
	queue := &Queue{
		file: file,
	}

	if err := queue.load(); err != nil {
		return nil, err
	}

	return queue, nil
}

func (queue *Queue) load() error {
	b, err := os.ReadFile(queue.file)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}

	return json.Unmarshal(b, &queue.lines)
}

func (queue *Queue) Push(payload string) error {
	queue.mu.Lock()
	defer queue.mu.Unlock()

	queue.lines = append(queue.lines, payload)

	return queue.save()
}

func (queue *Queue) Peek() (string, bool) {
	queue.mu.Lock()
	defer queue.mu.Unlock()

	if len(queue.lines) == 0 {
		return "", false
	}

	return queue.lines[0], true
}

func (queue *Queue) Ack() error {
	queue.mu.Lock()
	defer queue.mu.Unlock()

	if len(queue.lines) == 0 {
		return nil
	}

	queue.lines = queue.lines[1:]

	return queue.save()
}

func (queue *Queue) save() error {
	b, err := json.MarshalIndent(queue.lines, "", "  ")
	if err != nil {
		return err
	}

	return os.WriteFile(queue.file, b, 0644)
}
