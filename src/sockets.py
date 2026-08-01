from flask import request
from flask_login import current_user
from flask_socketio import emit, join_room

from extensions import db
from models import Meetings, ParticipantRole, Participants, Users


def init_sockets(socketio):

    @socketio.on("join")
    def handle_join(data):
        try:
            room = str(data.get("code"))
            name = data.get("name") or (current_user.Name if current_user.is_authenticated else "Guest")
            user_id = current_user.UserID if current_user.is_authenticated else None
            meeting = Meetings.query.filter_by(MeetingCode=data["code"]).first()
            if not meeting:
                return
            if meeting.IsEnded:
                emit("meeting_ended", {"code": room})
                return
            join_room(room)
            if user_id and data.get("code"):
                if not Participants.query.filter_by(MeetingCode=data["code"], UserID=user_id).first():
                    db.session.add(Participants(MeetingCode=data["code"], UserID=user_id, Role=ParticipantRole.Member))
                    db.session.commit()
            participants = Participants.query.filter_by(MeetingCode=data["code"]).join(Users).all()
            participant_list = {str(p.UserID): p.users.Name for p in participants}
            emit("participants", participant_list, to=room, include_self=True)
        except Exception as e:
            print(f"Error in handle_join: {e}")

    @socketio.on("speaking")
    def handle_speaking(data):
        try:
            room = str(data.get("code"))
            name = data.get("name") or (current_user.Name if current_user.is_authenticated else "Guest")
            user_id = current_user.UserID if current_user.is_authenticated else data.get("user_id")
            emit("someone_speaking", {"name": name, "user_id": user_id, "status": "is speaking"}, to=room, include_self=True)
        except Exception as e:
            print(f"Error in handle_speaking: {e}")

    @socketio.on("stopped_speaking")
    def handle_stopped_speaking(data):
        try:
            room = str(data.get("code"))
            name = data.get("name") or (current_user.Name if current_user.is_authenticated else "Guest")
            user_id = current_user.UserID if current_user.is_authenticated else data.get("user_id")
            emit("someone_stopped", {"name": name, "user_id": user_id, "status": "stopped speaking"}, to=room, include_self=True)
        except Exception as e:
            print(f"Error in handle_stopped_speaking: {e}")

    @socketio.on("mic_status")
    def handle_mic_status(data):
        try:
            room = str(data.get("code"))
            user_id = current_user.UserID if current_user.is_authenticated else data.get("user_id")
            muted = bool(data.get("muted"))
            emit("mic_status_update", {"user_id": user_id, "muted": muted}, to=room, include_self=True)
        except Exception as e:
            print(f"Error in handle_mic_status: {e}")

    @socketio.on("disconnect")
    def handle_disconnect():
        try:
            user_id = current_user.UserID if current_user.is_authenticated else None
            if user_id:
                participant = Participants.query.filter_by(UserID=user_id).first()
                if participant:
                    room = str(participant.MeetingCode)
                    name = Users.query.get(user_id).Name
                    emit("user-left", {"sid": request.sid, "name": name}, to=room)
                    participants = Participants.query.filter_by(MeetingCode=room).join(Users).all()
                    participant_list = {str(p.UserID): p.users.Name for p in participants}
                    emit("participants", participant_list, to=room)
        except Exception as e:
            print(f"Error in handle_disconnect: {e}")

    @socketio.on("meeting_started")
    def handle_meeting_started(data):
        try:
            room = str(data.get("code"))
            seconds = data.get("seconds", 0)
            meeting = Meetings.query.filter_by(MeetingCode=room).first()
            if meeting and not meeting.IsEnded:
                emit("meeting_started", {"code": room, "seconds": seconds}, to=room, include_self=False)
        except Exception as e:
            print(f"Error in handle_meeting_started: {e}")

    @socketio.on("meeting_ended")
    def handle_meeting_ended(data):
        try:
            room = str(data.get("code"))
            meeting = Meetings.query.filter_by(MeetingCode=room).first()
            if meeting and not meeting.IsEnded:
                meeting.IsEnded = True
                db.session.commit()
            emit("meeting_ended", {"code": room}, to=room, include_self=False)
        except Exception as e:
            print(f"Error in handle_meeting_ended: {e}")