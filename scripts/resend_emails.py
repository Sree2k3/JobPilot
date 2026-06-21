"""Re-send emails from the last saved matched results (no re-scraping)."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.jobpilot.scraper.email_sender import send_job_report
from src.jobpilot.scraper.sent_history import filter_new_jobs, mark_as_sent

files = [
    ("Autage Sachin", "sachin.autage111@gmail.com",
     "data/scraped/matched_Autage_Sachin_20260621_215728.json"),
    ("Rajesh VP", "sreedhar67patnaik@gmail.com",
     "data/scraped/matched_Rajesh_VP_20260621_220048.json"),
    ("Sreedhar Patnaik", "sreedhar67patnaik@gmail.com",
     "data/scraped/matched_Sreedhar_Patnaik_20260621_220229.json"),
]

for name, email, path in files:
    with open(path) as f:
        jobs = json.load(f)

    jobs_to_send = filter_new_jobs(email, jobs, name=name)
    print(f"{name} ({email}): {len(jobs)} total, {len(jobs_to_send)} to send")

    if not jobs_to_send:
        print("  -> All already sent, skipping")
        continue

    ok = send_job_report(email, name, jobs_to_send)
    if ok:
        links = [j.get("application_link", "") for j in jobs_to_send if j.get("application_link")]
        mark_as_sent(email, links, name=name)
        print("  -> Sent!")
    else:
        print("  -> FAILED")
