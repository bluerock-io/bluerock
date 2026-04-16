package internal

import (
	"fmt"
	"os"
	"time"

	"gopkg.in/yaml.v3"
)

type Config struct {
	LokiEndpoint string            `yaml:"loki_endpoint"`
	LokiRetry    LokiRetry         `yaml:"loki_retry"`
	PollInterval time.Duration     `yaml:"poll_interval"`
	BatchSize    int               `yaml:"batch_size"`
	StateFile    string            `yaml:"state_file"`
	Labels       map[string]string `yaml:"labels"`
	LogLevel     string            `yaml:"log_level"`
	SpoolFile    string            `yaml:"spool_file"`
	SpoolDir     string            `yaml:"spool_dir"`
	Mock         bool              `yaml:"mock"`
}

type LokiRetry struct {
	MaxRetries int           `yaml:"max_retries"`
	RetryDelay time.Duration `yaml:"retry_delay"`
}

func LoadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading config file: %w", err)
	}

	var cfg Config
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("parsing config: %w", err)
	}

	if cfg.LokiEndpoint == "" {
		return nil, fmt.Errorf("loki_endpoint is required")
	}

	if !cfg.Mock && cfg.SpoolFile == "" && cfg.SpoolDir == "" {
		return nil, fmt.Errorf("spool_file or spool_dir is required (or enable mock mode)")
	}

	if cfg.SpoolFile != "" && cfg.SpoolDir != "" {
		return nil, fmt.Errorf("spool_file and spool_dir are mutually exclusive")
	}

	if cfg.PollInterval == 0 {
		cfg.PollInterval = 60 * time.Second
	}

	if cfg.BatchSize == 0 {
		cfg.BatchSize = 100
	}

	if cfg.StateFile == "" {
		cfg.StateFile = "spoolfile2loki.state"
	}

	if cfg.Labels == nil {
		cfg.Labels = make(map[string]string)
	}

	if cfg.LogLevel == "" {
		cfg.LogLevel = "info"
	}

	return &cfg, nil
}
