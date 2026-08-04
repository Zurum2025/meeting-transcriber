from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length


class RegisterForm(FlaskForm):
    firstname = StringField("First Name", validators=[DataRequired(), Length(max=100)])
    lastname = StringField("Last Name", validators=[DataRequired(), Length(max=100)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=150)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    submit = SubmitField("Register")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log in")


class StartMeetingForm(FlaskForm):
    """Deliberately just a submit button — matches the original template,
    which only ever needed to know a POST with `start` in the form body
    happened."""
    start = SubmitField("Create meeting")


class JoinMeetingForm(FlaskForm):
    code = StringField("Meeting code", validators=[DataRequired()])
    join = SubmitField("Join")


class TestUploadForm(FlaskForm):
    audio = FileField(
        "Audio file",
        validators=[
            FileRequired(message="Please choose an audio file."),
            FileAllowed(
                ["webm", "wav", "mp3", "m4a", "ogg", "mp4"],
                "Audio files only.",
            ),
        ],
    )
    submit = SubmitField("Upload")