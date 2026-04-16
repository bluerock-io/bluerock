package internal

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"time"

	"go.uber.org/zap"
)

type Forwarder struct {
	config       *Config
	lokiClient   *LokiClient
	stateManager *StateManager
}

func NewForwarder(cfg *Config) (*Forwarder, error) {
	lokiClient := NewLokiClient(
		cfg.LokiEndpoint,
		cfg.LokiRetry.MaxRetries,
		cfg.LokiRetry.RetryDelay,
	)

	stateManager, err := NewStateManager(cfg.StateFile)
	if err != nil {
		return nil, fmt.Errorf("creating state manager: %w", err)
	}

	return &Forwarder{
		config:       cfg,
		lokiClient:   lokiClient,
		stateManager: stateManager,
	}, nil
}

// Close releases owned resources (currently: the state file lock).
// safe to call multiple times — the second call is a no-op.
func (f *Forwarder) Close() error {
	if f.stateManager == nil {
		return nil
	}
	err := f.stateManager.Close()
	f.stateManager = nil
	return err
}

func (f *Forwarder) Run(ctx context.Context) error {
	ticker := time.NewTicker(f.config.PollInterval)
	defer ticker.Stop()

	if err := f.runOnce(ctx); err != nil {
		Logger.Error("Error in initial run", zap.Error(err))
	}

	for {
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
			if err := f.runOnce(ctx); err != nil {
				Logger.Error("Error in run", zap.Error(err))
			}
		}
	}
}

func (f *Forwarder) runOnce(ctx context.Context) error {
	if f.config.Mock {
		return f.processMock(ctx)
	}
	if f.config.SpoolDir != "" {
		return f.processSpoolDir(ctx)
	}
	return f.processSpoolFile(ctx)
}

// spoolLine is the NDJSON line format written by the spool producer.
// The ts field may be a unix-millisecond integer or an ISO 8601 string.
type spoolLine struct {
	TS    flexTime        `json:"ts"`
	Event json.RawMessage `json:"event"`
}

// flexTime unmarshals a timestamp that is either a JSON number (unix ms)
// or a JSON string (RFC 3339 / ISO 8601).
type flexTime struct {
	time.Time
}

func (ft *flexTime) UnmarshalJSON(b []byte) error {
	b = bytes.TrimSpace(b)
	if len(b) == 0 {
		return fmt.Errorf("empty timestamp")
	}
	// Numeric — unix milliseconds.
	if b[0] != '"' {
		ms, err := strconv.ParseInt(string(b), 10, 64)
		if err != nil {
			return fmt.Errorf("invalid numeric timestamp: %w", err)
		}
		ft.Time = time.UnixMilli(ms)
		return nil
	}
	// String — try RFC 3339 / ISO 8601.
	var s string
	if err := json.Unmarshal(b, &s); err != nil {
		return fmt.Errorf("invalid timestamp string: %w", err)
	}
	t, err := time.Parse(time.RFC3339Nano, s)
	if err != nil {
		t, err = time.Parse(time.RFC3339, s)
	}
	if err != nil {
		return fmt.Errorf("cannot parse timestamp %q: %w", s, err)
	}
	ft.Time = t
	return nil
}

// eventMeta contains fields used as Loki labels.
type eventMeta struct {
	Name     string `json:"name"`
	Origin   string `json:"origin"`
	SensorID int    `json:"sensor_id"`
	Type     string `json:"type"`
}

type eventEnvelope struct {
	Meta eventMeta `json:"meta"`
}

func (f *Forwarder) processSpoolFile(ctx context.Context) error {
	spoolPath := f.config.SpoolFile
	lastTS := f.stateManager.GetLastFetched(spoolPath)

	file, err := os.Open(spoolPath)
	if err != nil {
		return fmt.Errorf("opening spool file %s: %w", spoolPath, err)
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 10*1024*1024), 10*1024*1024)

	var entries []LogEntry
	// ackedTS is the highest timestamp we've pushed to loki successfully.
	// pendingHighestTS is the max timestamp of entries in the current
	// not-yet-pushed batch. we only advance the persisted state with
	// ackedTS — otherwise a failed push would silently drop events.
	var ackedTS int64 = lastTS
	var pendingHighestTS int64 = lastTS
	skipped := 0

	// persist whatever progress we made, then decide whether to return an
	// error up. always call on exit.
	persistAcked := func() {
		if ackedTS > lastTS {
			f.stateManager.SetLastFetched(spoolPath, ackedTS)
			Logger.Info("Spool file progress saved",
				zap.String("path", spoolPath),
				zap.Int("skipped", skipped),
				zap.Time("last_ts", time.UnixMilli(ackedTS)))
		}
	}

	for scanner.Scan() {
		// stop promptly on shutdown — spool files can be large and we don't
		// want SIGTERM to wait for the full scan before exiting.
		select {
		case <-ctx.Done():
			persistAcked()
			return ctx.Err()
		default:
		}

		raw := scanner.Bytes()
		if len(bytes.TrimSpace(raw)) == 0 {
			continue
		}

		var sl spoolLine
		if err := json.Unmarshal(raw, &sl); err != nil {
			Logger.Warn("Skipping malformed spool line", zap.Error(err))
			continue
		}

		if sl.TS.UnixMilli() <= lastTS {
			skipped++
			continue
		}

		if sl.TS.UnixMilli() > pendingHighestTS {
			pendingHighestTS = sl.TS.UnixMilli()
		}

		entries = append(entries, f.makeEntry(sl))

		if len(entries) >= f.config.BatchSize {
			if err := f.lokiClient.Push(ctx, entries); err != nil {
				Logger.Error("Failed to push batch to Loki", zap.Error(err))
				persistAcked()
				return fmt.Errorf("push batch: %w", err)
			}
			Logger.Info("Pushed spool batch", zap.Int("count", len(entries)))
			ackedTS = pendingHighestTS
			entries = entries[:0]
		}
	}

	if err := scanner.Err(); err != nil {
		persistAcked()
		return fmt.Errorf("reading spool file: %w", err)
	}

	if len(entries) > 0 {
		if err := f.lokiClient.Push(ctx, entries); err != nil {
			Logger.Error("Failed to push final batch to Loki", zap.Error(err))
			persistAcked()
			return fmt.Errorf("push final batch: %w", err)
		}
		Logger.Info("Pushed spool batch", zap.Int("count", len(entries)))
		ackedTS = pendingHighestTS
	}

	if ackedTS > lastTS {
		persistAcked()
	} else {
		Logger.Debug("No new events in spool file", zap.String("path", spoolPath))
	}

	return nil
}

func (f *Forwarder) processMock(ctx context.Context) error {
	lines := bytes.Split(mockEventData, []byte("\n"))

	// Determine base timestamp from the first valid line so we can shift
	// all events to be relative to now.
	var baseTS int64
	for _, line := range lines {
		line = bytes.TrimSpace(line)
		if len(line) == 0 {
			continue
		}
		var sl spoolLine
		if err := json.Unmarshal(line, &sl); err == nil {
			baseTS = sl.TS.UnixMilli()
			break
		}
	}

	offset := time.Now().UnixMilli() - baseTS

	var entries []LogEntry
	sent := 0
	for _, line := range lines {
		line = bytes.TrimSpace(line)
		if len(line) == 0 {
			continue
		}

		var sl spoolLine
		if err := json.Unmarshal(line, &sl); err != nil {
			Logger.Warn("Skipping malformed mock line", zap.Error(err))
			continue
		}

		sl.TS.Time = time.UnixMilli(sl.TS.UnixMilli() + offset)
		entries = append(entries, f.makeEntry(sl))
		sent++

		if len(entries) >= f.config.BatchSize {
			if err := f.lokiClient.Push(ctx, entries); err != nil {
				Logger.Error("Failed to push mock batch to Loki", zap.Error(err))
			}
			entries = entries[:0]
		}
	}

	if len(entries) > 0 {
		if err := f.lokiClient.Push(ctx, entries); err != nil {
			Logger.Error("Failed to push mock batch to Loki", zap.Error(err))
		}
	}

	Logger.Info("Mock events forwarded", zap.Int("count", sent))
	return nil
}

func (f *Forwarder) processSpoolDir(ctx context.Context) error {
	dir := f.config.SpoolDir
	dirState := f.stateManager.GetDirState()

	// List all regular files in the spool directory.
	dirEntries, err := os.ReadDir(dir)
	if err != nil {
		return fmt.Errorf("reading spool directory %s: %w", dir, err)
	}

	type fileInfo struct {
		name    string
		size    int64
		modTime time.Time
	}
	var files []fileInfo
	for _, entry := range dirEntries {
		if entry.IsDir() {
			continue
		}
		info, err := entry.Info()
		if err != nil {
			Logger.Warn("Cannot stat file, skipping", zap.String("file", entry.Name()), zap.Error(err))
			continue
		}
		if info.Size() == 0 {
			continue
		}
		files = append(files, fileInfo{
			name:    entry.Name(),
			size:    info.Size(),
			modTime: info.ModTime(),
		})
	}

	if len(files) == 0 {
		Logger.Debug("No files in spool directory", zap.String("dir", dir))
		return nil
	}

	// Sort by modification time ascending (oldest first).
	sort.Slice(files, func(i, j int) bool {
		return files[i].modTime.Before(files[j].modTime)
	})

	// Purge completed entries for files that no longer exist.
	currentNames := make(map[string]bool, len(files))
	for _, f := range files {
		currentNames[f.name] = true
	}
	for name := range dirState.CompletedFiles {
		if !currentNames[name] {
			delete(dirState.CompletedFiles, name)
		}
	}

	// Categorise files: completed (skip) vs to-process.
	var toProcess []fileInfo
	var skippedCount int
	for _, fi := range files {
		completedSize, done := dirState.CompletedFiles[fi.name]
		if done && fi.size == completedSize {
			skippedCount++
			continue
		}
		toProcess = append(toProcess, fi)
	}

	Logger.Info("Scanning spool directory",
		zap.String("dir", dir),
		zap.Int("total_files", len(files)),
		zap.Int("completed", skippedCount),
		zap.Int("to_process", len(toProcess)),
	)

	if len(toProcess) == 0 {
		Logger.Debug("No new data in spool directory")
		return nil
	}

	// Process files in order.  The last file in the sorted list is the
	// "active" file that the writer may still be appending to.
	totalEvents := 0
	filesCompleted := 0

	for i, fi := range toProcess {
		isActive := (i == len(toProcess)-1)
		fullPath := filepath.Join(dir, fi.name)

		// Determine starting byte offset.
		var offset int64
		if fi.name == dirState.CurrentFile {
			offset = dirState.CurrentOffset
		}

		if isActive {
			Logger.Info("Reading active file",
				zap.String("file", fi.name),
				zap.Int64("from_offset", offset),
				zap.Int64("size", fi.size),
			)
		} else {
			Logger.Info("Reading completed file",
				zap.String("file", fi.name),
				zap.Int64("from_offset", offset),
				zap.Int64("size", fi.size),
			)
		}

		n, newOffset, err := f.processFileFrom(ctx, fullPath, offset)

		// processFileFrom returns ackedBytes as newOffset even on error, so
		// whatever did get pushed this iteration won't be re-pushed next tick.
		// update current tracking first so the persisted state reflects any
		// partial progress.
		if newOffset > offset {
			dirState.CurrentFile = fi.name
			dirState.CurrentOffset = newOffset
		}

		totalEvents += n

		if err != nil {
			Logger.Error("Error processing file",
				zap.String("file", fi.name),
				zap.Error(err),
			)
			// loki is likely down or the file is corrupt — don't burn the
			// poll budget on subsequent files, persist progress and bail.
			break
		}

		if ctx.Err() != nil {
			// graceful shutdown requested — persist and exit the loop.
			break
		}

		if !isActive {
			// This file is not the active file, so the writer is done
			// with it.  Mark it completed.
			dirState.CompletedFiles[fi.name] = fi.size
			filesCompleted++
			Logger.Info("File fully consumed",
				zap.String("file", fi.name),
				zap.Int("events", n),
			)
		}
	}

	f.stateManager.SetDirState(dirState)

	Logger.Info("Spool directory poll complete",
		zap.Int("events_forwarded", totalEvents),
		zap.Int("files_completed", filesCompleted),
	)

	return nil
}

// processFileFrom reads NDJSON lines from path starting at byte offset.
// Returns: (events sent, new byte offset, error).
func (f *Forwarder) processFileFrom(ctx context.Context, path string, offset int64) (int, int64, error) {
	file, err := os.Open(path)
	if err != nil {
		return 0, offset, fmt.Errorf("opening %s: %w", path, err)
	}
	defer file.Close()

	if offset > 0 {
		if _, err := file.Seek(offset, io.SeekStart); err != nil {
			return 0, offset, fmt.Errorf("seeking %s to %d: %w", path, offset, err)
		}
	}

	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 10*1024*1024), 10*1024*1024)

	var entries []LogEntry
	// ackedBytes is the offset up to which loki has confirmed receipt.
	// pendingBytes is everything we've read past ackedBytes but haven't
	// ack'd yet (entries awaiting push + any empty/malformed lines mixed
	// in between). they must advance together — acking empty lines alone
	// would leave ackedBytes pointing into the middle of a pending entry.
	sentAcked := 0
	ackedBytes := offset
	pendingBytes := int64(0)
	pendingCount := 0

	for scanner.Scan() {
		// stop promptly on shutdown — large spool files shouldn't keep the
		// process alive after SIGTERM.
		select {
		case <-ctx.Done():
			return sentAcked, ackedBytes, ctx.Err()
		default:
		}

		raw := scanner.Bytes()
		lineBytes := int64(len(raw)) + 1 // +1 for newline consumed by Scanner
		pendingBytes += lineBytes

		if len(bytes.TrimSpace(raw)) == 0 {
			// empty line — consumes bytes but produces no loki event.
			continue
		}

		var sl spoolLine
		if err := json.Unmarshal(raw, &sl); err != nil {
			Logger.Warn("Skipping malformed spool line",
				zap.String("file", filepath.Base(path)),
				zap.Error(err),
			)
			continue
		}

		entries = append(entries, f.makeEntry(sl))
		pendingCount++

		if len(entries) >= f.config.BatchSize {
			if err := f.lokiClient.Push(ctx, entries); err != nil {
				Logger.Error("Failed to push batch to Loki", zap.Error(err))
				return sentAcked, ackedBytes, fmt.Errorf("push batch: %w", err)
			}
			Logger.Debug("Pushed spool batch", zap.Int("count", len(entries)))
			sentAcked += pendingCount
			ackedBytes += pendingBytes
			pendingBytes, pendingCount = 0, 0
			entries = entries[:0]
		}
	}

	if err := scanner.Err(); err != nil {
		return sentAcked, ackedBytes, fmt.Errorf("reading %s: %w", path, err)
	}

	if len(entries) > 0 {
		if err := f.lokiClient.Push(ctx, entries); err != nil {
			Logger.Error("Failed to push final batch to Loki", zap.Error(err))
			return sentAcked, ackedBytes, fmt.Errorf("push final batch: %w", err)
		}
		Logger.Debug("Pushed spool batch", zap.Int("count", len(entries)))
		sentAcked += pendingCount
		ackedBytes += pendingBytes
	} else if pendingBytes > 0 {
		// no entries in final batch — pending bytes are all empty or
		// malformed lines with no predecessor entries waiting. safe to
		// ack them so the next tick doesn't re-scan the same tail.
		ackedBytes += pendingBytes
	}

	// bufio.Scanner's default split strips the trailing newline but
	// our lineBytes calculation always adds +1 for it. a file whose
	// last line lacks a newline therefore makes ackedBytes overshoot
	// by 1. clamp to the current file size so the next tick's seek
	// lands exactly at EOF (or at the start of freshly-appended data).
	if fi, statErr := file.Stat(); statErr == nil {
		if ackedBytes > fi.Size() {
			ackedBytes = fi.Size()
		}
	}

	return sentAcked, ackedBytes, nil
}

func (f *Forwarder) makeEntry(sl spoolLine) LogEntry {
	var env eventEnvelope
	_ = json.Unmarshal(sl.Event, &env)

	labels := make(map[string]string, len(f.config.Labels)+4)
	for k, v := range f.config.Labels {
		labels[k] = v
	}
	if env.Meta.Origin != "" {
		labels["origin"] = env.Meta.Origin
	}
	if env.Meta.Type != "" {
		labels["event_type"] = env.Meta.Type
	}
	if env.Meta.Name != "" {
		labels["event_name"] = env.Meta.Name
	}
	if env.Meta.SensorID != 0 {
		labels["sensor_id"] = strconv.Itoa(env.Meta.SensorID)
	}

	return LogEntry{
		Timestamp: sl.TS.Time,
		Line:      string(sl.Event),
		Labels:    labels,
	}
}
