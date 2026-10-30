package queue

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"sync"
)

const defaultCompactThreshold = 50

type Queue struct {
	mu               sync.Mutex
	file             string
	lines            []string
	ackedCount       int
	compactThreshold int
}

func New(file string) (*Queue, error) {
	q := &Queue{
		file:             file,
		lines:            make([]string, 0),
		compactThreshold: defaultCompactThreshold,
	}

	if err := q.load(); err != nil {
		return nil, err
	}

	return q, nil
}

func (q *Queue) load() error {
	b, err := os.ReadFile(q.file)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}

	trimmed := bytes.TrimSpace(b)
	if len(trimmed) == 0 {
		return nil
	}

	// Backwards compatibility: attempt to parse legacy JSON array format
	if trimmed[0] == '[' {
		var legacyLines []string
		if err := json.Unmarshal(trimmed, &legacyLines); err == nil {
			q.lines = legacyLines
			// Convert legacy file to append-only format immediately
			return q.compact()
		}
	}

	// Read line-by-line (WAL / JSON Lines format)
	scanner := bufio.NewScanner(bytes.NewReader(trimmed))
	// Allow large telemetry payloads up to 1MB per line if needed
	buf := make([]byte, 64*1024)
	scanner.Buffer(buf, 1024*1024)

	hasAcks := false
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}

		if strings.HasPrefix(line, "+") {
			q.lines = append(q.lines, strings.TrimPrefix(line, "+"))
		} else if line == "-" {
			hasAcks = true
			if len(q.lines) > 0 {
				q.lines = q.lines[1:]
			}
		} else {
			// Legacy plain JSON line without prefix
			q.lines = append(q.lines, line)
		}
	}

	if err := scanner.Err(); err != nil {
		return err
	}

	// If the file had accumulated acks, compact now to keep on-disk WAL tidy
	if hasAcks {
		return q.compact()
	}

	return nil
}

// Push adds a new payload to the queue with an O(1) sequential append to disk.
func (q *Queue) Push(payload string) error {
	q.mu.Lock()
	defer q.mu.Unlock()

	cleanPayload := strings.TrimSpace(payload)
	if cleanPayload == "" {
		return nil
	}

	f, err := os.OpenFile(q.file, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return fmt.Errorf("failed to open queue file for append: %w", err)
	}

	// WAL record format: "+<payload>\n"
	record := "+" + cleanPayload + "\n"
	if _, err := f.WriteString(record); err != nil {
		_ = f.Close()
		return fmt.Errorf("failed to write payload to queue: %w", err)
	}

	if err := f.Close(); err != nil {
		return fmt.Errorf("failed to close queue file: %w", err)
	}

	q.lines = append(q.lines, cleanPayload)
	return nil
}

// Peek returns the oldest unacknowledged item without removing it.
func (q *Queue) Peek() (string, bool) {
	q.mu.Lock()
	defer q.mu.Unlock()

	if len(q.lines) == 0 {
		return "", false
	}

	return q.lines[0], true
}

// Ack removes the oldest item from the queue and logs the ack sequentially.
func (q *Queue) Ack() error {
	q.mu.Lock()
	defer q.mu.Unlock()

	if len(q.lines) == 0 {
		return nil
	}

	// Append ack record "-" to WAL
	f, err := os.OpenFile(q.file, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return fmt.Errorf("failed to open queue file for ack: %w", err)
	}

	if _, err := f.WriteString("-\n"); err != nil {
		_ = f.Close()
		return fmt.Errorf("failed to write ack to queue: %w", err)
	}

	if err := f.Close(); err != nil {
		return fmt.Errorf("failed to close queue file after ack: %w", err)
	}

	q.lines = q.lines[1:]
	q.ackedCount++

	// Compact if threshold reached or if queue is completely drained
	if q.ackedCount >= q.compactThreshold || (len(q.lines) == 0 && q.ackedCount > 0) {
		return q.compact()
	}

	return nil
}

// Len returns the current number of queued items.
func (q *Queue) Len() int {
	q.mu.Lock()
	defer q.mu.Unlock()
	return len(q.lines)
}

// compact rewrites only the active in-memory queue atomically to disk.
// Must be called with q.mu held.
func (q *Queue) compact() error {
	tmpFile := q.file + ".tmp"

	f, err := os.OpenFile(tmpFile, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0644)
	if err != nil {
		return fmt.Errorf("failed to create temp file for compaction: %w", err)
	}

	writer := bufio.NewWriter(f)
	for _, line := range q.lines {
		if _, err := writer.WriteString("+" + line + "\n"); err != nil {
			_ = f.Close()
			_ = os.Remove(tmpFile)
			return fmt.Errorf("failed to write line during compaction: %w", err)
		}
	}

	if err := writer.Flush(); err != nil {
		_ = f.Close()
		_ = os.Remove(tmpFile)
		return fmt.Errorf("failed to flush compaction writer: %w", err)
	}

	if err := f.Sync(); err != nil {
		_ = f.Close()
		_ = os.Remove(tmpFile)
		return fmt.Errorf("failed to sync compacted file: %w", err)
	}

	if err := f.Close(); err != nil {
		_ = os.Remove(tmpFile)
		return fmt.Errorf("failed to close compacted file: %w", err)
	}

	if err := os.Rename(tmpFile, q.file); err != nil {
		_ = os.Remove(tmpFile)
		return fmt.Errorf("failed to rename compacted queue file: %w", err)
	}

	q.ackedCount = 0
	return nil
}


