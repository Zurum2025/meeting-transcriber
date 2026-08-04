import click
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from extensions import db
from models import Users


@click.command("create-admin")
@click.option("--name", prompt="Admin name", default="Admin User")
@click.option("--email", prompt="Admin email")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
@with_appcontext
def create_admin_command(name, email, password):
    """Create an admin user. Run this once against a fresh database —
    it used to happen automatically on every app start, which is why
    it's a deliberate, explicit step now."""
    if Users.query.filter_by(Email=email).first():
        click.echo(f"A user with email {email} already exists — nothing to do.")
        return
    admin = Users(Name=name, Email=email, Password=generate_password_hash(password), is_admin=True)
    db.session.add(admin)
    db.session.commit()
    click.echo(f"Admin user created: {email}")


def register_commands(app):
    app.cli.add_command(create_admin_command)