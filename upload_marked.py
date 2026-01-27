from __future__ import annotations

import os
import re
import base64
import pathlib
import requests
from dotenv import load_dotenv

# ----------------------------
# Load env
# ----------------------------
ENV_PATH = pathlib.Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

WISE_BASE = "https://na-api.wiseapp.live"
FILE_BASE = "https://na-files.wiseapp.live"
UA = "VendorIntegrations/jmcg-maths-mentors"

# ----------------------------
# Auth helpers
# ----------------------------
def basic_auth_header() -> str:
    user = os.environ["WISE_BASIC_USER"]
    pw = os.environ["WISE_BASIC_PASS"]
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return f"Basic {token}"


def headers(json=True):
    h = {
        "User-Agent": UA,
        "x-api-key": os.environ["WISE_API_KEY"],
        "x-wise-namespace": os.environ["WISE_NAMESPACE"],
        "Authorization": basic_auth_header(),
    }
    if json:
        h["Content-Type"] = "application/json"
    return h


# ----------------------------
# API calls
# ----------------------------
def wise_post(path, payload):
    r = requests.post(
        f"{WISE_BASE}{path}",
        headers=headers(),
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def upload_file_to_wise(file_path: pathlib.Path) -> dict:
    """
    Multipart upload to Wise file service.
    Returns file metadata to attach as feedback.
    """
    init = wise_post(
        "/files/initiateUpload",
        {
            "fileName": file_path.name,
            "fileType": "pdf",
        },
    )

    upload_url = init["data"]["uploadUrl"]
    file_key = init["data"]["fileKey"]

    with open(file_path, "rb") as f:
        r = requests.put(upload_url, data=f, timeout=180)
        r.raise_for_status()

    complete = wise_post(
        "/files/completeUpload",
        {
            "fileKey": file_key,
        },
    )

    return complete["data"]


def attach_feedback(assessment_id: str, student_id: str, file_data: dict):
    wise_post(
        "/user/submitAssessmentFeedback",
        {
            "assessmentId": assessment_id,
            "studentId": student_id,
            "attachments": [
                {
                    "fileKey": file_data["fileKey"],
                    "fileName": file_data["fileName"],
                    "fileType": "pdf",
                }
            ],
        },
    )


# ----------------------------
# Filename parsing
# ----------------------------
FILENAME_RE = re.compile(
    r"""
    ^(?P<class>.+?)__
    (?P<assessment>[^_]+)__
    (?P<student>.+?)__
    (?P<student_id>[a-f0-9]{24})__
    .+?\sMarked\.pdf$
    """,
    re.VERBOSE | re.IGNORECASE,
)


# ----------------------------
# Main
# ----------------------------
def main():
    print("=== Upload Marked PDFs ===")

    folder = input("Paste folder path containing MARKED PDFs:\n> ").strip().strip('"')
    base = pathlib.Path(folder)

    if not base.exists():
        print("Folder does not exist.")
        return

    files = list(base.glob("*Marked.pdf"))
    if not files:
        print("No '* Marked.pdf' files found.")
        return

    print(f"Found {len(files)} marked PDFs.\n")

    uploaded = 0
    skipped = 0

    for pdf in files:
        m = FILENAME_RE.match(pdf.name)
        if not m:
            print(f"[SKIP] Filename does not match expected format: {pdf.name}")
            skipped += 1
            continue

        assessment_id = m.group("assessment")
        student_id = m.group("student_id")

        try:
            print(f"Uploading: {pdf.name}")
            file_data = upload_file_to_wise(pdf)
            attach_feedback(assessment_id, student_id, file_data)
            uploaded += 1
        except Exception as e:
            print(f"[ERROR] Failed for {pdf.name}: {e}")

    print("\nDone.")
    print(f"Uploaded: {uploaded}")
    print(f"Skipped: {skipped}")


if __name__ == "__main__":
    main()
