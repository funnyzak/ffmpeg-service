# FFmpeg Service Deployment Guide

This guide explains how to deploy the FFmpeg Service using Gunicorn for production environments.

## Overview

The FFmpeg Service is designed to run with Gunicorn as the WSGI server in production environments. This provides:

- **Better Performance**: Multiple worker processes handle concurrent requests
- **Stability**: Automatic worker restart and memory management
- **Scalability**: Configurable worker count based on server resources
- **Reliability**: Built-in health checks and error handling
- **Media Processing**: Supports both video and audio processing with format conversion

## Quick Start

### 1. Using Docker (Recommended)

```bash
# Pull the latest image
docker pull funnyzak/ffmpeg-service:latest

# Run with default settings
docker run -d --name ffmpeg-service \
  -p 8080:8080 \
  funnyzak/ffmpeg-service

# Run with custom Gunicorn settings
docker run -d --name ffmpeg-service \
  -p 8080:8080 \
  -e GUNICORN_WORKERS=8 \
  -e GUNICORN_TIMEOUT=300 \
  -e GUNICORN_MAX_REQUESTS=2000 \
  funnyzak/ffmpeg-service
```

### 2. Using Docker Compose

```bash
# Copy environment template
cp env.example .env

# Edit configuration
nano .env

# Start the service
docker-compose up -d
```

## Gunicorn Configuration

### Environment Variables

| Variable | Description | Default | Recommended |
|----------|-------------|---------|-------------|
| `GUNICORN_WORKERS` | Number of worker processes | `4` | `(2 x CPU cores) + 1` |
| `GUNICORN_WORKER_CLASS` | Worker class type | `sync` | `sync` (for CPU-bound tasks) |
| `GUNICORN_TIMEOUT` | Worker timeout in seconds | `120` | `300` (for large files) |
| `GUNICORN_MAX_REQUESTS` | Restart workers after N requests | `1000` | `1000-2000` |
| `GUNICORN_MAX_REQUESTS_JITTER` | Add randomness to max requests | `100` | `100-200` |

### Configuration Examples

#### Small Server (2 CPU cores, 4GB RAM)
```env
GUNICORN_WORKERS=4
GUNICORN_WORKER_CLASS=sync
GUNICORN_TIMEOUT=120
GUNICORN_MAX_REQUESTS=1000
GUNICORN_MAX_REQUESTS_JITTER=100
```

#### Medium Server (4 CPU cores, 8GB RAM)
```env
GUNICORN_WORKERS=8
GUNICORN_WORKER_CLASS=sync
GUNICORN_TIMEOUT=180
GUNICORN_MAX_REQUESTS=1500
GUNICORN_MAX_REQUESTS_JITTER=150
```

#### Large Server (8 CPU cores, 16GB RAM)
```env
GUNICORN_WORKERS=16
GUNICORN_WORKER_CLASS=sync
GUNICORN_TIMEOUT=300
GUNICORN_MAX_REQUESTS=2000
GUNICORN_MAX_REQUESTS_JITTER=200
```

#### Memory-Constrained Environment
```env
GUNICORN_WORKERS=2
GUNICORN_WORKER_CLASS=sync
GUNICORN_TIMEOUT=60
GUNICORN_MAX_REQUESTS=500
GUNICORN_MAX_REQUESTS_JITTER=50
```

## Performance Tuning

### Worker Count Calculation

For CPU-intensive tasks like video processing:

```bash
# Formula: (2 x CPU cores) + 1
# Example: 4 CPU cores = 9 workers
workers = (2 * cpu_cores) + 1
```

### Memory Usage Estimation

Each worker typically uses:
- **Base memory**: 50-100MB
- **Video processing**: 200-500MB per active job
- **Peak memory**: 1-2GB for large video files

### Recommended Settings by Use Case

#### High-Throughput Processing
```env
GUNICORN_WORKERS=8
GUNICORN_TIMEOUT=300
GUNICORN_MAX_REQUESTS=2000
MAX_FILE_SIZE=2147483648  # 2GB
```

#### Memory-Constrained Environment
```env
GUNICORN_WORKERS=2
GUNICORN_TIMEOUT=60
GUNICORN_MAX_REQUESTS=500
MAX_FILE_SIZE=524288000   # 500MB
```

#### Development/Testing
```env
GUNICORN_WORKERS=1
GUNICORN_TIMEOUT=30
GUNICORN_MAX_REQUESTS=100
MAX_FILE_SIZE=104857600   # 100MB
```

## Monitoring and Health Checks

### Built-in Health Check

The service includes a health check endpoint:

```bash
# Check service health
curl http://localhost:8080/health

# Expected response
{
  "code": 0,
  "msg": "Service is healthy",
  "data": {}
}
```

### Docker Health Check

The Docker image includes automatic health checks:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

### Logging

Gunicorn logs are configured to output to stdout/stderr:

```bash
# View logs
docker logs ffmpeg-service

# Follow logs
docker logs -f ffmpeg-service
```

## Troubleshooting

### Common Issues

#### 1. Worker Timeout Errors
```
[ERROR] Worker timeout (pid: 1234)
```

**Solution**: Increase `GUNICORN_TIMEOUT` for large file processing:
```env
GUNICORN_TIMEOUT=300
```

#### 2. Memory Issues
```
[ERROR] Worker failed to boot
```

**Solution**: Reduce worker count and max requests:
```env
GUNICORN_WORKERS=2
GUNICORN_MAX_REQUESTS=500
```

#### 3. High CPU Usage
**Solution**: Adjust worker count based on CPU cores:
```env
GUNICORN_WORKERS=4  # For 2 CPU cores
```

#### 4. File Processing Failures
**Solution**: Check file size limits and timeout settings:
```env
MAX_FILE_SIZE=1073741824  # 1GB
GUNICORN_TIMEOUT=180
```

### Debugging Commands

```bash
# Test configuration
python test_gunicorn.py

# Check environment variables
docker exec ffmpeg-service env | grep GUNICORN

# Monitor resource usage
docker stats ffmpeg-service

# Check logs for errors
docker logs ffmpeg-service | grep ERROR
```

## Production Checklist

Before deploying to production:

- [ ] Set appropriate `GUNICORN_WORKERS` based on CPU cores
- [ ] Configure `GUNICORN_TIMEOUT` for expected file sizes
- [ ] Set `MAX_FILE_SIZE` based on available memory
- [ ] Configure `FILE_RETENTION_HOURS` for disk space
- [ ] Set up monitoring and alerting
- [ ] Test with expected load and file sizes
- [ ] Configure backup and recovery procedures
- [ ] Set up logging aggregation
- [ ] Configure API key authentication
- [ ] Test health check endpoints

## Security Considerations

### API Key Authentication

Enable authentication for production:

```env
API_KEYS=your_secret_key_here
```

### Resource Limits

Set appropriate limits to prevent abuse:

```env
MAX_FILE_SIZE=524288000      # 500MB
FILE_RETENTION_HOURS=2       # 2 hours
CLEANUP_INTERVAL_MINUTES=30  # 30 minutes
```

### Network Security

- Use HTTPS in production
- Configure firewall rules
- Limit access to trusted IPs
- Monitor for unusual activity

## Scaling Considerations

### Horizontal Scaling

For high-traffic environments:

1. **Load Balancer**: Use nginx or HAProxy
2. **Multiple Instances**: Run multiple containers
3. **Shared Storage**: Use network storage for temp files
4. **Database**: Consider adding a database for job tracking

### Vertical Scaling

For single-instance scaling:

1. **Increase Workers**: Based on CPU cores
2. **Increase Memory**: For larger file processing
3. **Optimize Storage**: Use SSD for temp files
4. **Network**: Ensure sufficient bandwidth

## Example Production Deployment

```yaml
# docker-compose.prod.yml
version: "3.8"
services:
  ffmpeg-service:
    image: funnyzak/ffmpeg-service:latest
    container_name: ffmpeg-service-prod
    environment:
      # Production settings
      - GUNICORN_WORKERS=8
      - GUNICORN_TIMEOUT=300
      - GUNICORN_MAX_REQUESTS=2000
      - MAX_FILE_SIZE=2147483648
      - FILE_RETENTION_HOURS=24
      - API_KEYS=your_production_key_here
    ports:
      - "8080:8080"
    volumes:
      - /data/temp:/tmp/videos
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 8G
          cpus: '4.0'
        reservations:
          memory: 4G
          cpus: '2.0'
```

This configuration provides a robust, scalable deployment suitable for production use. 