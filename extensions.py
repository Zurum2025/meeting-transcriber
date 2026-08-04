"""Shared extension instances.

These are created unbound and wired to a real Flask app inside
create_app() in app.py. Keeping them here (rather than on app.py)
is what lets models.py, routes.py, forms.py, and sockets.py import
`db`, `login_manager`, etc. without circular imports.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO
from flask_migrate import Migrate
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()

# async_mode left on default (eventlet is in requirements.txt and will be
# auto-detected). cors_allowed_origins kept permissive to match prior
# behavior; tighten this in production.
socketio = SocketIO(cors_allowed_origins="*")