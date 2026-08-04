from flask import Flask
from commands import register_commands
from config import Config
from extensions import csrf, db, login_manager, migrate, socketio


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # --- extensions ---
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "login"
    migrate.init_app(app, db)
    csrf.init_app(app)
    socketio.init_app(app)

    # --- models must be imported before routes/sockets touch the db,
    #     and before `flask db migrate` can see the schema ---
    import models  # noqa: F401

    # --- routes & sockets are registered onto this specific app instance,
    #     which keeps endpoint names identical to the pre-refactor app
    #     (url_for('home'), url_for('login'), ...) with no blueprint prefixes ---
    import routes
    routes.init_routes(app)

    import sockets
    sockets.init_sockets(socketio)

    register_commands(app)

    return app


# Module-level `app` so `FLASK_APP=app.py` works for `flask db ...` and
# `flask create-admin` without needing debug/reloader machinery to spin up.
app = create_app()

if __name__ == "__main__":
    # Set up a fresh environment with:
    #   flask db init   (first time only)
    #   flask db migrate -m "initial"
    #   flask db upgrade
    #   flask create-admin
    socketio.run(app, debug=True)