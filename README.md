# Intelligent Meeting Minutes Transcriber

An AI-powered web application that enables users to **conduct online meetings**, **record audio**, **transcribe speech into text**, and **automatically generate structured meeting minutes** in PDF format.

---

## Features

- **Real-time Meeting Recording**
- **Multi-user Meeting Room (WebSocket-based)**
- **Automatic Speech-to-Text Transcription** using Whisper
- **AI-powered Summarization** using GPT
- **Structured Meeting Minutes Generation (PDF)**
- **Speaker Detection (Real-time)**
- **Meeting Duration Timer**
- **User Authentication System (Login/Register)**
- **Admin Panel for System Monitoring**
- **Audio Upload for Testing Transcription Independently**

---

## System Architecture

```

Client (Browser)
↓
Flask Web Server (Backend)
↓
Whisper (Transcription Engine)
↓
GPT Model (Summarization Engine)
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
- SQLAlchemy

### AI & Processing
- Whisper (Speech-to-Text)
- OpenAI GPT (Summarization)

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
OPENAI_API_KEY=your_openai_api_key_here
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
Then enter the required details as shown on the screen

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
2. Starts or joins a meeting
3. Audio is recorded in real-time
4. Recording is sent to the backend
5. Whisper transcribes audio → raw text
6. GPT summarizes transcript → structured minutes
7. PDF is generated and stored
8. User downloads the meeting summary

---

## Testing the System

### Multi-user Testing

* Open the app in:

  * Multiple browsers (Chrome, Edge)
  * Incognito windows
* Login with different users
* Join the same meeting code

---

### Upload Audio (Standalone Testing)

You can test transcription without meetings via:

```
/upload_audio
```

---

## Project Structure

```
meeting-transcriber/
│
├── app.py
├── models.py
├── routes.py
├── forms.py
├── __init__.py
│
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── register.html
│   ├── meeting.html
│   ├── room.html
│
├── static/
│   ├── css/
│   │   └── style.css
│   ├── recordings/
│
├── recordings/
├── .env
└── requirements.txt
```

---

## Known Limitations

* Transcription accuracy depends on audio quality
* Speaker detection is volume-based (not speaker recognition)
* GPT summarization may occasionally be inconsistent
* No advanced role-based permissions
* SQLite limits scalability

---

## Security Notes

* Passwords are currently stored in plain text (**use hashing in production**)
* API keys must not be exposed publicly
* Use HTTPS in production
* Use MySQL in production
---

## Future Improvements

* Speaker identification (voice recognition)
* Meeting analytics dashboard
* Cloud storage integration
* Fine-tuned summarization models
* Improved mobile responsiveness

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