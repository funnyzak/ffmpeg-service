#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time    : 2025/7/31 10:00
# @Github  : https://github.com/funnyzak
# @File    : app.py
# @Description:FFmpeg Video Processing Service
"""
FFmpeg Video Processing Service
A Flask-based microservice for video processing using FFmpeg
"""

import os
import json
import uuid
import subprocess
import time
import threading
import logging
import logging.handlers
from datetime import datetime
from urllib.parse import urlparse
import requests
from flask import Flask, request, jsonify, send_file
import magic
from functools import wraps

# Configure logging
def setup_logging():
    """Setup comprehensive logging configuration"""
    # Create logs directory if it doesn't exist
    log_dir = os.getenv("LOG_DIR", "./logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # Get log level from environment
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] '
        '[%(funcName)s] [%(threadName)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler for all logs
    all_log_file = os.path.join(log_dir, "all.log")
    file_handler = logging.handlers.RotatingFileHandler(
        all_log_file, maxBytes=10*1024*1024, backupCount=5
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(file_handler)
    
    # Suppress Flask and Werkzeug logs in production
    if os.getenv("FLASK_DEBUG", "false").lower() not in ("true", "1", "yes", "on"):
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        logging.getLogger("gunicorn").setLevel(logging.WARNING)

    return root_logger

# Initialize logging
logger = setup_logging()

app = Flask(__name__)

# Configuration from environment variables
TEMP_DIR = os.getenv("TEMP_DIR", "/tmp/videos")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "524288000"))  # Default: 500MB
FILE_RETENTION_HOURS = int(os.getenv("FILE_RETENTION_HOURS", "2"))
CLEANUP_INTERVAL_MINUTES = int(os.getenv("CLEANUP_INTERVAL_MINUTES", "30"))

# Parse allowed extensions from environment
allowed_ext_str = os.getenv(
    "ALLOWED_VIDEO_EXTENSIONS", "mp4,avi,mov,mkv,flv,wmv,webm,m4v"
)
ALLOWED_VIDEO_EXTENSIONS = {
    f".{ext.strip()}" for ext in allowed_ext_str.split(",")
}

# Parse allowed audio extensions from environment
allowed_audio_ext_str = os.getenv(
    "ALLOWED_AUDIO_EXTENSIONS", "mp3,wav,flac,aac,ogg,m4a,wma,opus"
)
ALLOWED_AUDIO_EXTENSIONS = {
    f".{ext.strip()}" for ext in allowed_audio_ext_str.split(",")
}

# Parse supported video output formats from environment
video_output_fmt_str = os.getenv(
    "SUPPORTED_VIDEO_OUTPUT_FORMATS", "mp4,avi,mov,mkv,webm"
)
SUPPORTED_VIDEO_OUTPUT_FORMATS = {
    fmt.strip() for fmt in video_output_fmt_str.split(",")
}

# Parse supported audio output formats from environment
audio_output_fmt_str = os.getenv(
    "SUPPORTED_AUDIO_OUTPUT_FORMATS", "mp3,wav,flac,aac,ogg,m4a,opus"
)
SUPPORTED_AUDIO_OUTPUT_FORMATS = {
    fmt.strip() for fmt in audio_output_fmt_str.split(",")
}

# API Key authentication configuration
API_KEYS_STR = os.getenv("API_KEYS", "")
API_KEYS = (
    {key.strip() for key in API_KEYS_STR.split(",") if key.strip()}
    if API_KEYS_STR
    else set()
)

# Base URL configuration for full path URLs
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")  # Remove trailing slash

def log_startup_info():
    """Log startup information"""
    logger.info("=" * 60)
    logger.info("FFmpeg Service Starting")
    logger.info("=" * 60)
    logger.info(f"Python version: {os.sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info(f"Log level: {os.getenv('LOG_LEVEL', 'INFO')}")
    logger.info(f"Log directory: {os.getenv('LOG_DIR', './logs')}")
    logger.info(f"Flask debug mode: {os.getenv('FLASK_DEBUG', 'false')}")
    logger.info(f"Gunicorn workers: {os.getenv('GUNICORN_WORKERS', '4')}")
    logger.info(f"Gunicorn worker class: {os.getenv('GUNICORN_WORKER_CLASS', 'sync')}")
    logger.info(f"Gunicorn timeout: {os.getenv('GUNICORN_TIMEOUT', '120')}s")
    logger.info(f"Gunicorn max requests: {os.getenv('GUNICORN_MAX_REQUESTS', '1000')}")
    logger.info(f"Gunicorn max requests jitter: {os.getenv('GUNICORN_MAX_REQUESTS_JITTER', '100')}")
    logger.info(f"Gunicorn bind: {os.getenv('GUNICORN_BIND', '0.0.0.0:8080')}")
    logger.info(f"Gunicorn workers: {os.getenv('GUNICORN_WORKERS', '4')}")
    # Log configuration
    logger.info("Configuration loaded:")
    logger.info(f"  TEMP_DIR: {TEMP_DIR}")
    logger.info(f"  MAX_FILE_SIZE: {MAX_FILE_SIZE} bytes ({MAX_FILE_SIZE/1024/1024:.1f} MB)")
    logger.info(f"  FILE_RETENTION_HOURS: {FILE_RETENTION_HOURS}")
    logger.info(f"  CLEANUP_INTERVAL_MINUTES: {CLEANUP_INTERVAL_MINUTES}")
    logger.info(f"  ALLOWED_VIDEO_EXTENSIONS: {ALLOWED_VIDEO_EXTENSIONS}")
    logger.info(f"  ALLOWED_AUDIO_EXTENSIONS: {ALLOWED_AUDIO_EXTENSIONS}")
    logger.info(f"  SUPPORTED_VIDEO_OUTPUT_FORMATS: {SUPPORTED_VIDEO_OUTPUT_FORMATS}")
    logger.info(f"  SUPPORTED_AUDIO_OUTPUT_FORMATS: {SUPPORTED_AUDIO_OUTPUT_FORMATS}")
    logger.info(f"  API_KEYS configured: {len(API_KEYS) > 0}")
    logger.info(f"  BASE_URL: {BASE_URL or 'Not set'}")

log_startup_info()

def log_request_info(request_id=None):
    """Log request information with optional request ID"""
    if request_id is None:
        request_id = str(uuid.uuid4())[:8]
    
    log_data = {
        "request_id": request_id,
        "method": request.method,
        "path": request.path,
        "remote_addr": request.remote_addr,
        "user_agent": request.headers.get("User-Agent", "Unknown"),
        "content_length": request.content_length,
        "content_type": request.content_type,
    }
    
    logger.info(f"Request {request_id}: {log_data}")
    return request_id


def log_response_info(request_id, status_code, response_time=None):
    """Log response information"""
    log_data = {
        "request_id": request_id,
        "status_code": status_code,
        "response_time_ms": response_time,
    }
    
    if response_time:
        logger.info(f"Response {request_id}: {log_data}")
    else:
        logger.info(f"Response {request_id}: {log_data}")


def log_error(request_id, error, context=None):
    """Log error with context"""
    error_data = {
        "request_id": request_id,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "context": context or {},
    }
    
    logger.error(f"Error {request_id}: {error_data}", exc_info=True)


def require_api_key(f):
    """Decorator to require API key authentication"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip authentication if no API keys are configured
        if not API_KEYS:
            logger.debug("API key authentication disabled")
            return f(*args, **kwargs)

        # Get API key from request header
        api_key = request.headers.get("X-API-Key")

        if not api_key:
            logger.warning("API key required but not provided")
            return create_response(code=401, msg="API key required"), 401

        if api_key not in API_KEYS:
            logger.warning("Invalid API key provided")
            return create_response(code=403, msg="Invalid API key"), 403

        logger.debug("API key authentication successful")
        return f(*args, **kwargs)

    return decorated_function


class AudioProcessor:
    """Audio processing utility class"""

    def __init__(self, audio_path):
        self.audio_path = audio_path
        self.audio_info = None
        logger.debug(f"AudioProcessor initialized for: {audio_path}")

    def get_audio_info(self):
        """Extract audio metadata using ffprobe"""
        try:
            logger.info(f"Extracting audio info from: {self.audio_path}")
            
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                self.audio_path,
            ]
            
            logger.debug(f"Running ffprobe command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            )
            data = json.loads(result.stdout)

            # Find audio stream
            audio_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "audio":
                    audio_stream = stream
                    break

            if not audio_stream:
                logger.error(f"No audio stream found in: {self.audio_path}")
                raise ValueError("No audio stream found")

            format_info = data.get("format", {})

            self.audio_info = {
                "duration": float(format_info.get("duration", 0)),
                "size": int(format_info.get("size", 0)),
                "format_name": format_info.get("format_name", ""),
                "codec_name": audio_stream.get("codec_name", ""),
                "sample_rate": int(audio_stream.get("sample_rate", 0)),
                "channels": int(audio_stream.get("channels", 0)),
                "bit_rate": int(format_info.get("bit_rate", 0)),
                "channel_layout": audio_stream.get("channel_layout", ""),
            }

            logger.info(f"Audio info extracted successfully: {self.audio_info}")
            return self.audio_info

        except subprocess.CalledProcessError as e:
            logger.error(f"FFprobe failed for {self.audio_path}: {e.stderr}")
            raise Exception(f"FFprobe failed: {e.stderr}")
        except json.JSONDecodeError:
            logger.error(f"Failed to parse audio metadata for: {self.audio_path}")
            raise Exception("Failed to parse audio metadata")
        except Exception as e:
            logger.error(f"Error getting audio info for {self.audio_path}: {str(e)}")
            raise Exception(f"Error getting audio info: {str(e)}")

    def convert_format(self, output_format, quality="medium"):
        """Convert audio to specified format"""
        try:
            logger.info(f"Converting audio to {output_format} format with {quality} quality")
            
            if output_format not in SUPPORTED_AUDIO_OUTPUT_FORMATS:
                logger.error(f"Unsupported audio output format: {output_format}")
                raise ValueError(
                    f"Unsupported output format. Supported: "
                    f"{SUPPORTED_AUDIO_OUTPUT_FORMATS}"
                )

            output_filename = (
                f"converted_audio_{uuid.uuid4().hex}.{output_format}"
            )
            output_path = os.path.join(TEMP_DIR, output_filename)

            # Quality settings for different formats
            quality_settings = {
                "mp3": {
                    "low": ["-b:a", "128k"],
                    "medium": ["-b:a", "192k"],
                    "high": ["-b:a", "320k"],
                },
                "aac": {
                    "low": ["-b:a", "128k"],
                    "medium": ["-b:a", "192k"],
                    "high": ["-b:a", "256k"],
                },
                "ogg": {
                    "low": ["-q:a", "3"],
                    "medium": ["-q:a", "6"],
                    "high": ["-q:a", "9"],
                },
                "opus": {
                    "low": ["-b:a", "96k"],
                    "medium": ["-b:a", "128k"],
                    "high": ["-b:a", "192k"],
                },
            }

            # Base command
            cmd = ["ffmpeg", "-i", self.audio_path]

            # Add quality settings if available for the format
            if output_format in quality_settings:
                settings = quality_settings[output_format]
                cmd.extend(settings.get(quality, settings["medium"]))
            else:
                # Default settings for other formats
                cmd.extend(["-b:a", "192k"])

            # Add output path
            cmd.extend(["-y", output_path])

            logger.debug(f"Running ffmpeg command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Audio conversion failed: {result.stderr}")
                raise Exception(f"Conversion failed: {result.stderr}")

            # Get output file info
            file_size = os.path.getsize(output_path)
            logger.info(f"Audio conversion completed: {output_filename} ({file_size} bytes)")

            return {
                "filename": output_filename,
                "file_path": output_path,
                "file_size": file_size,
                "format": output_format,
                "url": create_download_url(output_filename),
            }

        except Exception as e:
            logger.error(f"Audio format conversion failed for {self.audio_path}: {str(e)}")
            raise Exception(f"Audio format conversion failed: {str(e)}")


class VideoProcessor:
    """Video processing utility class"""

    def __init__(self, video_path):
        self.video_path = video_path
        self.video_info = None
        logger.debug(f"VideoProcessor initialized for: {video_path}")

    def get_video_info(self):
        """Extract video metadata using ffprobe"""
        try:
            logger.info(f"Extracting video info from: {self.video_path}")
            
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                self.video_path,
            ]
            
            logger.debug(f"Running ffprobe command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            )
            data = json.loads(result.stdout)

            # Find video stream
            video_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break

            if not video_stream:
                logger.error(f"No video stream found in: {self.video_path}")
                raise ValueError("No video stream found")

            format_info = data.get("format", {})

            # Calculate frame rate safely
            frame_rate_str = video_stream.get("r_frame_rate", "0/1")
            if "/" in str(frame_rate_str):
                try:
                    # Safely parse fraction format like "30/1" or "30000/1001"
                    numerator, denominator = frame_rate_str.split("/")
                    numerator = float(numerator)
                    denominator = float(denominator)
                    if denominator != 0:
                        frame_rate = numerator / denominator
                    else:
                        frame_rate = 0
                except (ValueError, ZeroDivisionError):
                    frame_rate = 0
            else:
                try:
                    frame_rate = float(frame_rate_str)
                except (ValueError, TypeError):
                    frame_rate = 0

            self.video_info = {
                "duration": float(format_info.get("duration", 0)),
                "size": int(format_info.get("size", 0)),
                "format_name": format_info.get("format_name", ""),
                "codec_name": video_stream.get("codec_name", ""),
                "width": int(video_stream.get("width", 0)),
                "height": int(video_stream.get("height", 0)),
                "frame_rate": frame_rate,
                "bit_rate": int(format_info.get("bit_rate", 0)),
            }

            logger.info(f"Video info extracted successfully: {self.video_info}")
            return self.video_info

        except subprocess.CalledProcessError as e:
            logger.error(f"FFprobe failed for {self.video_path}: {e.stderr}")
            raise Exception(f"FFprobe failed: {e.stderr}")
        except json.JSONDecodeError:
            logger.error(f"Failed to parse video metadata for: {self.video_path}")
            raise Exception("Failed to parse video metadata")
        except Exception as e:
            logger.error(f"Error getting video info for {self.video_path}: {str(e)}")
            raise Exception(f"Error getting video info: {str(e)}")

    def take_screenshots(self, timestamps=None, count=None):
        """Take screenshots from video"""
        try:
            logger.info(f"Taking screenshots from video: {self.video_path}")
            
            if not self.video_info:
                self.get_video_info()

            duration = self.video_info["duration"]
            screenshots = []

            if timestamps:
                logger.info(f"Taking screenshots at specified timestamps: {timestamps}")
                # Use provided timestamps
                for timestamp in timestamps:
                    if timestamp > duration:
                        logger.warning(f"Timestamp {timestamp}s exceeds video duration {duration}s")
                        continue
                    screenshots.append(self._capture_screenshot(timestamp))
            elif count:
                logger.info(f"Taking {count} screenshots at evenly spaced intervals")
                # Take screenshots at evenly spaced intervals
                if count <= 0:
                    raise ValueError("Screenshot count must be positive")

                interval = duration / (count + 1)
                for i in range(1, count + 1):
                    timestamp = i * interval
                    screenshots.append(self._capture_screenshot(timestamp))
            else:
                logger.info("Taking 3 default screenshots at 25%, 50%, 75% of video")
                # Default: take 3 screenshots
                for i in [0.25, 0.5, 0.75]:
                    timestamp = duration * i
                    screenshots.append(self._capture_screenshot(timestamp))

            logger.info(f"Screenshot capture completed: {len(screenshots)} screenshots taken")
            return screenshots

        except Exception as e:
            logger.error(f"Screenshot capture failed for {self.video_path}: {str(e)}")
            raise Exception(f"Screenshot capture failed: {str(e)}")

    def _capture_screenshot(self, timestamp):
        """Capture a single screenshot at specified timestamp"""
        output_filename = f"screenshot_{uuid.uuid4().hex}_{int(timestamp)}.jpg"
        output_path = os.path.join(TEMP_DIR, output_filename)

        logger.debug(f"Capturing screenshot at {timestamp}s: {output_filename}")

        cmd = [
            "ffmpeg",
            "-i",
            self.video_path,
            "-ss",
            str(timestamp),
            "-vframes",
            "1",
            "-q:v",
            "2",
            "-y",
            output_path,
        ]

        logger.debug(f"Running ffmpeg screenshot command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Screenshot failed at {timestamp}s: {result.stderr}")
            raise Exception(f"Screenshot failed: {result.stderr}")

        # Get file size
        file_size = os.path.getsize(output_path)
        logger.debug(f"Screenshot captured successfully: {output_filename} ({file_size} bytes)")

        return {
            "timestamp": timestamp,
            "filename": output_filename,
            "file_path": output_path,
            "file_size": file_size,
            "url": create_download_url(output_filename),
        }

    def convert_format(self, output_format, quality="medium", resolution=None):
        """Convert video to specified format with optional resolution"""
        try:
            logger.info(f"Converting video to {output_format} format with {quality} quality")
            if resolution:
                logger.info(f"Resolution scaling: {resolution}")
            
            if output_format not in SUPPORTED_VIDEO_OUTPUT_FORMATS:
                logger.error(f"Unsupported video output format: {output_format}")
                raise ValueError(
                    f"Unsupported output format. Supported: "
                    f"{SUPPORTED_VIDEO_OUTPUT_FORMATS}"
                )

            output_filename = f"converted_{uuid.uuid4().hex}.{output_format}"
            output_path = os.path.join(TEMP_DIR, output_filename)

            # Quality settings
            quality_settings = {
                "low": ["-crf", "28"],
                "medium": ["-crf", "23"],
                "high": ["-crf", "18"],
            }

            cmd = [
                "ffmpeg",
                "-i",
                self.video_path,
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                *quality_settings.get(quality, quality_settings["medium"]),
            ]

            # Add resolution scaling if specified
            if resolution:
                resolution_str = self._parse_resolution(resolution)
                cmd.extend(["-vf", f"scale={resolution_str}"])

            cmd.extend(["-y", output_path])

            logger.debug(f"Running ffmpeg conversion command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Video conversion failed: {result.stderr}")
                raise Exception(f"Conversion failed: {result.stderr}")

            # Get output file info
            file_size = os.path.getsize(output_path)
            logger.info(f"Video conversion completed: {output_filename} ({file_size} bytes)")

            return {
                "filename": output_filename,
                "file_path": output_path,
                "file_size": file_size,
                "format": output_format,
                "resolution": resolution if resolution else "original",
                "url": create_download_url(output_filename),
            }

        except Exception as e:
            logger.error(f"Video format conversion failed for {self.video_path}: {str(e)}")
            raise Exception(f"Format conversion failed: {str(e)}")

    def _parse_resolution(self, resolution):
        """Parse and validate resolution parameter"""
        if not resolution:
            return None

        # Handle common resolution presets
        resolution_presets = {
            "240p": "426:240",
            "360p": "640:360",
            "480p": "854:480",
            "720p": "1280:720",
            "1080p": "1920:1080",
            "1440p": "2560:1440",
            "2160p": "3840:2160",  # 4K
            "4k": "3840:2160",
        }

        resolution_lower = str(resolution).lower()
        if resolution_lower in resolution_presets:
            return resolution_presets[resolution_lower]

        # Handle custom resolution formats
        resolution_str = str(resolution)
        # Format: WIDTHxHEIGHT (e.g., "1920x1080")
        if 'x' in resolution_str:
            parts = resolution_str.split('x')
            if len(parts) == 2:
                try:
                    width = int(parts[0])
                    height = int(parts[1])
                    if (width > 0 and height > 0 and
                            width <= 7680 and height <= 4320):
                        return f"{width}:{height}"
                except ValueError:
                    pass

        # Format: WIDTH:HEIGHT (e.g., "1920:1080")
        if ':' in resolution_str:
            parts = resolution_str.split(':')
            if len(parts) == 2:
                try:
                    width = int(parts[0])
                    height = int(parts[1])
                    if (width > 0 and height > 0 and
                            width <= 7680 and height <= 4320):
                        return f"{width}:{height}"
                except ValueError:
                    pass

        # Handle single dimension with aspect ratio preservation
        try:
            dimension = int(resolution_str)
            if dimension > 0 and dimension <= 4320:
                # Assume it's height, preserve aspect ratio
                return f"-1:{dimension}"
        except ValueError:
            pass

        raise ValueError(
            f"Invalid resolution format: {resolution}. "
            f"Supported formats: '720p', '1080p', '1920x1080', "
            f"'1280:720', or single dimension"
        )


def download_media_from_url(url):
    """Download media file (video or audio) from URL"""
    try:
        logger.info(f"Downloading media from URL: {url}")
        
        # Validate URL
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            logger.error(f"Invalid URL format: {url}")
            raise ValueError("Invalid URL")

        # Create temporary file
        temp_filename = f"input_{uuid.uuid4().hex}"
        temp_path = os.path.join(TEMP_DIR, temp_filename)
        logger.debug(f"Created temp file: {temp_path}")

        # Download file
        logger.debug(f"Starting download from: {url}")
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        # Check content type
        content_type = response.headers.get("content-type", "").lower()
        media_types = ["video", "audio", "application/octet-stream"]
        if not any(media_type in content_type for media_type in media_types):
            logger.warning(f"Content type '{content_type}' may not be a media file")
            # Don't raise error, let it continue as some servers don't set correct content-type

        # Check file size
        content_length = response.headers.get("content-length")
        if content_length:
            file_size = int(content_length)
            logger.info(f"Expected file size: {file_size} bytes ({file_size/1024/1024:.1f} MB)")
            if file_size > MAX_FILE_SIZE:
                logger.error(f"File too large: {file_size} bytes > {MAX_FILE_SIZE} bytes")
                raise ValueError("File too large")

        # Save file
        logger.debug("Starting file download...")
        with open(temp_path, "wb") as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if downloaded > MAX_FILE_SIZE:
                        os.remove(temp_path)
                        logger.error(f"Downloaded file too large: {downloaded} bytes")
                        raise ValueError("File too large")

        logger.info(f"Download completed: {temp_path} ({downloaded} bytes)")
        return temp_path

    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for URL {url}: {str(e)}")
        raise Exception(f"Failed to download media: {str(e)}")
    except Exception as e:
        if "temp_path" in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
            logger.debug(f"Cleaned up temp file: {temp_path}")
        logger.error(f"Download error for URL {url}: {str(e)}")
        raise Exception(f"Download error: {str(e)}")


def detect_media_type(file_path):
    """Detect if file is video or audio"""
    try:
        # Get file extension
        file_ext = os.path.splitext(file_path)[1].lower()

        if file_ext in ALLOWED_VIDEO_EXTENSIONS:
            return "video"
        elif file_ext in ALLOWED_AUDIO_EXTENSIONS:
            return "audio"

        # Use magic to detect MIME type
        mime_type = magic.from_file(file_path, mime=True)
        if mime_type.startswith("video/"):
            return "video"
        elif mime_type.startswith("audio/"):
            return "audio"

        return "unknown"
    except Exception:
        return "unknown"


def create_media_processor(file_path):
    """Create appropriate processor based on media type"""
    media_type = detect_media_type(file_path)

    if media_type == "video":
        return VideoProcessor(file_path), "video"
    elif media_type == "audio":
        return AudioProcessor(file_path), "audio"
    else:
        raise ValueError("Unsupported media type")


def save_uploaded_file(file):
    """Save uploaded file"""
    try:
        logger.info(f"Saving uploaded file: {file.filename}")
        
        # Check file size
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Seek back to beginning

        logger.info(f"Uploaded file size: {file_size} bytes ({file_size/1024/1024:.1f} MB)")

        if file_size > MAX_FILE_SIZE:
            logger.error(f"Uploaded file too large: {file_size} bytes > {MAX_FILE_SIZE} bytes")
            raise ValueError("File too large")

        # Check file extension
        filename = file.filename or ""
        file_ext = os.path.splitext(filename)[1].lower()
        logger.debug(f"File extension: {file_ext}")

        # Check if it's a supported video or audio file
        if (file_ext not in ALLOWED_VIDEO_EXTENSIONS and
                file_ext not in ALLOWED_AUDIO_EXTENSIONS):
            logger.warning(f"Unsupported file extension: {file_ext}")
            # Try to detect file type using magic
            file_content = file.read(1024)
            file.seek(0)
            mime_type = magic.from_buffer(file_content, mime=True)
            logger.debug(f"Detected MIME type: {mime_type}")
            if not (mime_type.startswith("video/") or
                    mime_type.startswith("audio/")):
                logger.error(f"Invalid file type: {mime_type}")
                raise ValueError("Not a valid video or audio file")

        # Save file
        temp_filename = f"upload_{uuid.uuid4().hex}{file_ext}"
        temp_path = os.path.join(TEMP_DIR, temp_filename)

        file.save(temp_path)
        logger.info(f"File saved successfully: {temp_path}")
        return temp_path

    except Exception as e:
        logger.error(f"File upload error for {file.filename}: {str(e)}")
        raise Exception(f"File upload error: {str(e)}")


def cleanup_temp_files(*file_paths):
    """Clean up temporary files"""
    for file_path in file_paths:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.debug(f"Cleaned up temp file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp file {file_path}: {e}")
                pass  # Ignore cleanup errors


def _parse_bool(value):
    """Parse boolean value from string or boolean"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    return bool(value) if value is not None else False


def _parse_int(value):
    """Parse integer value from string or int"""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_list(value):
    """Parse list value from string or list"""
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            # Try to parse as JSON array
            import json

            return json.loads(value)
        except json.JSONDecodeError:
            # Fall back to comma-separated values
            return [float(x.strip()) for x in value.split(",") if x.strip()]
    return None


def create_download_url(filename):
    """Create download URL - return full URL if BASE_URL is set, 
    otherwise relative URL"""
    relative_url = f"/download/{filename}"
    if BASE_URL:
        return f"{BASE_URL}{relative_url}"
    return relative_url


def create_response(code=0, msg="", data=None):
    """Create standardized response"""
    return jsonify({"code": code, "msg": msg, "data": data or {}})


def cleanup_old_files():
    """Clean up files older than FILE_RETENTION_HOURS"""
    try:
        if not os.path.exists(TEMP_DIR):
            logger.debug("Temp directory does not exist, skipping cleanup")
            return

        current_time = time.time()
        retention_seconds = FILE_RETENTION_HOURS * 3600
        cleaned_count = 0
        error_count = 0

        logger.debug(f"Starting cleanup (retention: {FILE_RETENTION_HOURS} hours)")

        for filename in os.listdir(TEMP_DIR):
            file_path = os.path.join(TEMP_DIR, filename)

            # Skip input files (they should be cleaned immediately)
            if filename.startswith("input_") or filename.startswith("upload_"):
                continue

            # Check if file is older than retention period
            if os.path.isfile(file_path):
                file_age = current_time - os.path.getmtime(file_path)
                if file_age > retention_seconds:
                    try:
                        os.remove(file_path)
                        cleaned_count += 1
                        logger.info(f"Cleaned up old file: {filename} (age: {file_age/3600:.1f}h)")
                    except Exception as e:
                        error_count += 1
                        logger.error(f"Failed to clean up {filename}: {e}")

        if cleaned_count > 0 or error_count > 0:
            logger.info(f"Cleanup completed: {cleaned_count} files cleaned, {error_count} errors")

    except Exception as e:
        logger.error(f"Cleanup error: {e}")


def start_cleanup_thread():
    """Start background cleanup thread"""

    def cleanup_worker():
        logger.info("Cleanup worker thread started")
        while True:
            time.sleep(CLEANUP_INTERVAL_MINUTES * 60)
            cleanup_old_files()

    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
    cleanup_thread.start()
    logger.info(
        f"Started cleanup thread (interval: {CLEANUP_INTERVAL_MINUTES} "
        f"minutes, retention: {FILE_RETENTION_HOURS} hours)"
    )


# API Routes


@app.route("/", methods=["GET"])
def homepage():
    """Homepage with project information"""
    html_content = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FFmpeg Service</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                         'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 0;
            background-color: #f8fafc;
            color: #1a202c;
            font-size: 16px;
        }

        .container {
            max-width: 900px;
            margin: 0 auto;
            padding: 2rem 1rem;
        }

        .card {
            background: white;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            padding: 2rem;
            margin-bottom: 1.5rem;
            border: 1px solid #e2e8f0;
        }

        h1 {
            color: #2d3748;
            text-align: center;
            margin: 0 0 0.5rem 0;
            font-size: 2.25rem;
            font-weight: 600;
            letter-spacing: -0.025em;
        }

        .subtitle {
            text-align: center;
            color: #718096;
            font-size: 1.125rem;
            margin-bottom: 2rem;
            font-weight: 400;
        }

        .description {
            background-color: #f7fafc;
            padding: 1.5rem;
            border-radius: 6px;
            margin: 1.5rem 0;
            border-left: 3px solid #4299e1;
            font-size: 1rem;
            line-height: 1.7;
        }

        .description p {
            margin: 0;
        }

        .features {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.25rem;
            margin: 2rem 0;
        }

        .feature {
            background-color: #ffffff;
            padding: 1.5rem;
            border-radius: 6px;
            border: 1px solid #e2e8f0;
            transition: box-shadow 0.2s ease;
        }

        .feature:hover {
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        }

        .feature h3 {
            color: #2d3748;
            margin: 0 0 0.75rem 0;
            font-size: 1.125rem;
            font-weight: 600;
        }

        .feature p {
            margin: 0;
            color: #4a5568;
            font-size: 0.9rem;
            line-height: 1.6;
        }

        .api-info {
            background-color: #ebf8ff;
            padding: 1.5rem;
            border-radius: 6px;
            margin: 1.5rem 0;
            border-left: 3px solid #3182ce;
        }

        .api-info h3 {
            color: #2b6cb0;
            margin: 0 0 1rem 0;
            font-size: 1.125rem;
            font-weight: 600;
        }

        .api-info ul {
            margin: 0;
            padding-left: 1.25rem;
            color: #2d3748;
        }

        .api-info li {
            margin-bottom: 0.5rem;
            line-height: 1.5;
        }

        .api-info strong {
            color: #2b6cb0;
            font-weight: 600;
        }

        .footer {
            text-align: center;
            padding: 1.5rem 0 0 0;
            border-top: 1px solid #e2e8f0;
            color: #718096;
        }

        .footer p {
            margin: 0;
            font-size: 0.9rem;
        }

        .footer a {
            color: #3182ce;
            text-decoration: none;
            font-weight: 500;
        }

        .footer a:hover {
            color: #2c5282;
            text-decoration: underline;
        }

        .footer strong {
            color: #4a5568;
        }

        .footer .separator {
            margin: 0 0.5rem;
            color: #cbd5e0;
        }

        /* 响应式优化 */
        @media (max-width: 768px) {
            .container {
                padding: 1rem 0.75rem;
            }

            .card {
                padding: 1.5rem;
            }

            h1 {
                font-size: 1.875rem;
            }

            .features {
                grid-template-columns: 1fr;
                gap: 1rem;
            }

            .footer {
                font-size: 0.8rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>FFmpeg Service</h1>
            <p class="subtitle">A Simple Media Processing Microservice</p>

            <div class="description">
                <p>FFmpeg Service is a Flask-based microservice that provides
                   powerful
                   media processing capabilities. The service supports both
                   video and
                   audio file processing, including format conversion, metadata
                   extraction, screenshot generation (for videos), and offers
                   developers an easy-to-use media processing API.</p>
            </div>

            <div class="features">
                <div class="feature">
                    <h3>🎬 Video Processing</h3>
                    <p>Supports conversion and processing of multiple video
                       formats,
                       including popular formats such as MP4, AVI, MOV, MKV,
                       and
                       more.</p>
                </div>
                <div class="feature">
                    <h3>🎵 Audio Processing</h3>
                    <p>Supports audio file processing including format
                       conversion
                       for MP3, WAV, FLAC, AAC, OGG, M4A, and more audio
                       formats.</p>
                </div>
                <div class="feature">
                    <h3>📸 Screenshot Feature</h3>
                    <p>Automatically extracts video screenshots, supports
                       specifying
                       timestamps or evenly distributed screenshots,
                       making video
                       preview convenient.</p>
                </div>
                <div class="feature">
                    <h3>📊 Information Analysis</h3>
                    <p>Extracts detailed metadata for both video and audio
                       files,
                       including resolution, frame rate, duration, codec,
                       sample
                       rate, and more.</p>
                </div>
                <div class="feature">
                    <h3>🔒 Secure Authentication</h3>
                    <p>Supports API Key authentication to ensure service
                       security
                       and reliability, suitable for production
                       environments.</p>
                </div>
            </div>

            <div class="api-info">
                <h3>API Endpoints</h3>
                <ul>
                    <li><strong>POST /process</strong> - Main media processing
                        endpoint (supports both video and audio)</li>
                    <li><strong>POST /info</strong> - Get media information
                        (supports both video and audio)</li>
                    <li><strong>GET /download/&lt;filename&gt;</strong> -
                        Download
                        processed files</li>
                    <li><strong>GET /health</strong> - Health check</li>
                </ul>
            </div>
        </div>

        <div class="footer" style="text-align:center; margin-top:24px;">
            <p>
                &copy; 2025
                <a href="https://github.com/funnyzak/ffmpeg-service"
                   target="_blank">FFmpeg Service</a>
                &mdash; by <a href="https://github.com/funnyzak"
                   target="_blank">@funnyzak</a>
                <span class="separator">|</span>
                Built with Flask + FFmpeg
            </p>
        </div>
    </div>
</body>
</html>
    """
    return html_content


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return create_response(msg="Service is healthy")


@app.route("/process", methods=["POST"])
@require_api_key
def process_media():
    """Main media processing endpoint (supports both video and audio)"""
    start_time = time.time()
    request_id = log_request_info()
    
    input_files = []  # Files to clean up immediately (input files)
    output_files = []  # Files to keep for download (output files)

    try:
        logger.info(f"Processing request {request_id}: media processing started")
        
        # Parse request - handle both JSON and form data
        if request.is_json:
            data = request.get_json()
            logger.debug(f"Request {request_id}: JSON data received")
        else:
            data = request.form.to_dict()
            logger.debug(f"Request {request_id}: Form data received")

        # Get processing options with type conversion for form data
        extract_info = _parse_bool(data.get("extract_info", True))
        take_screenshots = _parse_bool(data.get("take_screenshots", False))
        screenshot_timestamps = _parse_list(data.get("screenshot_timestamps"))
        screenshot_count = _parse_int(data.get("screenshot_count"))
        convert_format = data.get("convert_format")
        convert_quality = data.get("convert_quality", "medium")
        convert_resolution = data.get("convert_resolution")

        logger.info(f"Request {request_id}: Processing options - "
                   f"extract_info={extract_info}, take_screenshots={take_screenshots}, "
                   f"convert_format={convert_format}, quality={convert_quality}")

        # Get media file
        media_path = None

        if "media_url" in data:
            url = data.get("media_url")
            logger.info(f"Request {request_id}: Processing media from URL")
            media_path = download_media_from_url(url)
            input_files.append(media_path)
        elif "file" in request.files:
            # Upload file
            logger.info(f"Request {request_id}: Processing uploaded file")
            media_path = save_uploaded_file(request.files["file"])
            input_files.append(media_path)
        else:
            logger.warning(f"Request {request_id}: No media_url or file provided")
            return create_response(
                code=400, msg="No media_url or file provided"
            ), 400

        # Create appropriate processor based on media type
        processor, media_type = create_media_processor(media_path)
        result = {"media_type": media_type}
        logger.info(f"Request {request_id}: Media type detected: {media_type}")

        # Extract media info
        if extract_info:
            logger.info(f"Request {request_id}: Extracting media info")
            if media_type == "video":
                result["info"] = processor.get_video_info()
            elif media_type == "audio":
                result["info"] = processor.get_audio_info()

        # Take screenshots (only for video)
        if take_screenshots and media_type == "video":
            logger.info(f"Request {request_id}: Taking screenshots")
            screenshots = processor.take_screenshots(
                timestamps=screenshot_timestamps, count=screenshot_count
            )
            result["screenshots"] = screenshots
            # Keep screenshot files for download
            output_files.extend([shot["file_path"] for shot in screenshots])
        elif take_screenshots and media_type == "audio":
            logger.warning(f"Request {request_id}: Screenshots requested for audio file")
            result["warning"] = "Screenshots not supported for audio files"

        # Convert format
        if convert_format:
            logger.info(f"Request {request_id}: Converting format to {convert_format}")
            # Validate format compatibility
            if (media_type == "video" and
                    convert_format in SUPPORTED_VIDEO_OUTPUT_FORMATS):
                conversion_result = processor.convert_format(
                    convert_format, convert_quality, convert_resolution
                )
            elif (media_type == "audio" and
                  convert_format in SUPPORTED_AUDIO_OUTPUT_FORMATS):
                conversion_result = processor.convert_format(
                    convert_format, convert_quality
                )
            else:
                supported_formats = (
                    SUPPORTED_VIDEO_OUTPUT_FORMATS if media_type == "video"
                    else SUPPORTED_AUDIO_OUTPUT_FORMATS
                )
                logger.error(f"Request {request_id}: Unsupported format '{convert_format}' for {media_type}")
                raise ValueError(
                    f"Unsupported format '{convert_format}' for {media_type}. "
                    f"Supported formats: {supported_formats}"
                )

            result["conversion"] = conversion_result
            # Keep converted file for download
            output_files.append(conversion_result["file_path"])

        # Clean up input files only (keep output files for download)
        cleanup_temp_files(*input_files)

        response_time = (time.time() - start_time) * 1000
        logger.info(f"Request {request_id}: Processing completed successfully in {response_time:.1f}ms")
        log_response_info(request_id, 200, response_time)

        return create_response(
            msg="Media processing completed successfully", data=result
        )

    except ValueError as e:
        # Clean up all files on error
        cleanup_temp_files(*(input_files + output_files))
        response_time = (time.time() - start_time) * 1000
        logger.warning(f"Request {request_id}: Validation error - {str(e)}")
        log_response_info(request_id, 400, response_time)
        log_error(request_id, e, {"endpoint": "/process"})
        return create_response(code=400, msg=str(e)), 400
    except Exception as e:
        # Clean up all files on error
        cleanup_temp_files(*(input_files + output_files))
        response_time = (time.time() - start_time) * 1000
        logger.error(f"Request {request_id}: Processing failed - {str(e)}")
        log_response_info(request_id, 500, response_time)
        log_error(request_id, e, {"endpoint": "/process"})
        return create_response(
            code=500, msg=f"Processing failed: {str(e)}"
        ), 500


@app.route("/info", methods=["POST"])
@require_api_key
def get_media_info():
    """Get media information (supports both video and audio)"""
    start_time = time.time()
    request_id = log_request_info()
    temp_files = []

    try:
        logger.info(f"Request {request_id}: Media info extraction started")
        
        # Parse request - handle both JSON and form data
        if request.is_json:
            data = request.get_json()
            logger.debug(f"Request {request_id}: JSON data received")
        else:
            data = request.form.to_dict()
            logger.debug(f"Request {request_id}: Form data received")

        # Get media file
        if "media_url" in data:
            url = data.get("media_url")
            logger.info(f"Request {request_id}: Getting media info from URL")
            media_path = download_media_from_url(url)
            temp_files.append(media_path)
        elif "file" in request.files:
            logger.info(f"Request {request_id}: Getting media info from uploaded file")
            media_path = save_uploaded_file(request.files["file"])
            temp_files.append(media_path)
        else:
            logger.warning(f"Request {request_id}: No media_url or file provided")
            return create_response(
                code=400, msg="No media_url or file provided"
            ), 400

        # Create appropriate processor based on media type
        processor, media_type = create_media_processor(media_path)
        logger.info(f"Request {request_id}: Media type detected: {media_type}")

        # Extract media info
        logger.info(f"Request {request_id}: Extracting media info")
        if media_type == "video":
            info = processor.get_video_info()
        elif media_type == "audio":
            info = processor.get_audio_info()

        message = "Media information extracted successfully"

        # Structure response data consistently
        response_data = {
            "media_type": media_type,
            "info": info
        }

        cleanup_temp_files(*temp_files)
        
        response_time = (time.time() - start_time) * 1000
        logger.info(f"Request {request_id}: Info extraction completed in {response_time:.1f}ms")
        log_response_info(request_id, 200, response_time)
        
        return create_response(msg=message, data=response_data)

    except ValueError as e:
        cleanup_temp_files(*temp_files)
        response_time = (time.time() - start_time) * 1000
        logger.warning(f"Request {request_id}: Validation error - {str(e)}")
        log_response_info(request_id, 400, response_time)
        log_error(request_id, e, {"endpoint": "/info"})
        return create_response(code=400, msg=str(e)), 400
    except Exception as e:
        cleanup_temp_files(*temp_files)
        response_time = (time.time() - start_time) * 1000
        logger.error(f"Request {request_id}: Info extraction failed - {str(e)}")
        log_response_info(request_id, 500, response_time)
        log_error(request_id, e, {"endpoint": "/info"})
        return (
            create_response(
                code=500, msg=f"Failed to extract media info: {str(e)}"
            ),
            500,
        )


@app.route("/download/<filename>", methods=["GET"])
def download_file(filename):
    """Download processed files"""
    start_time = time.time()
    request_id = log_request_info()
    
    try:
        logger.info(f"Request {request_id}: Download request for file: {filename}")
        
        file_path = os.path.join(TEMP_DIR, filename)
        if not os.path.exists(file_path):
            logger.warning(f"Request {request_id}: File not found: {filename}")
            return create_response(code=404, msg="File not found"), 404

        # Check if auto-delete is requested
        auto_delete = (
            request.args.get("auto_delete", "false").lower() == "true"
        )
        
        if auto_delete:
            logger.info(f"Request {request_id}: Auto-delete enabled for {filename}")

        # Get file size for logging
        file_size = os.path.getsize(file_path)
        logger.info(f"Request {request_id}: Serving file {filename} ({file_size} bytes)")

        response = send_file(
            file_path, as_attachment=True, download_name=filename
        )

        if auto_delete:
            # Schedule file deletion after response is sent
            @response.call_on_close
            def cleanup_after_download():
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"Auto-deleted file after download: {filename}")
                except Exception as e:
                    logger.error(f"Failed to auto-delete {filename}: {e}")

        response_time = (time.time() - start_time) * 1000
        logger.info(f"Request {request_id}: Download completed in {response_time:.1f}ms")
        log_response_info(request_id, 200, response_time)
        
        return response

    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        logger.error(f"Request {request_id}: Download failed for {filename} - {str(e)}")
        log_response_info(request_id, 500, response_time)
        log_error(request_id, e, {"endpoint": "/download", "filename": filename})
        return create_response(code=500, msg=f"Download failed: {str(e)}"), 500


@app.errorhandler(413)
def file_too_large(e):
    return create_response(code=413, msg="File too large"), 413


@app.errorhandler(404)
def not_found(e):
    return create_response(code=404, msg="Endpoint not found"), 404


@app.errorhandler(500)
def internal_error(e):
    return create_response(code=500, msg="Internal server error"), 500


# Ensure temp directory exists
os.makedirs(TEMP_DIR, exist_ok=True)
logger.info(f"Temp directory ensured: {TEMP_DIR}")

# Start background cleanup thread
start_cleanup_thread()

# Initial cleanup on startup
cleanup_old_files()

logger.info("=" * 60)
logger.info("FFmpeg Service Started Successfully")
logger.info("=" * 60)

# Create app instance for Gunicorn
if __name__ == "__main__":
    # Configuration from environment variables
    FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
    FLASK_PORT = int(os.getenv("FLASK_PORT", "8080"))
    FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() in (
        "true",
        "1",
        "yes",
        "on",
    )

    logger.info(f"Starting Flask development server on {FLASK_HOST}:{FLASK_PORT}")
    logger.info(f"Debug mode: {FLASK_DEBUG}")
    
    # Run Flask app (for development only)
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
