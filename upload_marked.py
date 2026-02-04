from __future__ import annotations

import os
import re
import sys
import time
import base64
import pathlib
import requests
from dotenv import load_dotenv

# ----------------------------
# Load env
# ----------------------------
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
ENV_PATH = SCRIPT_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

WISE_BASE = "https://na-api.wiseapp.live"
FILE_BASE = "https://na-files.wiseapp.live"
UA = "VendorIntegrations/jmcg-maths-mentors"

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

REQUIRED_ENV_VARS = [
    "WISE_API_KEY",
    "WISE_NAMESPACE",
    "WISE_BASIC_USER",
    "WISE_BASIC_PASS",
]


def validate_env() -> None:
    """Check all required environment variables are set."""
    missing = [k for k in REQUIRED_ENV_VARS if not os.environ.get(k)]
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        print("Please check your .env file or Streamlit secrets configuration.")
        sys.exit(1)


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
# API calls with retry
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
    Multipart upload to Wise file service with retry logic.
    Returns file metadata to attach as feedback.
    """
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
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

        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                print(f"  [Retry {attempt}/{MAX_RETRIES}] Upload failed, retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                raise last_error


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
# Format: {class}__{assessmentID}__{student}__{studentID}__{filename} Marked.pdf
# Assessment ID and Student ID are both 24 hex character MongoDB ObjectIDs
FILENAME_RE = re.compile(
    r"""
    ^(?P<class>.+?)__
    (?P<assessment>[a-f0-9]{24})__
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
    validate_env()
    print("=== Upload Marked PDFs ===")

    # Accept folder path from command line argument
    if len(sys.argv) < 2:
        print("Usage: python upload_marked.py <folder_path>")
        print("ERROR: No folder path provided.")
        sys.exit(1)

    folder = sys.argv[1].strip().strip('"')
    base = pathlib.Path(folder)

    if not base.exists():
        print(f"ERROR: Folder does not exist: {base}")
        sys.exit(1)

    files = list(base.glob("*Marked.pdf"))
    if not files:
        print("No '* Marked.pdf' files found in folder.")
        print("Make sure your marked files end with ' Marked.pdf' (with a space before 'Marked').")
        return

    print(f"Found {len(files)} marked PDFs.\n")

    uploaded = 0
    skipped = 0
    failed = 0

    for i, pdf in enumerate(files, 1):
        m = FILENAME_RE.match(pdf.name)
        if not m:
            print(f"[{i}/{len(files)}] SKIP - Filename format not recognized: {pdf.name}")
            skipped += 1
            continue

        assessment_id = m.group("assessment")
        student_id = m.group("student_id")

        try:
            print(f"[{i}/{len(files)}] Uploading: {pdf.name}")
            file_data = upload_file_to_wise(pdf)
            attach_feedback(assessment_id, student_id, file_data)
            print(f"  SUCCESS - Feedback attached for student {student_id[:8]}...")
            uploaded += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1

    print("\n" + "=" * 40)
    print("Upload Complete!")
    print(f"  Uploaded: {uploaded}")
    print(f"  Skipped:  {skipped}")
    print(f"  Failed:   {failed}")
    print("=" * 40)


if __name__ == "__main__":
    main()
