"""
Email sender for JobPilot — sends matched-job reports to candidates
with a CSV attachment and an HTML summary.
"""

import os
import smtplib
import csv
import io
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr, formatdate, make_msgid
from email import encoders
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Default SMTP config (Gmail App Password) ──
DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587


def _smtp_config() -> dict:
    """Read SMTP credentials from environment variables."""
    return {
        "host": os.getenv("SMTP_HOST", DEFAULT_SMTP_HOST),
        "port": int(os.getenv("SMTP_PORT", str(DEFAULT_SMTP_PORT))),
        "user": os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "from_name": os.getenv("SMTP_FROM_NAME", "JobPilot"),
        "from_email": os.getenv("SMTP_FROM_EMAIL", os.getenv("SMTP_USER", "")),
    }


def is_email_configured() -> bool:
    """Check whether SMTP credentials are present in the environment."""
    cfg = _smtp_config()
    return bool(cfg["user"] and cfg["password"])


def _build_html_body(
    candidate_name: str,
    jobs: list[dict],
) -> str:
    """Build a simple, clean HTML email — just a message + CTA to check the attached CSV."""
    ts = datetime.now().strftime("%A, %B %d, %Y")
    job_count = len(jobs)

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #f5f7fa;
            margin: 0;
            padding: 0;
        }}
        .container {{
            max-width: 560px;
            margin: 0 auto;
            padding: 24px 16px;
        }}
        .header {{
            background: linear-gradient(135deg, #2563eb, #7c3aed);
            color: white;
            border-radius: 12px 12px 0 0;
            padding: 32px 24px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 26px;
        }}
        .header p {{
            margin: 6px 0 0;
            opacity: 0.9;
            font-size: 14px;
        }}
        .body-card {{
            background: white;
            border-radius: 0 0 12px 12px;
            padding: 28px 24px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.06);
        }}
        .greeting {{
            font-size: 16px;
            color: #1e293b;
            margin: 0 0 16px;
        }}
        .message {{
            color: #334155;
            font-size: 14px;
            line-height: 1.6;
            margin: 0 0 16px;
        }}
        .cta-box {{
            background: #f0fdf4;
            border: 1px solid #bbf7d0;
            border-radius: 8px;
            padding: 16px;
            margin: 16px 0;
            text-align: center;
        }}
        .cta-box p {{
            margin: 0;
            font-size: 14px;
            color: #166534;
        }}
        .footer {{
            text-align: center;
            color: #94a3b8;
            font-size: 12px;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>JobPilot</h1>
            <p>Your Weekly Job Matches</p>
        </div>
        <div class="body-card">
            <p class="greeting">Dear <strong>{candidate_name}</strong>,</p>

            <p class="message">
                Thank you for subscribing to <strong>JobPilot</strong>! We've found <strong>{job_count} job
                match(es)</strong> tailored to your profile and skills for the week of <strong>{ts}</strong>.
            </p>

            <p class="message">
                Our AI analyzed your experience, skills, and preferences, then searched Naukri.com to
                find the most relevant opportunities available right now. Each listing has been scored
                based on skill overlap, experience fit, and location match.
            </p>

            <div class="cta-box">
                <p><strong>Your full job list is attached as a CSV file.</strong><br>
                Open it to see all details &mdash; job title, company, experience, location, skills,
                match score, missing skills, and direct application links.</p>
            </div>

            <p class="message">
                Best of luck with your applications!<br>
                &mdash; The JobPilot Team
            </p>
        </div>
        <div class="footer">
            JobPilot &bull; Automated Job Matching System &bull; {ts}
        </div>
    </div>
</body>
</html>"""


def _build_csv_bytes(jobs: list[dict]) -> bytes:
    """Build a UTF-8 CSV string as bytes, with clean alignment."""
    fields = [
        "#",
        "Source",
        "Job Title",
        "Company",
        "Experience Required",
        "Location",
        "Salary",
        "Skills",
        "Missing Skills",
        "Match Score",
        "Recommendation",
        "Why Match",
        "Application Link",
    ]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(fields)

    for i, j in enumerate(jobs, start=1):
        skills = j.get("skills", [])
        skills_str = "; ".join(skills[:8]) if isinstance(skills, list) else str(skills)
        missing = j.get("missing_skills", "")
        writer.writerow([
            i,
            j.get("source", "Naukri"),
            j.get("job_title", j.get("title", "")),
            j.get("company", ""),
            j.get("experience_required", j.get("experience", "")),
            j.get("location", ""),
            j.get("salary", ""),
            skills_str,
            missing,
            f"{j.get('match_score', '')}%",
            j.get("recommendation", ""),
            j.get("why_match", ""),
            j.get("application_link", ""),
        ])

    return output.getvalue().encode("utf-8")


def send_job_report(
    recipient_email: str,
    candidate_name: str,
    jobs: list[dict],
    csv_path: Optional[Path] = None,
) -> bool:
    """
    Send an HTML email with a ranked job table and CSV attachment.

    Args:
        recipient_email: Candidate's email address.
        candidate_name: Candidate's name for the greeting.
        jobs: List of scored job dicts.
        csv_path: Optional path to an existing CSV file to attach.
                  If omitted, builds the CSV from *jobs*.

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    if not is_email_configured():
        logger.warning("SMTP not configured — skipping email")
        return False

    cfg = _smtp_config()
    if not recipient_email:
        logger.warning("No recipient email — skipping")
        return False

    # Limit jobs to top 20 for email readability
    display_jobs = jobs[:20]

    # ── Build message ──
    msg = MIMEMultipart("mixed")
    msg["From"] = formataddr((cfg["from_name"], cfg["from_email"]))
    msg["To"] = recipient_email
    msg["Subject"] = Header(
        f"JobPilot — {len(display_jobs)} Job Matches Found for You ({datetime.now().strftime('%d %b %Y')})",
        "utf-8",
    )
    msg["Date"] = formatdate(localtime=True)
    msg["X-Mailer"] = "JobPilot-1.0"
    msg["Message-ID"] = make_msgid(domain="jobpilot.local")

    # ── Part 1: HTML body ──
    html = _build_html_body(candidate_name, display_jobs)
    part_html = MIMEText(html, "html", "utf-8")
    msg.attach(part_html)

    # ── Part 2: CSV attachment ──
    if csv_path and Path(csv_path).exists():
        with open(csv_path, "rb") as f:
            csv_data = f.read()
    else:
        csv_data = _build_csv_bytes(jobs)

    part_csv = MIMEBase("text", "csv", charset="utf-8")
    part_csv.set_payload(csv_data)
    encoders.encode_base64(part_csv)
    ts = datetime.now().strftime("%Y%m%d")
    part_csv.add_header(
        "Content-Disposition",
        "attachment",
        filename=f"JobPilot_Matches_{ts}.csv",
    )
    msg.attach(part_csv)

    # ── Send ──
    try:
        logger.info("Connecting to SMTP %s:%d ...", cfg["host"], cfg["port"])
        server = smtplib.SMTP(cfg["host"], cfg["port"])
        server.set_debuglevel(1)  # log SMTP conversation
        server.starttls()
        server.login(cfg["user"], cfg["password"])
        result = server.sendmail(cfg["from_email"], [recipient_email], msg.as_string())
        server.quit()
        if result:
            logger.warning("SMTP deferred delivery for %s: %s", recipient_email, result)
            print(f"  [Email] SMTP accepted but deferred — check spam folder: {result}")
        else:
            logger.info("Email accepted by SMTP server for %s", recipient_email)
            print(f"  [Email] ✓ Accepted by SMTP server for {recipient_email}")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error(
            "SMTP authentication failed for %s — check SMTP_USER / SMTP_PASSWORD",
            cfg["user"],
        )
    except smtplib.SMTPException as e:
        logger.error("SMTP error: %s", e)
    except Exception as e:
        logger.error("Failed to send email: %s", e)

    return False
