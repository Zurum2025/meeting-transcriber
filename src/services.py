"""Everything that isn't routing or data access: talking to Whisper,
talking to Gemini, merging speaker transcripts, and building the PDF.

Kept separate from routes.py so the request-handling code doesn't have
to know how any of this works internally.
"""

import json
import os
from datetime import datetime

from flask import current_app
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from extensions import db
from models import Audio, Minutes, Participants, Transcripts, Users

_whisper_model = None


def get_whisper_model():
    """Lazily load (and cache) the Whisper model. Loading it eagerly at
    import time would slow down every `flask` CLI command, including
    `flask db migrate`, so this stays lazy."""
    global _whisper_model
    if _whisper_model is None:
        import whisper  # imported lazily for the same reason

        cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "whisper")
        os.makedirs(cache_dir, exist_ok=True)
        current_app.logger.info("Loading Whisper model...")
        _whisper_model = whisper.load_model("tiny", download_root=cache_dir)
    return _whisper_model


def summarize_transcript_gpt(transcript_text, attendee_names=None):
    """Turn a speaker-labeled transcript into structured minutes via Gemini."""
    try:
        from google import genai

        api_key = current_app.config.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("Missing Gemini API key. Set GEMINI_API_KEY in your .env file.")

        client = genai.Client(api_key=api_key)

        max_chars = 40000
        if len(transcript_text) > max_chars:
            transcript_text = transcript_text[:max_chars]

        prompt = (
            "You are generating structured meeting minutes from a speaker-labeled "
            "transcript (each line starts with the speaker's name). Extract the "
            "requested fields. For action_points, capture every concrete task, "
            "commitment, or follow-up mentioned, including who said it if named.\n\n"
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
                        "agenda": {"type": "string"},
                        "summary": {"type": "string"},
                        "action_points": {"type": "array", "items": {"type": "string"}},
                        "conclusion": {"type": "string"},
                    },
                    "required": ["meeting_topic", "agenda", "summary", "action_points", "conclusion"],
                },
            },
        )
        data = json.loads(response.text)

        action_points = data.get("action_points") or []
        action_points_text = (
            "\n".join(f"- {p}" for p in action_points)
            if action_points
            else "- No specific action points identified."
        )
        attendees_text = ", ".join(attendee_names) if attendee_names else "Participants"
        meeting_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        return f"""
        Date and Time: {meeting_date}
        Meeting Topic: {data.get('meeting_topic', 'General Discussion')}
        Attendees: {attendees_text}
        Agenda: {data.get('agenda', 'Summarized from transcript')}
        Summary of Discussions: {data.get('summary', '')}
        Action Points:
        {action_points_text}
        Conclusion: {data.get('conclusion', 'Meeting concluded.')}
        """
    except json.JSONDecodeError:
        return "Error generating summary: model returned malformed JSON"
    except Exception as e:
        current_app.logger.error(f"Error in summarize_transcript_gpt: {e}")
        return f"Error generating summary: {str(e)}"


def finalize_meeting_summary(code):
    """Merge all per-participant transcripts received so far into one
    speaker-labeled transcript, ordered by when each segment was actually
    spoken, then regenerate the meeting minutes from it."""
    try:
        audio_rows = Audio.query.filter_by(MeetingCode=code).filter(Audio.UserID.isnot(None)).all()
        if not audio_rows:
            return

        entries = []  # (absolute_start_seconds, speaker_name, text)
        for audio in audio_rows:
            speaker_transcript = Transcripts.query.filter_by(AudioID=audio.AudioID, IsMerged=False).first()
            if not speaker_transcript or not speaker_transcript.SegmentsJSON:
                continue
            user = Users.query.get(audio.UserID)
            speaker_name = user.Name if user else f"User {audio.UserID}"
            base_time = (audio.ClientStartTime / 1000.0) if audio.ClientStartTime else 0
            for seg in json.loads(speaker_transcript.SegmentsJSON):
                text = seg.get("text", "").strip()
                if text:
                    entries.append((base_time + seg.get("start", 0), speaker_name, text))

        if not entries:
            return
        entries.sort(key=lambda e: e[0])

        merged_lines = []
        current_speaker, current_words = None, []
        for _, speaker, text in entries:
            if speaker == current_speaker:
                current_words.append(text)
            else:
                if current_speaker is not None:
                    merged_lines.append(f"{current_speaker}: {' '.join(current_words)}")
                current_speaker, current_words = speaker, [text]
        merged_lines.append(f"{current_speaker}: {' '.join(current_words)}")
        merged_text = "\n".join(merged_lines)

        old_merged = Transcripts.query.filter_by(MeetingCode=code, IsMerged=True).first()
        if old_merged:
            Minutes.query.filter_by(TranscriptID=old_merged.TranscriptID).delete()
            db.session.delete(old_merged)
            db.session.commit()

        merged_transcript = Transcripts(MeetingCode=code, AudioID=None, RawText=merged_text, IsMerged=True)
        db.session.add(merged_transcript)
        db.session.commit()

        attendee_names = [p.users.Name for p in Participants.query.filter_by(MeetingCode=code).join(Users).all()]
        summary = summarize_transcript_gpt(merged_text, attendee_names=attendee_names)

        db.session.add(Minutes(MeetingCode=code, TranscriptID=merged_transcript.TranscriptID, SummaryText=summary))
        db.session.commit()
        current_app.logger.info(
            f"Refreshed merged transcript + minutes for meeting {code} ({len(audio_rows)} speaker clip(s))"
        )
    except Exception as e:
        current_app.logger.error(f"Error in finalize_meeting_summary: {e}")
        db.session.rollback()


def save_summary_as_pdf(text, filename):
    """Simple line-by-line PDF writer. Kept for parity with the original
    codebase — download_minutes() below uses the richer SimpleDocTemplate
    approach instead, so this one is currently unused, but other code may
    still reference it."""
    c = canvas.Canvas(filename, pagesize=LETTER)
    width, height = LETTER
    y = height - 72
    for line in text.split("\n"):
        if y <= 72:
            c.showPage()
            y = height - 72
        c.drawString(72, y, line)
        y -= 15
    c.save()


def build_minutes_pdf(summary_text):
    """Build the polished, section-aware minutes PDF used by download_minutes()."""
    from io import BytesIO

    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=LETTER,
        leftMargin=1 * inch,
        rightMargin=1 * inch,
        topMargin=1 * inch,
        bottomMargin=1 * inch,
    )

    styles = getSampleStyleSheet()
    normal_style = styles["Normal"]
    normal_style.fontSize = 12
    normal_style.leading = 14
    heading_style = styles["Heading1"]
    heading_style.fontSize = 14
    bullet_style = ParagraphStyle(
        name="Bullet",
        parent=normal_style,
        leftIndent=20,
        bulletIndent=10,
        bulletFontName="Helvetica",
        bulletFontSize=12,
    )

    elements = []
    lines = summary_text.split("\n")
    current_section = None
    section_headings = {
        "Date and Time:", "Meeting Topic:", "Attendees:", "Agenda:",
        "Summary of Discussions:", "Action Points:", "Conclusion:",
    }

    for line in lines:
        line = line.strip()
        if not line:
            elements.append(Spacer(1, 0.2 * inch))
            continue
        if line.endswith(":") and line in section_headings:
            current_section = line
            elements.append(Paragraph(line, heading_style))
            elements.append(Spacer(1, 0.1 * inch))
        elif current_section == "Action Points:" and line.startswith("-"):
            elements.append(Paragraph(f"\u2022 {line[1:].strip()}", bullet_style))
        else:
            elements.append(Paragraph(line, normal_style))
        elements.append(Spacer(1, 0.1 * inch))

    doc.build(elements)
    pdf_buffer.seek(0)
    return pdf_buffer