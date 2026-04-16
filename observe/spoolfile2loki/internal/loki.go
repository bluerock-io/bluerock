package internal

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math/rand/v2"
	"net/http"
	"strconv"
	"time"

	"go.uber.org/zap"
)

// cap the retry wait so a big retryDelay can't blow up into a
// multi-minute nap. also keeps goroutine shutdown responsive.
const maxRetryBackoff = 30 * time.Second

type LokiClient struct {
	endpoint   string
	httpClient *http.Client
	maxRetries int
	retryDelay time.Duration
}

type LogEntry struct {
	Timestamp time.Time
	Line      string
	Labels    map[string]string
}

type lokiPushRequest struct {
	Streams []lokiStream `json:"streams"`
}

type lokiStream struct {
	Stream map[string]string `json:"stream"`
	Values [][]string        `json:"values"`
}

func NewLokiClient(endpoint string, maxRetries int, retryDelay time.Duration) *LokiClient {
	if maxRetries <= 0 {
		maxRetries = 10
	}
	if retryDelay <= 0 {
		retryDelay = 2 * time.Second
	}
	return &LokiClient{
		endpoint:   endpoint,
		maxRetries: maxRetries,
		retryDelay: retryDelay,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

func (c *LokiClient) Push(ctx context.Context, entries []LogEntry) error {
	if len(entries) == 0 {
		return nil
	}

	Logger.Debug("Preparing to push logs to Loki", zap.Int("entries", len(entries)))

	streamMap := make(map[string]*lokiStream)

	for _, entry := range entries {
		key := labelsToKey(entry.Labels)

		stream, exists := streamMap[key]
		if !exists {
			stream = &lokiStream{
				Stream: entry.Labels,
				Values: [][]string{},
			}
			streamMap[key] = stream
		}

		timestamp := strconv.FormatInt(entry.Timestamp.UnixNano(), 10)
		stream.Values = append(stream.Values, []string{timestamp, entry.Line})
	}

	streams := make([]lokiStream, 0, len(streamMap))
	for _, stream := range streamMap {
		streams = append(streams, *stream)
	}

	reqBody := lokiPushRequest{
		Streams: streams,
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return fmt.Errorf("marshaling request: %w", err)
	}

	var lastErr error
	for attempt := 1; attempt <= c.maxRetries; attempt++ {
		if attempt > 1 {
			// exponential backoff with jitter. the jitter keeps multiple
			// forwarder instances from retrying in lockstep and hammering
			// loki all at once when it comes back up.
			delay := backoffWithJitter(c.retryDelay, attempt)
			Logger.Warn("Retrying push to Loki",
				zap.Int("attempt", attempt),
				zap.Int("max_retries", c.maxRetries),
				zap.Duration("wait", delay))
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(delay):
			}
		}

		req, err := http.NewRequestWithContext(ctx, "POST", c.endpoint+"/loki/api/v1/push", bytes.NewBuffer(jsonData))
		if err != nil {
			lastErr = fmt.Errorf("creating request: %w", err)
			continue
		}

		req.Header.Set("Content-Type", "application/json")

		Logger.Debug("Sending push request to Loki",
			zap.String("endpoint", c.endpoint),
			zap.Int("streams", len(streams)),
			zap.Int("attempt", attempt))

		resp, err := c.httpClient.Do(req)
		if err != nil {
			lastErr = fmt.Errorf("sending request: %w", err)
			Logger.Error("Failed to push to Loki",
				zap.Error(err),
				zap.Int("attempt", attempt))
			continue
		}

		if resp.StatusCode >= 400 {
			body, _ := io.ReadAll(resp.Body)
			resp.Body.Close()
			lastErr = fmt.Errorf("loki returned status %d: %s", resp.StatusCode, string(body))
			Logger.Error("Loki returned error status",
				zap.Int("status", resp.StatusCode),
				zap.String("body", string(body)),
				zap.Int("attempt", attempt))
			continue
		}

		resp.Body.Close()
		Logger.Info("Successfully pushed logs to Loki",
			zap.Int("entries", len(entries)),
			zap.Int("attempt", attempt))
		return nil
	}

	// exhausted retries. let the caller decide what to do — a transient
	// loki outage longer than maxRetries*retryDelay should not take the
	// whole forwarder down; the next tick will try again.
	Logger.Error("Failed to push to Loki after max retries",
		zap.Int("max_retries", c.maxRetries),
		zap.Error(lastErr))
	return fmt.Errorf("failed after %d retries: %w", c.maxRetries, lastErr)
}

func labelsToKey(labels map[string]string) string {
	b, _ := json.Marshal(labels)
	return string(b)
}

// backoffWithJitter returns the wait duration before retry attempt n
// (where n >= 2). doubles the base delay for each attempt up to
// maxRetryBackoff, then adds random jitter in the range [-25%, +25%]
// so parallel forwarders don't retry in lockstep.
func backoffWithJitter(base time.Duration, attempt int) time.Duration {
	shift := attempt - 2
	if shift < 0 {
		shift = 0
	}
	if shift > 20 { // guard against overflow on pathological configs
		shift = 20
	}
	d := base * time.Duration(1<<shift)
	if d > maxRetryBackoff {
		d = maxRetryBackoff
	}
	// +/- 25% jitter
	jitterRange := int64(d) / 2
	if jitterRange > 0 {
		d += time.Duration(rand.Int64N(jitterRange)) - time.Duration(jitterRange/2)
	}
	if d < 0 {
		d = base
	}
	return d
}
