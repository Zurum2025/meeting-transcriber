import os
import uuid
from datetime import datetime, timedelta

from flask import (
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from decorators import admin_required
from extensions import csrf, db
from forms import JoinMeetingForm, LoginForm, RegisterForm, StartMeetingForm, TestUploadForm
from models import Audio, Meetings, ParticipantRole, Participants, Transcripts, Minutes, Users
from services import build_minutes_pdf, finalize_meeting_summary, get_whisper_model, summarize_transcript_gpt


def init_routes(app):

    @app.route("/")
    def home():
        return render_template("home.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("start_meeting"))
        form = RegisterForm()
        if form.validate_on_submit():
            if Users.query.filter_by(Email=form.email.data).first():
                form.email.errors.append("An account with this email already exists.")
                return render_template("register.html", form=form)
            user = Users(
                Name=f"{form.firstname.data} {form.lastname.data}",
                Email=form.email.data,
                Password=generate_password_hash(form.password.data),
                is_admin=False,
            )
            db.session.add(user)
            db.session.commit()
            return redirect(url_for("login"))
        return render_template("register.html", form=form)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("start_meeting"))
        form = LoginForm()
        error = None
        if form.validate_on_submit():
            user = Users.query.filter_by(Email=form.email.data).first()
            if user and check_password_hash(user.Password, form.password.data):
                login_user(user, remember=True)
                return redirect(url_for("start_meeting"))
            error = "Invalid email or password."
        return render_template("login.html", form=form, error=error)

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.route("/admin")
    @login_required
    @admin_required
    def admin_panel():
        try:
            users = Users.query.all()
            meetings = Meetings.query.all()
            audio_recordings = Audio.query.all()
            transcripts = Transcripts.query.all()
            minutes = Minutes.query.all()
            participants_by_meeting = {}
            for meeting in meetings:
                meeting_participants = Participants.query.filter_by(MeetingCode=meeting.MeetingCode).join(Users).all()
                participants_by_meeting[meeting.MeetingCode] = [
                    {"UserID": p.UserID, "Name": p.users.Name, "Role": p.Role.value}
                    for p in meeting_participants
                ]
            return render_template(
                "admin.html",
                users=users,
                meetings=meetings,
                audio_recordings=audio_recordings,
                transcripts=transcripts,
                minutes=minutes,
                participants=participants_by_meeting,
            )
        except Exception as e:
            current_app.logger.error(f"Error in admin_panel: {e}")
            return render_template("admin.html", error=str(e))

    @app.route("/admin/delete_user/<int:user_id>", methods=["POST"])
    @login_required
    @admin_required
    def delete_user(user_id):
        user = Users.query.get_or_404(user_id)
        if user.is_admin:
            return "Cannot delete admin users.", 403
        db.session.delete(user)
        db.session.commit()
        return redirect(url_for("admin_panel"))

    @app.route("/admin/delete_meeting/<int:meeting_id>", methods=["POST"])
    @login_required
    @admin_required
    def delete_meeting(meeting_id):
        meeting = Meetings.query.get_or_404(meeting_id)
        db.session.delete(meeting)
        db.session.commit()
        return redirect(url_for("admin_panel"))

    @app.route("/admin/delete_audio/<int:audio_id>", methods=["POST"])
    @login_required
    @admin_required
    def delete_audio(audio_id):
        audio = Audio.query.get_or_404(audio_id)
        suffix = f"_{audio.UserID}" if audio.UserID else "_standalone"
        try:
            os.remove(os.path.join(current_app.config["UPLOAD_FOLDER"], f"{audio.MeetingCode}{suffix}_recording.webm"))
        except FileNotFoundError:
            pass
        db.session.delete(audio)
        db.session.commit()
        return redirect(url_for("admin_panel"))

    @app.route("/meeting", methods=["GET", "POST"])
    @login_required
    def start_meeting():
        start_form = StartMeetingForm()
        join_form = JoinMeetingForm()
        error = None

        if request.method == "POST":
            try:
                if "start" in request.form and start_form.validate_on_submit():
                    while True:
                        code = uuid.uuid4().int & (1 << 31) - 1
                        if not Meetings.query.filter_by(MeetingCode=code).first():
                            break
                    new_meeting = Meetings(
                        MeetingCode=code,
                        Title=request.form.get("title", "Untitled Meeting"),
                        Date=datetime.utcnow().date(),
                    )
                    db.session.add(new_meeting)
                    db.session.add(
                        Participants(MeetingCode=code, UserID=current_user.UserID, Role=ParticipantRole.Chairman)
                    )
                    db.session.commit()
                    return redirect(url_for("meeting_room", code=code))

                elif "join" in request.form and join_form.validate_on_submit():
                    code = int(join_form.code.data.strip())
                    meeting = Meetings.query.filter_by(MeetingCode=code).first()
                    if meeting:
                        if not Participants.query.filter_by(MeetingCode=code, UserID=current_user.UserID).first():
                            db.session.add(
                                Participants(MeetingCode=code, UserID=current_user.UserID, Role=ParticipantRole.Member)
                            )
                            db.session.commit()
                        return redirect(url_for("meeting_room", code=code))
                    else:
                        error = "Invalid meeting code."
            except (ValueError, KeyError) as e:
                error = "Invalid meeting code."
            except Exception as e:
                current_app.logger.error(f"Error in start_meeting: {e}")
                db.session.rollback()
                error = str(e)

        return render_template("meeting.html", start_form=start_form, join_form=join_form, error=error)

    @app.route("/my-meetings")
    @login_required
    def my_meetings():
        try:
            meetings = (
                Meetings.query.join(Participants)
                .filter(Participants.UserID == current_user.UserID)
                .order_by(Meetings.Date.desc())
                .all()
            )
            audios, transcripts, minutes = {}, {}, {}
            for meeting in meetings:
                audios[meeting.MeetingCode] = Audio.query.filter_by(MeetingCode=meeting.MeetingCode).first()
                transcripts[meeting.MeetingCode] = Transcripts.query.filter_by(
                    MeetingCode=meeting.MeetingCode, IsMerged=True
                ).first()
                minutes[meeting.MeetingCode] = Minutes.query.filter_by(MeetingCode=meeting.MeetingCode).first()
            return render_template("view_meetings.html", meetings=meetings, audios=audios, transcripts=transcripts, minutes=minutes)
        except Exception as e:
            current_app.logger.error(f"Error in my_meetings: {e}")
            return render_template("view_meetings.html", error=str(e))

    @app.route("/meeting/<int:code>")
    @login_required
    def meeting_room(code):
        try:
            meeting = Meetings.query.filter_by(MeetingCode=code).first_or_404()
            if meeting.IsEnded:
                return render_template("403.html", error="This meeting has ended."), 403
            participant = Participants.query.filter_by(MeetingCode=code, UserID=current_user.UserID).first()
            is_chairman = bool(participant and participant.Role == ParticipantRole.Chairman)
            return render_template("room.html", meeting=meeting, is_chairman=is_chairman)
        except Exception as e:
            current_app.logger.error(f"Error in meeting_room: {e}")
            return render_template("403.html", error=str(e)), 403

    @app.route("/meeting/<int:code>/end", methods=["POST"])
    @login_required
    def end_meeting(code):
        meeting = Meetings.query.filter_by(MeetingCode=code).first_or_404()
        duration_seconds = request.form.get("duration", 0, type=int)
        meeting.Duration = (datetime.min + timedelta(seconds=duration_seconds)).time()
        db.session.commit()
        return redirect(url_for("start_meeting"))

    @app.route("/upload_audio", methods=["POST"])
    @csrf.exempt  # fired from a JS fetch() during a live recording, not a rendered form
    def upload_audio():
        try:
            code = request.args.get("code", type=int)
            if not code:
                return jsonify({"error": "No meeting code provided"}), 400

            meeting = Meetings.query.filter_by(MeetingCode=code).first()
            if not meeting:
                return jsonify({"error": "Meeting not found"}), 404

            if "audio" not in request.files:
                return jsonify({"error": "No audio file provided"}), 400
            file = request.files["audio"]
            if file.filename == "":
                return jsonify({"error": "No file selected"}), 400

            user_id = request.form.get("user_id", type=int)
            client_start_time = request.form.get("client_start_time", type=float)

            upload_folder = current_app.config["UPLOAD_FOLDER"]
            os.makedirs(upload_folder, exist_ok=True)
            suffix = f"_{user_id}" if user_id else "_standalone"
            audio_path = os.path.join(upload_folder, f"{code}{suffix}_recording.webm")
            file.save(audio_path)

            audio_entry = Audio(MeetingCode=code, UserID=user_id, ClientStartTime=client_start_time, Timestamp=datetime.utcnow())
            db.session.add(audio_entry)
            db.session.commit()

            model = get_whisper_model()
            result = model.transcribe(audio_path, fp16=False)
            transcription = result["text"].strip()
            segments = result.get("segments", [])

            import json
            db.session.add(
                Transcripts(
                    MeetingCode=code,
                    AudioID=audio_entry.AudioID,
                    RawText=transcription,
                    SegmentsJSON=json.dumps(segments),
                    IsMerged=False,
                )
            )
            db.session.commit()

            finalize_meeting_summary(code)
            return jsonify({"message": "Audio uploaded and processed"}), 200
        except Exception as e:
            current_app.logger.error(f"Error in upload_audio: {e}")
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route("/test_upload", methods=["GET", "POST"])
    @login_required
    def test_upload():
        """Standalone Whisper + summarization smoke test, referenced from
        the README and templates but never wired up in the original app."""
        form = TestUploadForm()
        if form.validate_on_submit():
            upload_folder = current_app.config["UPLOAD_FOLDER"]
            os.makedirs(upload_folder, exist_ok=True)
            filename = secure_filename(form.audio.data.filename or "test_upload.webm")
            path = os.path.join(upload_folder, f"standalone_{uuid.uuid4().hex}_{filename}")
            form.audio.data.save(path)
            try:
                model = get_whisper_model()
                result = model.transcribe(path, fp16=False)
                transcript_text = result["text"].strip()
                summary = summarize_transcript_gpt(transcript_text)
            except Exception as e:
                current_app.logger.error(f"Error in test_upload: {e}")
                return render_template("test_upload.html", form=form, error=str(e))
            return render_template("test_result.html", transcript=transcript_text, summary=summary)
        return render_template("test_upload.html", form=form)

    @app.route("/download_audio/<int:audio_id>")
    @login_required
    def download_audio(audio_id):
        audio = Audio.query.get_or_404(audio_id)
        suffix = f"_{audio.UserID}" if audio.UserID else "_standalone"
        audio_path = os.path.join(current_app.config["UPLOAD_FOLDER"], f"{audio.MeetingCode}{suffix}_recording.webm")
        if os.path.exists(audio_path):
            return send_file(audio_path, as_attachment=True, download_name=f"meeting_{audio.MeetingCode}_audio.webm")
        abort(404)

    @app.route("/download_transcript/<int:transcript_id>")
    @login_required
    def download_transcript(transcript_id):
        from io import BytesIO

        transcript = Transcripts.query.get_or_404(transcript_id)
        text_file = BytesIO(transcript.RawText.encode("utf-8"))
        return send_file(
            text_file,
            as_attachment=True,
            download_name=f"meeting_{transcript.MeetingCode}_transcript.txt",
            mimetype="text/plain",
        )

    @app.route("/download_minutes/<int:minute_id>")
    @login_required
    def download_minutes(minute_id):
        try:
            minute = Minutes.query.get_or_404(minute_id)
            pdf_buffer = build_minutes_pdf(minute.SummaryText)
            return send_file(
                pdf_buffer,
                as_attachment=True,
                download_name=f"meeting_{minute.MeetingCode}_summary.pdf",
                mimetype="application/pdf",
            )
        except Exception as e:
            current_app.logger.error(f"Error in download_minutes: {e}")
            return jsonify({"error": str(e)}), 500

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("403.html"), 403