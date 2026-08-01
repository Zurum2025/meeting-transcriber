import enum
from datetime import datetime

from flask_login import UserMixin

from extensions import db, login_manager


class ParticipantRole(enum.Enum):
    Chairman = "Chairman"
    Member = "Member"


class Users(UserMixin, db.Model):
    __tablename__ = "users"
    UserID = db.Column(db.Integer, primary_key=True)
    Name = db.Column(db.String(150), nullable=False)
    Email = db.Column(db.String(150), unique=True, nullable=False)
    Password = db.Column(db.String(150), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def get_id(self):
        return str(self.UserID)


class Meetings(db.Model):
    __tablename__ = "meetings"
    MeetingCode = db.Column(db.Integer, primary_key=True)
    Title = db.Column(db.String(255), nullable=False)
    Date = db.Column(db.Date, nullable=False)
    Duration = db.Column(db.Time, nullable=True)
    IsEnded = db.Column(db.Boolean, default=False, nullable=False)


class Audio(db.Model):
    __tablename__ = "audio"
    AudioID = db.Column(db.Integer, primary_key=True)
    MeetingCode = db.Column(db.Integer, db.ForeignKey("meetings.MeetingCode"), nullable=False)
    UserID = db.Column(db.Integer, db.ForeignKey("users.UserID"), nullable=True)
    ClientStartTime = db.Column(db.Float, nullable=True)
    Timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Transcripts(db.Model):
    __tablename__ = "transcripts"
    TranscriptID = db.Column(db.Integer, primary_key=True)
    MeetingCode = db.Column(db.Integer, db.ForeignKey("meetings.MeetingCode"), nullable=False)
    AudioID = db.Column(db.Integer, db.ForeignKey("audio.AudioID"), nullable=True)
    RawText = db.Column(db.Text, nullable=False)
    SegmentsJSON = db.Column(db.Text, nullable=True)
    IsMerged = db.Column(db.Boolean, default=False, nullable=False)


class Minutes(db.Model):
    __tablename__ = "minutes"
    MinuteID = db.Column(db.Integer, primary_key=True)
    MeetingCode = db.Column(db.Integer, db.ForeignKey("meetings.MeetingCode"), nullable=False)
    TranscriptID = db.Column(db.Integer, db.ForeignKey("transcripts.TranscriptID"), nullable=False)
    SummaryText = db.Column(db.Text, nullable=False)


class Participants(db.Model):
    __tablename__ = "participants"
    MeetingCode = db.Column(db.Integer, db.ForeignKey("meetings.MeetingCode"), primary_key=True)
    UserID = db.Column(db.Integer, db.ForeignKey("users.UserID"), primary_key=True)
    Role = db.Column(db.Enum(ParticipantRole), nullable=False, default=ParticipantRole.Member)
    users = db.relationship("Users", backref="participants", lazy=True)


@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(int(user_id))