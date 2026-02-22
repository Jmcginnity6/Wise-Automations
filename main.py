from __future__ import annotations

import os
import re
import sys
import base64
import pathlib
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from dateutil import parser as dateparser
from PIL import Image

# ---- Load .env reliably (Windows-safe) ----
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
ENV_PATH = SCRIPT_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

WISE_BASE = "https://na-api.wiseapp.live"
UA = "VendorIntegrations/jmcg-maths-mentors"

DOWNLOAD_DATE = datetime.now().strftime("%Y-%m-%d")
DOWNLOAD_ROOT = SCRIPT_DIR / "downloads" / f"Downloaded_{DOWNLOAD_DATE}"

# Can be overridden via CLI argument: python main.py <days>
DAYS_BACK = int(sys.argv[1]) if len(sys.argv) > 1 else 7
DEBUG = False

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

REQUIRED_ENV_VARS = [
    "WISE_API_KEY",
    "WISE_NAMESPACE",
    "WISE_INSTITUTE_ID",
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
# Auth + headers
# ----------------------------
def _basic_auth_header() -> str:
    user = os.environ["WISE_BASIC_USER"]
    pw = os.environ["WISE_BASIC_PASS"]
    token = base64.b64encode(f"{user}:{pw}".encode("utf-8")).decode("utf-8")
    return f"Basic {token}"


def wise_headers(content_type: bool = True) -> dict:
    h = {
        "User-Agent": UA,
        "x-wise-namespace": os.environ["WISE_NAMESPACE"],
        "x-api-key": os.environ["WISE_API_KEY"],
        "Authorization": _basic_auth_header(),
    }
    if content_type:
        h["Content-Type"] = "application/json"
    return h


def wise_get(path: str, params: dict | None = None) -> dict:
    url = f"{WISE_BASE}{path}"
    r = requests.get(url, headers=wise_headers(content_type=False), params=params, timeout=60)
    r.raise_for_status()
    return r.json()


# ----------------------------
# Wise endpoints
# ----------------------------
def get_live_classes(institute_id: str) -> list[dict]:
    data = wise_get(
        f"/institutes/{institute_id}/classes",
        params={"classType": "LIVE", "showCoTeachers": "true"},
    )

    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        inner = data["data"]
        if isinstance(inner.get("classes"), list):
            return inner["classes"]

    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"]
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("classes"), list):
        return data["classes"]
    return []


def get_content_timeline(class_id: str) -> dict:
    return wise_get(
        f"/user/classes/{class_id}/contentTimeline",
        params={"showSequentialLearningDisabledSections": "true"},
    )


def get_assessment(assessment_id: str) -> dict:
    return wise_get(f"/user/getAssessment/{assessment_id}")


# ----------------------------
# Helpers
# ----------------------------
def safe_part(s: str, max_len: int = 60) -> str:
    s = (s or "").strip()
    s = re.sub(r'[<>:"/\\|?*\n\r\t]+', " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("__", "_")
    return s[:max_len] if len(s) > max_len else s


def parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        if value > 10_000_000_000:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            dt = dateparser.parse(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None
    return None


def find_any_timestamp(obj: dict) -> datetime | None:
    COMMON_KEYS = (
        "submittedAt", "submitted_at", "submissionTime", "submittedOn",
        "createdAt", "updatedAt", "time", "timestamp", "date",
    )
    found: list[datetime] = []

    def walk(x):
        if isinstance(x, dict):
            for k in COMMON_KEYS:
                dt = parse_dt(x.get(k))
                if dt:
                    found.append(dt)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(obj)
    return max(found) if found else None


def extract_student_id(sub: dict) -> str:
    v = sub.get("student_id") or sub.get("studentId") or sub.get("student")
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return str(v.get("_id") or v.get("id") or "")
    return ""


def extract_student_name(sub: dict) -> str:
    v = sub.get("studentId")
    if isinstance(v, dict) and isinstance(v.get("name"), str):
        return v["name"].strip()

    student = sub.get("student")
    if isinstance(student, dict):
        first = student.get("firstName") or student.get("first_name")
        last = student.get("lastName") or student.get("last_name")
        if first or last:
            return " ".join(x for x in [first, last] if x)
        for k in ("name", "fullName"):
            if student.get(k):
                return str(student[k]).strip()

    for k in ("studentName", "student_name", "fullName", "name"):
        vv = sub.get(k)
        if isinstance(vv, str) and vv.strip():
            return vv.strip()

    return "unknown_student"


def extract_assessment_ids(timeline: dict) -> list[str]:
    ids: set[str] = set()

    def walk(x):
        if isinstance(x, dict):
            et = str(x.get("entityType") or x.get("type") or x.get("contentType") or "").lower()
            if "assessment" in et or "assignment" in et or "homework" in et:
                for k in ("_id", "id", "assessmentId", "assignment_id", "assignmentId"):
                    vv = x.get(k)
                    if vv:
                        ids.add(str(vv))
            for k in ("assessmentId", "assignment_id", "assignmentId"):
                vv = x.get(k)
                if vv:
                    ids.add(str(vv))
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(timeline)
    return sorted(ids)


SUBMISSION_HINT_KEYS = {"studentId", "student_id", "submissionId", "submission_id", "attachments", "files", "submittedAt"}


def find_submission_lists_anywhere(obj) -> list[tuple[str, list[dict]]]:
    matches: list[tuple[str, list[dict]]] = []

    def looks_like_submission_dict(d: dict) -> bool:
        keys = set(d.keys())
        return any(k in keys for k in SUBMISSION_HINT_KEYS)

    def walk(x, path: str):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(x, list):
            if x and all(isinstance(i, dict) for i in x):
                score = sum(1 for i in x[:10] if looks_like_submission_dict(i))
                if score > 0:
                    matches.append((path, x))
            for i, v in enumerate(x):
                walk(v, f"{path}[{i}]")

    walk(obj, "")
    return matches


def unique_path(base_dir: pathlib.Path, desired_name: str) -> pathlib.Path:
    p = base_dir / desired_name
    if not p.exists():
        return p
    stem = p.stem
    suffix = p.suffix
    for i in range(2, 9999):
        candidate = base_dir / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
    return base_dir / f"{stem} ({int(datetime.now().timestamp())}){suffix}"


def download_url(url: str, out_path: pathlib.Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)


# ----------------------------
# Attachment handling (dedupe + type)
# ----------------------------
def extract_attachments(sub: dict) -> list[dict]:
    """
    Return list of unique attachments with:
      - kind: 'pdf' or 'image'
      - url, filename, s3Key
    Dedupe by s3Key when present; fallback by filename.
    Prefer 'path' over 's3FilePath'.
    """
    attachments = sub.get("attachments")
    if not isinstance(attachments, list):
        attachments = []

    picked: list[dict] = []
    seen_keys: set[str] = set()
    seen_names: set[str] = set()

    for a in attachments:
        if not isinstance(a, dict):
            continue

        a_type = str(a.get("type") or "").lower()
        fname = str(a.get("filename") or a.get("fileName") or a.get("name") or "")
        s3key = str(a.get("s3Key") or a.get("key") or "")

        # choose url (prefer path)
        url = a.get("path") or a.get("s3FilePath") or a.get("url") or a.get("downloadUrl")
        if not isinstance(url, str) or not url.startswith("http"):
            continue

        # determine kind
        ext = pathlib.Path(fname).suffix.lower() if fname else pathlib.Path(urlparse(url).path).suffix.lower()
        kind = None
        if a_type == "pdf" or ext == ".pdf":
            kind = "pdf"
        elif a_type in ("image", "png", "jpg", "jpeg", "webp") or ext in IMAGE_EXTS:
            kind = "image"
        else:
            continue

        # dedupe
        if s3key:
            if s3key in seen_keys:
                continue
            seen_keys.add(s3key)
        else:
            keyname = (fname or url).lower()
            if keyname in seen_names:
                continue
            seen_names.add(keyname)

        if not fname:
            fname = pathlib.Path(urlparse(url).path).name or f"attachment{ext or ''}"

        picked.append({"kind": kind, "url": url, "filename": fname, "s3Key": s3key})

    return picked


# ----------------------------
# Image -> PDF
# ----------------------------
def images_to_pdf(image_paths: list[pathlib.Path], out_pdf: pathlib.Path) -> None:
    """
    Combine images into a multi-page PDF using Pillow.
    """
    if not image_paths:
        return

    # open all and convert to RGB
    imgs = []
    for p in image_paths:
        img = Image.open(p)
        # If image has alpha, convert properly
        if img.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
        imgs.append(img)

    first, rest = imgs[0], imgs[1:]
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    first.save(out_pdf, save_all=True, append_images=rest)


# ----------------------------
# Main: one folder, PDFs + images-as-PDF
# ----------------------------
def main():
    validate_env()
    institute_id = os.environ["WISE_INSTITUTE_ID"]
    since = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)

    DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)

    classes = get_live_classes(institute_id)
    print(f"LIVE classes found: {len(classes)}")
    print(f"Download folder: {DOWNLOAD_ROOT.resolve()}")
    print(f"Since (UTC): {since.isoformat()}")
    print("PDF-only output: ON (PDFs download; images get combined into a PDF)")

    downloaded_pdfs = 0
    created_image_pdfs = 0
    ignored_no_files = 0

    for c in classes:
        class_id = str(c.get("_id") or c.get("id") or "")
        class_name = safe_part(c.get("name") or c.get("className") or f"class_{class_id}", max_len=50)
        if not class_id:
            continue

        timeline = get_content_timeline(class_id)
        assessment_ids = extract_assessment_ids(timeline)

        if DEBUG:
            print(f"\n[DEBUG] Class {class_name} -> assessment ids: {len(assessment_ids)}")

        for aid in assessment_ids:
            assessment = get_assessment(aid)

            candidate_lists = find_submission_lists_anywhere(assessment)
            if not candidate_lists:
                continue

            candidate_lists.sort(key=lambda t: len(t[1]), reverse=True)
            _, submissions = candidate_lists[0]

            # best-effort title
            title = None
            if isinstance(assessment, dict):
                for pth in ("data.title", "title", "data.name", "name"):
                    cur = assessment
                    ok = True
                    for part in pth.split("."):
                        if isinstance(cur, dict) and part in cur:
                            cur = cur[part]
                        else:
                            ok = False
                            break
                    if ok and isinstance(cur, str) and cur.strip():
                        title = cur.strip()
                        break
            # Use raw assessment ID if no title (for upload regex matching)
            assessment_title = safe_part(title, max_len=60) if title else aid

            for sub in submissions:
                ts = find_any_timestamp(sub)
                if ts is not None and ts < since:
                    continue

                student_name = safe_part(extract_student_name(sub), max_len=50)
                student_id = extract_student_id(sub)

                atts = extract_attachments(sub)
                if not atts:
                    ignored_no_files += 1
                    continue

                # Build a base prefix for filenames
                prefix = f"{class_name}__{assessment_title}__{student_name}__{student_id}"
                prefix = re.sub(r"\s+", " ", prefix).strip()

                # 1) Download PDF attachments directly
                pdf_atts = [a for a in atts if a["kind"] == "pdf"]
                for a in pdf_atts:
                    original = safe_part(a["filename"], max_len=90)
                    out_name = f"{prefix}__{original}"
                    if not out_name.lower().endswith(".pdf"):
                        out_name += ".pdf"
                    out_path = unique_path(DOWNLOAD_ROOT, out_name)

                    try:
                        download_url(a["url"], out_path)
                        downloaded_pdfs += 1
                        print(f"Downloaded PDF: {out_path.name}")
                    except Exception as e:
                        print(f"[WARN] PDF download failed: {a['url']} -> {e}")

                # 2) If no PDFs were submitted, but images were, combine images into one PDF
                if not pdf_atts:
                    image_atts = [a for a in atts if a["kind"] == "image"]
                    if image_atts:
                        tmp_dir = DOWNLOAD_ROOT / "_tmp_images"
                        tmp_dir.mkdir(parents=True, exist_ok=True)

                        # download images to temp
                        image_paths: list[pathlib.Path] = []
                        try:
                            for idx, a in enumerate(image_atts, start=1):
                                ext = pathlib.Path(a["filename"]).suffix.lower()
                                if ext not in IMAGE_EXTS:
                                    ext = ".jpg"
                                img_name = f"{prefix}__image_{idx:02d}{ext}"
                                img_path = unique_path(tmp_dir, img_name)
                                try:
                                    download_url(a["url"], img_path)
                                    image_paths.append(img_path)
                                except Exception as e:
                                    print(f"[WARN] Image download failed: {a['url']} -> {e}")

                            if image_paths:
                                out_pdf_name = f"{prefix}__images.pdf"
                                out_pdf_path = unique_path(DOWNLOAD_ROOT, out_pdf_name)
                                try:
                                    images_to_pdf(image_paths, out_pdf_path)
                                    created_image_pdfs += 1
                                    print(f"Created PDF from images: {out_pdf_path.name}")
                                except Exception as e:
                                    print(f"[WARN] Failed to create PDF from images -> {e}")
                        finally:
                            # Always clean up temp images
                            for p in image_paths:
                                try:
                                    p.unlink()
                                except Exception:
                                    pass

    print("\nDone.")
    print(f"PDFs downloaded: {downloaded_pdfs}")
    print(f"PDFs created from images: {created_image_pdfs}")
    print(f"Submissions ignored (no files): {ignored_no_files}")


if __name__ == "__main__":
    main()
