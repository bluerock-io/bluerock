package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/spf13/cobra"
	"go.uber.org/zap"

	"spoolfile2loki/internal"
)

var (
	configFile string
	logLevel   string
)

var rootCmd = &cobra.Command{
	Use:   "spoolfile2loki",
	Short: "Forward spool file events to Grafana Loki",
	Long:  `A service that reads NDJSON spool files and forwards events to Grafana Loki for centralized log aggregation and querying.`,
	Run:   runForwarder,
}

var versionCmd = &cobra.Command{
	Use:   "version",
	Short: "Print version information",
	Run: func(cmd *cobra.Command, args []string) {
		println("spoolfile2loki version " + internal.Version)
	},
}

func init() {
	rootCmd.Flags().StringVarP(&configFile, "config", "c", "config.yaml", "Path to configuration file")
	rootCmd.Flags().StringVarP(&logLevel, "log-level", "l", "info", "Log level (debug, info, warning, error)")
	rootCmd.AddCommand(versionCmd)
}

func main() {
	if err := rootCmd.Execute(); err != nil {
		log.Printf("Error: %v", err)
		os.Exit(1)
	}
}

func runForwarder(cmd *cobra.Command, args []string) {
	cfg, err := internal.LoadConfig(configFile)
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	effectiveLogLevel := logLevel
	if !cmd.Flags().Changed("log-level") && cfg.LogLevel != "" {
		effectiveLogLevel = cfg.LogLevel
	}

	if err := internal.InitLogger(effectiveLogLevel); err != nil {
		log.Fatalf("Failed to initialize logger: %v", err)
	}
	defer internal.CloseLogger()

	forwarder, err := internal.NewForwarder(cfg)
	if err != nil {
		internal.Logger.Fatal("Failed to create forwarder", zap.Error(err))
	}
	// release the state file lock on exit so the next instance can start.
	defer func() {
		if err := forwarder.Close(); err != nil {
			internal.Logger.Warn("Error closing forwarder", zap.Error(err))
		}
	}()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	go func() {
		<-sigChan
		internal.Logger.Info("Shutdown signal received, stopping...")
		cancel()
	}()

	internal.Logger.Info("Starting spoolfile2loki forwarder",
		zap.Bool("mock", cfg.Mock),
		zap.String("spool_file", cfg.SpoolFile),
		zap.String("spool_dir", cfg.SpoolDir))

	if err := forwarder.Run(ctx); err != nil {
		internal.Logger.Fatal("Forwarder error", zap.Error(err))
	}

	internal.Logger.Info("Forwarder stopped")
}
