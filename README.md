# Waveform Studio — AI Meeting Transcription & Minutes

An AI-powered web application that enables users to **conduct online meetings**, **record audio**, **transcribe speech into text**, and **automatically generate structured meeting minutes** in PDF format.

---

## Features

- **Real-time Meeting Recording**
- **Multi-user Meeting Room (WebSocket-based)**, styled after modern video conferencing tools
- **Per-participant Recording with Server-side Merge** — every participant (chairman and members) records their own mic independently; clips are merged server-side by user and timestamp into a single speaker-labeled transcript
- **Automatic Speech-to-Text Transcription** using Whisper
- **AI-powered Summarization** using Google Gemini
- **Structured Meeting Minutes Generation (PDF)**
- **Speaking Indicator (Real-time, volume-based)**
- **Meeting Duration Timer**
- **User Authentication System (Login/Register)**
- **Admin Panel for System Monitoring**
- **Standalone Audio Upload for Testing Transcription Independently**

---

## System Architecture

```

Client (Browser)
↓
Flask Web Server (Backend)
↓
Whisper (Transcription Engine)
↓
Gemini (Summarization Engine)
↓
PDF Generator (ReportLab)
↓
Database (SQLite / SQLAlchemy)

````

---

## Technologies Used

### Frontend
- HTML5
- CSS3 (Custom + Bootstrap)
- JavaScript (Vanilla)
- Socket.IO (Real-time communication)

### Backend
- Python
- Flask
- Flask-SocketIO
- Flask-Login
- Flask-WTF (CSRF protection)
- Flask-Migrate (database schema migrations)
- SQLAlchemy

### AI & Processing
- Whisper (Speech-to-Text)
- Google Gemini (Summarization)

### Others
- ReportLab (PDF generation)
- FFmpeg (Audio processing)
- python-dotenv (Environment variables)

---

## Installation Guide

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/meeting-transcriber.git
cd meeting-transcriber
````

### 2. Create Virtual Environment

```bash
python -m venv venv
```

Activate it:

* **Windows**

```bash
venv\Scripts\activate
```

* **Mac/Linux**

```bash
source venv/bin/activate
```

---

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 4. Install FFmpeg (Required for Whisper)

Download from: [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)
Ensure it is added to your system PATH.

---

### 5. Setup Environment Variables

Create a `.env` file in the root directory:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

The following are optional and fall back to sensible defaults if omitted:

```env
SECRET_KEY=change-me-in-production
DATABASE_URL=sqlite:///db.sqlite3
UPLOAD_FOLDER=Uploads
GEMINI_MODEL=gemini-3.1-flash-lite
SOCKETIO_CORS_ALLOWED_ORIGINS=*
```

---

### 6. Setup Database

```bash
flask db init
flask db migrate -m "initial"
flask db upgrade
```
---

### 7. Create Administrator

```bash
flask create-admin
```
Then enter the required details as shown on the screen.

### 8. Run the Application

```bash
python app.py
```

Open in browser:

```
http://127.0.0.1:5000
```

---

## How It Works

1. User logs in or registers
2. Starts or joins a meeting room
3. Each participant's audio is recorded independently in real-time
4. On meeting end, each participant's recording is uploaded and tagged with their user ID and client start time
5. Whisper transcribes each participant's audio → per-speaker raw text
6. The backend merges all speaker transcripts into one speaker-labeled transcript, ordered by when things were actually said
7. Gemini summarizes the merged transcript → structured minutes
8. PDF is generated and stored
9. User downloads the meeting summary

---

## Testing the System

### Multi-user Testing

* Open the app in:

  * Multiple browsers (Chrome, Edge)
  * Incognito windows
  * Different devices
  
* Login with different users
* Join the same meeting code

---

### Upload Audio (Standalone Testing)

You can test the Whisper + Gemini pipeline directly, without opening a full meeting room, via:

```
/test_upload
```

---

## Project Structure

```
waveform-studio/
│
├── app.py                 # App factory only
├── config.py               # Environment-driven settings + TestConfig
├── extensions.py            # Unbound extension instances (db, login_manager, migrate, csrf, socketio)
├── models.py               # SQLAlchemy models
├── forms.py                # Flask-WTF forms
├── decorators.py            # Admin access control
├── routes.py                # All HTTP routes (init_routes)
├── sockets.py               # Socket.IO handlers (init_sockets)
├── services.py               # Whisper transcription, Gemini summarization, transcript merging, PDF generation
├── commands.py               # `flask create-admin` CLI command
│
├── templates/
│   ├── base.html
│   ├── home.html
│   ├── login.html
│   ├── register.html
│   ├── meeting.html
│   ├── room.html
│   ├── view_meetings.html
│   ├── transcript.html
│   ├── test_upload.html
│   ├── test_result.html
│   ├── admin.html
│   └── 403.html
│
├── static/
│   └── css/
│       └── style.css
│
├── Uploads/                 # Recorded audio (gitignored, path configurable via UPLOAD_FOLDER)
├── migrations/                # Flask-Migrate schema migrations (gitignored)
├── .env
└── requirements.txt
```

---

## Known Limitations

* Transcription accuracy depends on audio quality
* Speaking indicators in the meeting room UI are volume-based, not true speaker recognition — actual speaker labeling in the generated minutes instead comes from each participant recording their own mic independently, merged server-side by user and timestamp
* Gemini summarization may occasionally be inconsistent
* No advanced role-based permissions beyond chairman/member
* SQLite limits scalability
* Late joiners to a meeting are not captured in that meeting's recording
* Timestamp alignment between participants' clips is approximate, not frame-accurate
* The "Download audio" button on the meetings page currently assumes one audio file per meeting; this doesn't yet reflect the multi-participant recording model

---

## Security Notes

* Passwords are hashed (Werkzeug `generate_password_hash`/`check_password_hash`), never stored in plain text
* Set a real `SECRET_KEY` via environment variable in production — do not use the development default
* API keys must not be exposed publicly
* Use HTTPS in production
* Use MySQL in production (SQLAlchemy's `inspect()` is used in place of raw `sqlite3` specifically to keep the codebase database-agnostic for this migration)

---

## Future Improvements

* WebRTC video streaming — the meeting room tile layout is already designed to accommodate a video element replacing the avatar circle
* True speaker identification (voice recognition) for the live in-room indicator
* Meeting analytics dashboard
* Cloud storage integration
* Fine-tuned summarization models
* A proper multi-file "Download audio" flow for meetings with multiple participant recordings

---

## Authors

*Developed as a Final Year Project by:*</br>
Ukonu Chizurum Chiemela - 2021/SC/19631</br>
Okoli Elisha Chinonyerem - 2021/SC/20627

**Supervisor**</br>
Engr. Eze Udu

---

## License

This project is for academic purposes.

**Submitted to**:</br>The Department of Computer Science, Alex Ekwueme Federal University, Nigeria.

**General Project Coordinator**:</br> Mr Afolabi Idris Yinka
