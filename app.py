from flask import Flask, jsonify, render_template, redirect, url_for, request, session, abort, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, UserMixin, current_user, login_required
from flask_socketio import SocketIO, join_room, emit
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
import uuid
import whisper
from datetime import datetime, timedelta
from google import genai
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from dotenv import load_dotenv
import enum
from io import StringIO, BytesIO

import json



# Verify flask_login import
try:
    from flask_login import login_required
    print("flask_login.login_required imported successfully")
except ImportError as e:
    print(f"Error importing flask_login: {e}")
    raise

load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

socketio = SocketIO(app, cors_allowed_origins="*")

login_manager = LoginManager()
login_manager.init_app(app)

# ENUM for Participant Role
class ParticipantRole(enum.Enum):
    Chairman = 'Chairman'
    Member = 'Member'

# Database Models
class Users(UserMixin, db.Model):
    __tablename__ = 'users'
    UserID = db.Column(db.Integer, primary_key=True)
    Name = db.Column(db.String(150), nullable=False)
    Email = db.Column(db.String(150), unique=True, nullable=False)
    Password = db.Column(db.String(150), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)  # Added for admin functionality

    def get_id(self):
        return str(self.UserID)

class Meetings(db.Model):
    __tablename__ = 'meetings'
    MeetingCode = db.Column(db.Integer, primary_key=True)
    Title = db.Column(db.String(255), nullable=False)
    Date = db.Column(db.Date, nullable=False)
    Duration = db.Column(db.Time, nullable=True)
    IsEnded = db.Column(db.Boolean, default=False, nullable=False) 

class Audio(db.Model):
    __tablename__ = 'audio'
    AudioID = db.Column(db.Integer, primary_key=True)
    MeetingCode = db.Column(db.Integer, db.ForeignKey('meetings.MeetingCode'), nullable=False)
    Timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class Transcripts(db.Model):
    __tablename__ = 'transcripts'
    TranscriptID = db.Column(db.Integer, primary_key=True)
    MeetingCode = db.Column(db.Integer, db.ForeignKey('meetings.MeetingCode'), nullable=False)
    AudioID = db.Column(db.Integer, db.ForeignKey('audio.AudioID'), nullable=False)
    RawText = db.Column(db.Text, nullable=False)

class Minutes(db.Model):
    __tablename__ = 'minutes'
    MinuteID = db.Column(db.Integer, primary_key=True)
    MeetingCode = db.Column(db.Integer, db.ForeignKey('meetings.MeetingCode'), nullable=False)
    TranscriptID = db.Column(db.Integer, db.ForeignKey('transcripts.TranscriptID'), nullable=False)
    SummaryText = db.Column(db.Text, nullable=False)

class Participants(db.Model):
    __tablename__ = 'participants'
    MeetingCode = db.Column(db.Integer, db.ForeignKey('meetings.MeetingCode'), primary_key=True)
    UserID = db.Column(db.Integer, db.ForeignKey('users.UserID'), primary_key=True)
    Role = db.Column(db.Enum(ParticipantRole), nullable=False, default=ParticipantRole.Member)
    users = db.relationship('Users', backref='participants', lazy=True)

# Admin Required Decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(int(user_id))

# Routes
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('start_meeting'))
    if request.method == 'POST':
        user = Users(
            Name=f"{request.form['firstname']} {request.form['lastname']}",
            Email=request.form['email'],
            Password=generate_password_hash(request.form['password']),
            is_admin=False  # Default to non-admin
        )
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('start_meeting'))
    if request.method == 'POST':
        user = Users.query.filter_by(Email=request.form['email']).first()
        if user and check_password_hash(user.Password, request.form['password']):
            login_user(user, remember=True)
            return redirect(url_for('start_meeting'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    try:
        users = Users.query.all()
        meetings = Meetings.query.all()
        audio_recordings = Audio.query.all()  # Pass as list, not dict
        transcripts = Transcripts.query.all()
        minutes = Minutes.query.all()
        # Join Participants with Users for names
        participants_by_meeting = {}
        for meeting in meetings:
            meeting_participants = Participants.query.filter_by(MeetingCode=meeting.MeetingCode).join(Users).all()
            participants_by_meeting[meeting.MeetingCode] = [
                {'UserID': p.UserID, 'Name': p.users.Name, 'Role': p.Role.value}
                for p in meeting_participants
            ]
        return render_template(
            'admin.html',
            users=users,
            meetings=meetings,
            audio_recordings=audio_recordings,  # Changed from recordings
            transcripts=transcripts,
            minutes=minutes,
            participants=participants_by_meeting
        )
    except Exception as e:
        print(f"Error in admin_panel: {e}")
        return render_template('admin.html', error=str(e))
    
@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = Users.query.get_or_404(user_id)
    if user.is_admin:
        return "Cannot delete admin users.", 403
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete_meeting/<int:meeting_id>', methods=['POST'])
@login_required
@admin_required
def delete_meeting(meeting_id):
    meeting = Meetings.query.get_or_404(meeting_id)
    db.session.delete(meeting)
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete_audio/<int:audio_id>', methods=['POST'])
@login_required
@admin_required
def delete_audio(audio_id):
    audio = Audio.query.get_or_404(audio_id)
    try:
        os.remove(os.path.join('recordings', f"{audio.MeetingCode}_recording.webm"))
    except FileNotFoundError:
        pass  # File might not exist
    db.session.delete(audio)
    db.session.commit()
    return redirect(url_for('admin_panel'))

@socketio.on('join')
def handle_join(data):
    try:
        room = str(data.get('code'))
        name = data.get('name') or (current_user.Name if current_user.is_authenticated else 'Guest')
        user_id = current_user.UserID if current_user.is_authenticated else None
        sid = request.sid
        print(f"User {name} (ID: {user_id}, SID: {sid}) joining room {room}")
        meeting = Meetings.query.filter_by(MeetingCode=data['code']).first()
        if not meeting:
            print(f"Meeting {data['code']} not found")
            return
        if meeting.IsEnded:
            print(f"Meeting {data['code']} has ended, rejecting join")
            emit('meeting_ended', {'code': room})
            return
        join_room(room)
        if user_id and data.get('code'):
            if not Participants.query.filter_by(MeetingCode=data['code'], UserID=user_id).first():
                participant = Participants(
                    MeetingCode=data['code'],
                    UserID=user_id,
                    Role=ParticipantRole.Member
                )
                db.session.add(participant)
                db.session.commit()
                print(f"Added participant {name} (ID: {user_id}) to meeting {data['code']} as Member")
        participants = Participants.query.filter_by(MeetingCode=data['code']).join(Users).all()
        participant_list = {str(p.UserID): p.users.Name for p in participants}
        print(f"Emitting participants: {participant_list}")
        emit('participants', participant_list, to=room, include_self=True)
    except Exception as e:
        print(f"Error in handle_join: {e}")

@socketio.on('speaking')
def handle_speaking(data):
    try:
        room = str(data.get('code'))
        name = data.get('name') or (current_user.Name if current_user.is_authenticated else 'Guest')
        user_id = current_user.UserID if current_user.is_authenticated else data.get('user_id')
        print(f"Received speaking event: {name} in room {room}")  # Debug
        emit('someone_speaking', {'name': name, 'user_id': user_id, 'status': 'is speaking'}, to=room, include_self=True)
    except Exception as e:
        print(f"Error in handle_speaking: {e}")

@socketio.on('stopped_speaking')
def handle_stopped_speaking(data):
    try:
        room = str(data.get('code'))
        name = data.get('name') or (current_user.Name if current_user.is_authenticated else 'Guest')
        user_id = current_user.UserID if current_user.is_authenticated else data.get('user_id')
        print(f"Received stopped_speaking event: {name} in room {room}")  # Debug
        emit('someone_stopped', {'name': name, 'user_id': user_id, 'status': 'stopped speaking'}, to=room, include_self=True)
    except Exception as e:
        print(f"Error in handle_stopped_speaking: {e}")

@socketio.on('mic_status')
def handle_mic_status(data):
    try:
        room = str(data.get('code'))
        user_id = current_user.UserID if current_user.is_authenticated else data.get('user_id')
        muted = bool(data.get('muted'))
        print(f"Mic status update: user {user_id} muted={muted} in room {room}")  # Debug
        emit('mic_status_update', {'user_id': user_id, 'muted': muted}, to=room, include_self=True)
    except Exception as e:
        print(f"Error in handle_mic_status: {e}")

@socketio.on('disconnect')
def handle_disconnect():
    try:
        user_id = current_user.UserID if current_user.is_authenticated else None
        if user_id:
            print(f"User {user_id} disconnected")
            participant = Participants.query.filter_by(UserID=user_id).first()
            if participant:
                room = str(participant.MeetingCode)
                name = Users.query.get(user_id).Name
                emit('user-left', {'sid': request.sid, 'name': name}, to=room)
                participants = Participants.query.filter_by(MeetingCode=room).join(Users).all()
                participant_list = {str(p.UserID): p.users.Name for p in participants}
                emit('participants', participant_list, to=room)
    except Exception as e:
        print(f"Error in handle_disconnect: {e}")


@socketio.on('meeting_started')
def handle_meeting_started(data):
    try:
        room = str(data.get('code'))
        seconds = data.get('seconds', 0)
        meeting = Meetings.query.filter_by(MeetingCode=room).first()
        if meeting and not meeting.IsEnded:
            print(f"Broadcasting meeting_started in room {room} with {seconds} seconds")
            emit('meeting_started', {'code': room, 'seconds': seconds}, to=room, include_self=False)
        else:
            print(f"Meeting {room} is ended or not found, not broadcasting meeting_started")
    except Exception as e:
        print(f"Error in handle_meeting_started: {e}")

@socketio.on('meeting_ended')
def handle_meeting_ended(data):
    try:
        room = str(data.get('code'))
        meeting = Meetings.query.filter_by(MeetingCode=room).first()
        if meeting and not meeting.IsEnded:
            meeting.IsEnded = True
            db.session.commit()
            print(f"Marked meeting {room} as ended")
        print(f"Broadcasting meeting_ended in room {room}")
        emit('meeting_ended', {'code': room}, to=room, include_self=False)
    except Exception as e:
        print(f"Error in handle_meeting_ended: {e}")

@app.route('/meeting', methods=['GET', 'POST'])
@login_required
def start_meeting():
    if request.method == 'POST':
        try:
            if 'start' in request.form:
                while True:
                    code = uuid.uuid4().int & (1<<31)-1
                    if not Meetings.query.filter_by(MeetingCode=code).first():
                        break
                new_meeting = Meetings(
                    MeetingCode=code,
                    Title=request.form.get('title', 'Untitled Meeting'),
                    Date=datetime.utcnow().date()
                )
                db.session.add(new_meeting)
                participant = Participants(
                    MeetingCode=code,
                    UserID=current_user.UserID,
                    Role=ParticipantRole.Chairman
                )
                db.session.add(participant)
                db.session.commit()
                print(f"Added participant {current_user.Name} (ID: {current_user.UserID}) to meeting {code} as Chairman")
                return redirect(url_for('meeting_room', code=code))
            elif 'join' in request.form:
                code = int(request.form['code'].strip())
                meeting = Meetings.query.filter_by(MeetingCode=code).first()
                if meeting:
                    if not Participants.query.filter_by(MeetingCode=code, UserID=current_user.UserID).first():
                        participant = Participants(
                            MeetingCode=code,
                            UserID=current_user.UserID,
                            Role=ParticipantRole.Member
                        )
                        db.session.add(participant)
                        db.session.commit()
                        print(f"Added participant {current_user.Name} (ID: {current_user.UserID}) to meeting {code} as Member")
                    return redirect(url_for('meeting_room', code=code))
                else:
                    return render_template('meeting.html', error="Invalid meeting code.")
        except Exception as e:
            print(f"Error in start_meeting: {e}")
            db.session.rollback()
            return render_template('meeting.html', error=str(e))
    return render_template('meeting.html', error=None)


@app.route('/my-meetings')
@login_required
def my_meetings():
    try:
        # Fetch meetings user has attended
        meetings = Meetings.query.join(Participants).filter(Participants.UserID == current_user.UserID).order_by(Meetings.Date.desc()).all()
        print(f"Found {len(meetings)} meetings for user {current_user.UserID} ({current_user.Name}, is_admin={current_user.is_admin}): {[m.MeetingCode for m in meetings]}")
        audios = {}
        transcripts = {}
        minutes = {}
        for meeting in meetings:
            audio = Audio.query.filter_by(MeetingCode=meeting.MeetingCode).first()
            transcript = Transcripts.query.filter_by(MeetingCode=meeting.MeetingCode).first()
            minute = Minutes.query.filter_by(MeetingCode=meeting.MeetingCode).first()
            audios[meeting.MeetingCode] = audio
            transcripts[meeting.MeetingCode] = transcript
            minutes[meeting.MeetingCode] = minute
            print(f"Meeting {meeting.MeetingCode}: Title={meeting.Title}, Audio={audio.AudioID if audio else None}, Transcript={transcript.TranscriptID if transcript else None}, Minute={minute.MinuteID if minute else None}")
        return render_template('view_meetings.html', meetings=meetings, audios=audios, transcripts=transcripts, minutes=minutes)
    except Exception as e:
        print(f"Error in my_meetings: {e}")
        return render_template('view_meetings.html', error=str(e))

@app.route('/meeting/<int:code>')
@login_required
def meeting_room(code):
    try:
        meeting = Meetings.query.filter_by(MeetingCode=code).first_or_404()
        if meeting.IsEnded:
            return render_template('403.html', error="This meeting has ended."), 403
        participant = Participants.query.filter_by(MeetingCode=code, UserID=current_user.UserID).first()
        is_chairman = participant and participant.Role == ParticipantRole.Chairman
        print(f"User {current_user.Name} (ID: {current_user.UserID}, is_admin={current_user.is_admin}) is {'Chairman' if is_chairman else 'Member or not in Participants'} for meeting {code}")
        if not participant:
            print(f"Warning: No participant entry for UserID {current_user.UserID} in meeting {code}")
        return render_template('room.html', meeting=meeting, is_chairman=is_chairman)
    except Exception as e:
        print(f"Error in meeting_room: {e}")
        return render_template('403.html', error=str(e)), 403

@app.route('/meeting/<int:code>/end', methods=['POST'])
@login_required
def end_meeting(code):
    meeting = Meetings.query.filter_by(MeetingCode=code).first_or_404()
    # Update duration (assuming meetingSeconds is sent from frontend)
    duration_seconds = request.form.get('duration', 0, type=int)
    meeting.Duration = (datetime.min + timedelta(seconds=duration_seconds)).time()
    db.session.commit()
    return redirect(url_for('start_meeting'))

def summarize_transcript_gpt(transcript_text):
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("Missing Gemini API key. Set GEMINI_API_KEY in your .env file.")

        client = genai.Client(api_key=api_key)

        max_chars = 40000
        if len(transcript_text) > max_chars:
            transcript_text = transcript_text[:max_chars]
            print(f"Truncated transcript to {max_chars} characters for Gemini")

        prompt = (
            "You are generating structured meeting minutes from a raw, possibly "
            "messy speech-to-text transcript. Read it carefully and extract the "
            "requested fields. For action_points, capture every concrete task, "
            "commitment, or follow-up mentioned — including ones phrased casually "
            "(e.g. \"I'll handle the vendor call\" counts as an action point). "
            "If a field genuinely isn't present in the transcript, say so briefly "
            "rather than inventing details.\n\n"
            f"Transcript:\n{transcript_text}"
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": {
                    "type": "object",
                    "properties": {
                        "meeting_topic": {"type": "string"},
                        "attendees": {"type": "string"},
                        "agenda": {"type": "string"},
                        "summary": {"type": "string"},
                        "action_points": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "conclusion": {"type": "string"}
                    },
                    "required": [
                        "meeting_topic", "attendees", "agenda",
                        "summary", "action_points", "conclusion"
                    ]
                }
            }
        )

        data = json.loads(response.text)

        action_points = data.get("action_points") or []
        if action_points:
            action_points_text = '\n'.join(f"- {point}" for point in action_points)
        else:
            action_points_text = "- No specific action points identified."

        meeting_date = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        structured_summary = f"""
        Date and Time: {meeting_date}
        Meeting Topic: {data.get('meeting_topic', 'General Discussion')}
        Attendees: {data.get('attendees', 'Participants')}
        Agenda: {data.get('agenda', 'Summarized from transcript')}
        Summary of Discussions: {data.get('summary', '')}
        Action Points:
        {action_points_text}
        Conclusion: {data.get('conclusion', 'Meeting concluded.')}
        """
        print(f"Generated summary: {structured_summary[:100]}...")
        return structured_summary
    except json.JSONDecodeError as e:
        print(f"Error parsing Gemini JSON response: {e}")
        return f"Error generating summary: model returned malformed JSON"
    except Exception as e:
        print(f"Error in summarize_transcript_gpt: {e}")
        return f"Error generating summary: {str(e)}"

@app.route('/upload_audio', methods=['POST'])
def upload_audio():
    try:
        code = request.args.get('code', type=int)
        if not code:
            print("No meeting code provided")
            return jsonify({'error': 'No meeting code provided'}), 400
        
        meeting = Meetings.query.filter_by(MeetingCode=code).first()
        if not meeting:
            print(f"Meeting {code} not found")
            return jsonify({'error': 'Meeting not found'}), 404
        if meeting.IsEnded:
            print(f"Meeting {code} already ended")
            return jsonify({'error': 'Meeting already ended'}), 400

        if 'audio' not in request.files:
            print("No audio file provided")
            return jsonify({'error': 'No audio file provided'}), 400
        file = request.files['audio']
        if file.filename == '':
            print("No file selected")
            return jsonify({'error': 'No file selected'}), 400

        # Save audio file
        upload_folder = 'Uploads'
        os.makedirs(upload_folder, exist_ok=True)
        audio_path = os.path.join(upload_folder, f"{code}_recording.webm")
        file.save(audio_path)
        print(f"Saved audio to {audio_path}")

        # Add to Audio table
        audio_entry = Audio(MeetingCode=code, Timestamp=datetime.utcnow())
        db.session.add(audio_entry)
        db.session.commit()
        print(f"Added audio entry for meeting {code}, AudioID: {audio_entry.AudioID}")

        # Transcribe audio with Whisper
        cache_dir = "C:/Users/Zurum/.cache/whisper"
        os.makedirs(cache_dir, exist_ok=True)
        model_name = "tiny"
        cache_path = os.path.join(cache_dir, f"{model_name}.pt")
        
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                print(f"Loading Whisper model (attempt {attempt}/{max_attempts})")
                model = whisper.load_model(model_name, download_root=cache_dir)
                break
            except RuntimeError as e:
                print(f"Whisper model load error: {e}")
                if "checksum does not match" in str(e) and os.path.exists(cache_path):
                    os.remove(cache_path)
                    print(f"Cleared corrupted model cache: {cache_path}")
                if attempt == max_attempts:
                    raise Exception("Failed to load Whisper model after multiple attempts")
        
        result = model.transcribe(audio_path, fp16=False)
        transcription = result['text'].strip()
        if not transcription:
            print("Transcription is empty")
            return jsonify({'error': 'Transcription failed: No text generated'}), 400
        print(f"Generated transcript: {transcription[:100]}...")

        # Add to Transcripts table
        transcript = Transcripts(
            MeetingCode=code,
            AudioID=audio_entry.AudioID,
            RawText=transcription
        )
        db.session.add(transcript)
        db.session.commit()
        print(f"Saved transcript for meeting {code}, TranscriptID: {transcript.TranscriptID}")

        # Generate summary with GPT-3.5-turbo
        try:
            summary = summarize_transcript_gpt(transcription)
            print(f"Generated summary: {summary[:100]}...")
        except Exception as e:
            print(f"Error generating summary: {e}")
            summary = f"Error generating summary: {str(e)}"

        # Add to Minutes table
        minute = Minutes(
            MeetingCode=code,
            TranscriptID=transcript.TranscriptID,
            SummaryText=summary
        )
        db.session.add(minute)
        db.session.commit()
        print(f"Saved summary for meeting {code}: {summary[:100]}...")

        return jsonify({'message': 'Audio uploaded, transcribed, and summarized'}), 200
    except Exception as e:
        print(f"Error in upload_audio: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

    


def save_summary_as_pdf(text, filename):
    c = canvas.Canvas(filename, pagesize=LETTER)
    width, height = LETTER
    y = height - 72
    for line in text.split('\n'):
        if y <= 72:
            c.showPage()
            y = height - 72
        c.drawString(72, y, line)
        y -= 15
    c.save()

@app.route('/download_audio/<int:audio_id>')
@login_required
def download_audio(audio_id):
    audio = Audio.query.get_or_404(audio_id)
    audio_path = os.path.join('uploads', f"{audio.MeetingCode}_recording.webm")
    if os.path.exists(audio_path):
        return send_file(audio_path, as_attachment=True, download_name=f"meeting_{audio.MeetingCode}_audio.webm")
    abort(404)


@app.route('/download_transcript/<int:transcript_id>')
@login_required
def download_transcript(transcript_id):
    transcript = Transcripts.query.get_or_404(transcript_id)
    text_file = BytesIO(transcript.RawText.encode('utf-8'))
    return send_file(
        text_file,
        as_attachment=True,
        download_name=f"meeting_{transcript.MeetingCode}_transcript.txt",
        mimetype='text/plain'
    )

@app.route('/download_minutes/<int:minute_id>')
@login_required
def download_minutes(minute_id):
    try:
        minute = Minutes.query.get_or_404(minute_id)
        pdf_buffer = BytesIO()
        
        # Set up PDF document with margins
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=LETTER,
            leftMargin=1*inch,
            rightMargin=1*inch,
            topMargin=1*inch,
            bottomMargin=1*inch
        )
        
        # Define styles
        styles = getSampleStyleSheet()
        normal_style = styles['Normal']
        normal_style.fontSize = 12
        normal_style.leading = 14  # Line spacing
        heading_style = styles['Heading1']
        heading_style.fontSize = 14
        bullet_style = ParagraphStyle(
            name='Bullet',
            parent=normal_style,
            leftIndent=20,
            bulletIndent=10,
            bulletFontName='Helvetica',
            bulletFontSize=12
        )
        
        # Build content
        elements = []
        lines = minute.SummaryText.split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            if not line:
                elements.append(Spacer(1, 0.2*inch))
                continue
            
            # Detect section headings (e.g., "Date and Time:", "Action Points:")
            if line.endswith(':') and line in [
                'Date and Time:', 'Meeting Topic:', 'Attendees:', 'Agenda:',
                'Summary of Discussions:', 'Action Points:', 'Conclusion:'
            ]:
                current_section = line
                elements.append(Paragraph(line, heading_style))
                elements.append(Spacer(1, 0.1*inch))
            elif current_section == 'Action Points:' and line.startswith('-'):
                # Format action points as bullets
                elements.append(Paragraph(f'• {line[1:].strip()}', bullet_style))
            else:
                # Regular text with wrapping
                elements.append(Paragraph(line, normal_style))
            elements.append(Spacer(1, 0.1*inch))
        
        # Build PDF
        doc.build(elements)
        pdf_buffer.seek(0)
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=f"meeting_{minute.MeetingCode}_summary.pdf",
            mimetype='application/pdf'
        )
    except Exception as e:
        print(f"Error in download_minutes: {e}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

# Create Admin User on Database Initialization
def create_admin_user():
    print("starting creat_admin_user")
    admin_email = "admin@example.com"  # Customize this
    admin_password = "admin123"  # Customize this
    admin_name = "Admin User"
    try:
        existing_user = Users.query.filter_by(Email = admin_email).first()
        print(f"Existing user check: {existing_user}")
        if not existing_user:
            admin_user = Users(
                Name = admin_name,
                Email = admin_email,
                Password = generate_password_hash(admin_password),
                is_admin = True
            )
            db.session.add(admin_user)
            db.session.commit()
            print(f"Admin user created: {admin_email}/{admin_password}")
        else:
            print("Admin user already exists")
    except Exception as e:
        print(f"Error creating admin user: {e}")

if __name__ == '__main__':
    with app.app_context():
        try:
            print("Creating database and table")
            db.create_all()  # Create new tables
            create_admin_user()  # Create admin user
        except Exception as e:
            print(f"Error during database initialization: {e}")
    socketio.run(app, debug=True)
