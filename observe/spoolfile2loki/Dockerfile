ARG GO_VERSION=1.25
FROM --platform=$BUILDPLATFORM golang:${GO_VERSION}-alpine AS builder

WORKDIR /build

# Copy go mod files
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Build the binary for the target architecture
ARG TARGETOS
ARG TARGETARCH
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -o spoolfile2loki ./cmd/spoolfile2loki

FROM alpine:3.19

# Install runtime dependencies
RUN apk add --no-cache \
    bash \
    ca-certificates

# Create directories
RUN mkdir -p /var/spoolfile2loki /etc/spoolfile2loki

# Copy binary from builder
COPY --from=builder /build/spoolfile2loki /usr/bin/spoolfile2loki

# Copy example config
COPY config.yaml.example /etc/spoolfile2loki/config.yaml

# Set working directory
WORKDIR /var/spoolfile2loki

# Run the binary
ENTRYPOINT ["/usr/bin/spoolfile2loki"]
CMD ["--config", "/etc/spoolfile2loki/config.yaml"]
