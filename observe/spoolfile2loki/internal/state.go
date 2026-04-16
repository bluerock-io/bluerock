package internal

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"syscall"

	"go.uber.org/zap"
)

type StateManager struct {
	filePath string
	state    *State
	mu       sync.RWMutex
	// lockFile holds an exclusive flock on a sibling `<state>.lock` file
	// so two spoolfile2loki instances pointed at the same state path
	// can't clobber each other's writes. released on Close().
	lockFile *os.File
}

type State struct {
	LastFetched map[string]int64 `json:"last_fetched"`
	DirState    *DirState        `json:"dir_state,omitempty"`
}

// DirState tracks progress when reading from a spool directory of rolling files.
type DirState struct {
	// CompletedFiles maps filename → size at time of completion.
	CompletedFiles map[string]int64 `json:"completed_files"`
	// CurrentFile is the file we are currently tailing.
	CurrentFile string `json:"current_file"`
	// CurrentOffset is the byte offset we have read up to in CurrentFile.
	CurrentOffset int64 `json:"current_offset"`
}

func NewStateManager(stateFile string) (*StateManager, error) {
	if stateFile == "" {
		stateFile = "spoolfile2loki.state"
	}

	absPath, err := filepath.Abs(stateFile)
	if err != nil {
		return nil, fmt.Errorf("resolving state file path: %w", err)
	}

	// acquire an exclusive filesystem lock before touching state. two
	// forwarders reading/writing the same state.json would silently
	// corrupt each other's offsets — the lock turns that into a fast,
	// explicit startup error instead.
	lockPath := absPath + ".lock"
	lockFile, err := os.OpenFile(lockPath, os.O_RDWR|os.O_CREATE, 0600)
	if err != nil {
		return nil, fmt.Errorf("opening state lock file %s: %w", lockPath, err)
	}
	if err := syscall.Flock(int(lockFile.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		lockFile.Close()
		return nil, fmt.Errorf("another spoolfile2loki is already running against %s (lock file %s held): %w", absPath, lockPath, err)
	}

	sm := &StateManager{
		filePath: absPath,
		lockFile: lockFile,
		state: &State{
			LastFetched: make(map[string]int64),
		},
	}

	if err := sm.load(); err != nil {
		Logger.Warn("Could not load state file, starting fresh",
			zap.String("path", absPath),
			zap.Error(err))
	} else {
		Logger.Info("Loaded state from file",
			zap.String("path", absPath),
			zap.Int("log_groups", len(sm.state.LastFetched)))
	}

	return sm, nil
}

// Close releases the state lock so another instance can take over.
// always call from the forwarder shutdown path.
func (sm *StateManager) Close() error {
	if sm.lockFile == nil {
		return nil
	}
	// closing the fd releases the flock on linux; do an explicit
	// unlock first so the error path is clearer if the kernel is
	// unhappy.
	_ = syscall.Flock(int(sm.lockFile.Fd()), syscall.LOCK_UN)
	err := sm.lockFile.Close()
	sm.lockFile = nil
	return err
}

func (sm *StateManager) load() error {
	sm.mu.Lock()
	defer sm.mu.Unlock()

	data, err := os.ReadFile(sm.filePath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return fmt.Errorf("reading state file: %w", err)
	}

	if len(data) == 0 {
		return nil
	}

	var state State
	if err := json.Unmarshal(data, &state); err != nil {
		return fmt.Errorf("parsing state file: %w", err)
	}

	sm.state = &state
	if sm.state.LastFetched == nil {
		sm.state.LastFetched = make(map[string]int64)
	}

	return nil
}

func (sm *StateManager) Save() error {
	sm.mu.RLock()
	defer sm.mu.RUnlock()

	data, err := json.MarshalIndent(sm.state, "", "  ")
	if err != nil {
		return fmt.Errorf("marshaling state: %w", err)
	}

	tmpFile := sm.filePath + ".tmp"
	if err := os.WriteFile(tmpFile, data, 0600); err != nil {
		return fmt.Errorf("writing temp state file: %w", err)
	}

	if err := os.Rename(tmpFile, sm.filePath); err != nil {
		os.Remove(tmpFile)
		return fmt.Errorf("renaming state file: %w", err)
	}

	Logger.Debug("Saved state to file", zap.String("path", sm.filePath))
	return nil
}

func (sm *StateManager) GetLastFetched(logGroup string) int64 {
	sm.mu.RLock()
	defer sm.mu.RUnlock()
	return sm.state.LastFetched[logGroup]
}

func (sm *StateManager) SetLastFetched(logGroup string, timestamp int64) {
	sm.mu.Lock()
	sm.state.LastFetched[logGroup] = timestamp
	sm.mu.Unlock()

	if err := sm.Save(); err != nil {
		// fail-soft: the next save will retry. a crash between now and
		// then means we re-process some events on restart, which is
		// acceptable because loki dedupes on (timestamp, stream).
		Logger.Error("Failed to save state", zap.Error(err))
	}
}

func (sm *StateManager) GetDirState() DirState {
	sm.mu.RLock()
	defer sm.mu.RUnlock()
	if sm.state.DirState == nil {
		return DirState{CompletedFiles: make(map[string]int64)}
	}
	// Return a copy.
	cp := DirState{
		CompletedFiles: make(map[string]int64, len(sm.state.DirState.CompletedFiles)),
		CurrentFile:    sm.state.DirState.CurrentFile,
		CurrentOffset:  sm.state.DirState.CurrentOffset,
	}
	for k, v := range sm.state.DirState.CompletedFiles {
		cp.CompletedFiles[k] = v
	}
	return cp
}

func (sm *StateManager) SetDirState(ds DirState) {
	sm.mu.Lock()
	sm.state.DirState = &ds
	sm.mu.Unlock()

	if err := sm.Save(); err != nil {
		// fail-soft: see SetLastFetched. worst case is a few duplicated
		// events on restart, which loki handles idempotently.
		Logger.Error("Failed to save state", zap.Error(err))
	}
}
