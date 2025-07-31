#!/bin/bash

# FFmpeg Service Startup Script
# This script demonstrates how to start the service with different configurations

echo "FFmpeg Service Startup Script"
echo "=============================="

# Check if running in Docker
if [ -f /.dockerenv ]; then
    echo "Running in Docker container"
    echo "Starting FFmpeg Service with Gunicorn..."
    echo "Workers: ${GUNICORN_WORKERS:-4}"
    echo "Worker Class: ${GUNICORN_WORKER_CLASS:-sync}"
    echo "Timeout: ${GUNICORN_TIMEOUT:-120}s"
    echo "Max Requests: ${GUNICORN_MAX_REQUESTS:-1000}"
    echo "Port: ${FLASK_PORT:-8080}"
    echo ""
    
    exec gunicorn \
        --bind 0.0.0.0:${FLASK_PORT:-8080} \
        --workers ${GUNICORN_WORKERS:-4} \
        --worker-class ${GUNICORN_WORKER_CLASS:-sync} \
        --timeout ${GUNICORN_TIMEOUT:-120} \
        --max-requests ${GUNICORN_MAX_REQUESTS:-1000} \
        --max-requests-jitter ${GUNICORN_MAX_REQUESTS_JITTER:-100} \
        --access-logfile - \
        --error-logfile - \
        --log-level info \
        app:app
else
    echo "Running in local environment"
    echo "Starting Flask development server..."
    echo "Port: ${FLASK_PORT:-8080}"
    echo "Debug: ${FLASK_DEBUG:-false}"
    echo ""
    
    # For local development, use Flask's built-in server
    python app.py
fi 