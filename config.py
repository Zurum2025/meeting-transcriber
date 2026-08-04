import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base config. Everything here is meant to be overridden by
    environment variables in production — nothing sensitive is
    hardcoded anymore."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///db.sqlite3")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "Uploads")

    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")

    # Socket.IO
    SOCKETIO_CORS_ALLOWED_ORIGINS = os.environ.get("SOCKETIO_CORS_ALLOWED_ORIGINS", "*")


class TestConfig(Config):
    """Used by the automated test suite / stub test client. Never used
    for a real run."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    UPLOAD_FOLDER = "/tmp/waveform_test_uploads"