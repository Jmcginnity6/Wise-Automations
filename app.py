import streamlit as st
import subprocess
import pathlib
import sys
import os
import io
import zipfile
import tempfile

from dotenv import load_dotenv

# ----------------------------
# Configuration
# ----------------------------
st.set_page_config(
    page_title="Wise Marker App",
    page_icon="📝",
    layout="centered",
)

ROOT = pathlib.Path(__file__).resolve().parent
DOWNLOADS_DIR = ROOT / "downloads"

REQUIRED_ENV_VARS = [
    "WISE_API_KEY",
    "WISE_NAMESPACE",
    "WISE_INSTITUTE_ID",
    "WISE_BASIC_USER",
    "WISE_BASIC_PASS",
]


# ----------------------------
# Credential Loading
# ----------------------------
def load_credentials() -> bool:
    try:
        for key in REQUIRED_ENV_VARS:
            if key in st.secrets:
                os.environ[key] = st.secrets[key]
    except Exception:
        pass

    env_path = ROOT / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)

    missing = [k for k in REQUIRED_ENV_VARS if not os.environ.get(k)]
    return len(missing) == 0


def get_missing_credentials() -> list[str]:
    return [k for k in REQUIRED_ENV_VARS if not os.environ.get(k)]


# ----------------------------
# Helper Functions
# ----------------------------
def get_download_folders() -> list[pathlib.Path]:
    if not DOWNLOADS_DIR.exists():
        return []
    return sorted(DOWNLOADS_DIR.glob("Downloaded_*"), reverse=True)


def get_latest_download_folder() -> pathlib.Path | None:
    folders = get_download_folders()
    return folders[0] if folders else None


def get_pdf_files(folder: pathlib.Path) -> list[pathlib.Path]:
    """Get all non-marked PDFs in folder."""
    if not folder or not folder.exists():
        return []
    return [f for f in folder.glob("*.pdf") if not f.name.startswith("_") and "Marked" not in f.name]


def make_zip(folder: pathlib.Path) -> bytes:
    """Zip all PDFs in folder and return as bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for pdf in folder.glob("*.pdf"):
            if not pdf.name.startswith("_"):
                zf.write(pdf, pdf.name)
    return buf.getvalue()


def run_script(script_name: str, args: list[str] | None = None) -> bool:
    script_path = ROOT / script_name
    if not script_path.exists():
        st.error(f"Script not found: {script_name}")
        return False

    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args)

    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    output_box = st.empty()
    lines = []
    for line in proc.stdout:
        lines.append(line.rstrip())
        output_box.code("\n".join(lines[-50:]), language="text")

    proc.wait()

    if proc.returncode == 0:
        st.success("Done!")
        return True
    else:
        st.error(f"Failed (exit code {proc.returncode})")
        return False


# ----------------------------
# Main App
# ----------------------------
def main():
    st.title("📝 Wise Marker App")
    st.write("Download student submissions, mark them on your iPad, then upload feedback.")

    # Load and check credentials
    if not load_credentials():
        missing = get_missing_credentials()
        st.error("⚠️ Missing API Credentials")
        st.write("The following credentials are not configured:")
        for key in missing:
            st.write(f"  - `{key}`")
        st.info(
            "**For local use:** Create a `.env` file in the app folder.\n\n"
            "**For Streamlit Cloud:** Add these to your app secrets."
        )
        return

    # Workflow instructions - expanded by default
    with st.expander("📋 How to use this app", expanded=True):
        st.markdown("""
        #### Step 1 — Download Submissions
        Click **Download Last 7 Days** to fetch all student submissions from Wise.
        Once complete, click **Download ZIP** to save all the PDFs to your device.

        #### Step 2 — Mark on Your iPad
        1. Open the ZIP file and extract the PDFs
        2. Open each PDF in an annotation app (e.g. **GoodNotes**, **Notability**, or **PDF Expert**)
        3. Add your written feedback
        4. Export/save each marked file — **the filename must end with ` Marked.pdf`**

        > **Example:** `M2 Maths Class__Test 3__Kerry Irvine__...pdf`
        > becomes → `M2 Maths Class__Test 3__Kerry Irvine__... Marked.pdf`

        #### Step 3 — Upload Marked Files
        Use the **Upload Marked PDFs** section below to select all your marked files.
        The app will send them directly to Wise as student feedback.
        """)

    st.divider()

    # ---- STEP 1: DOWNLOAD ----
    st.subheader("Step 1 — Download Submissions")

    if st.button("Download Last 7 Days", use_container_width=True, type="primary"):
        with st.spinner("Fetching submissions from Wise..."):
            run_script("main.py")
        st.rerun()

    latest_folder = get_latest_download_folder()
    if latest_folder:
        pdfs = get_pdf_files(latest_folder)
        st.caption(f"Latest folder: **{latest_folder.name}** — {len(pdfs)} file(s)")

        if pdfs:
            zip_bytes = make_zip(latest_folder)
            st.download_button(
                label=f"Download ZIP ({len(pdfs)} PDFs)",
                data=zip_bytes,
                file_name=f"{latest_folder.name}.zip",
                mime="application/zip",
                use_container_width=True,
            )
        else:
            st.info("No submissions found in the latest folder. Try downloading again.")

    st.divider()

    # ---- STEP 2 label (instructions only, done on iPad) ----
    st.subheader("Step 2 — Mark on Your iPad")
    st.write("Extract the ZIP, annotate each PDF, and save with ` Marked.pdf` at the end of the filename.")

    st.divider()

    # ---- STEP 3: UPLOAD ----
    st.subheader("Step 3 — Upload Marked Files")
    st.write("Select all your marked PDFs to upload them as feedback on Wise.")

    uploaded_files = st.file_uploader(
        "Choose marked PDF files",
        type=["pdf"],
        accept_multiple_files=True,
        help="Select all files ending in ' Marked.pdf'",
    )

    if uploaded_files:
        # Check naming
        bad_names = [f.name for f in uploaded_files if not f.name.lower().endswith(" marked.pdf")]
        if bad_names:
            st.warning(
                f"{len(bad_names)} file(s) don't end with ` Marked.pdf` and will be skipped:\n"
                + "\n".join(f"- {n}" for n in bad_names)
            )

        good_files = [f for f in uploaded_files if f.name.lower().endswith(" marked.pdf")]
        st.write(f"Ready to upload: **{len(good_files)}** marked file(s)")

        if good_files and st.button("Upload to Wise", use_container_width=True, type="primary"):
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = pathlib.Path(tmp_dir)

                # Save uploaded files to temp folder
                for uf in good_files:
                    (tmp_path / uf.name).write_bytes(uf.read())

                with st.spinner(f"Uploading {len(good_files)} file(s) to Wise..."):
                    run_script("upload_marked.py", [str(tmp_path)])
    else:
        st.info("No files selected yet.")


if __name__ == "__main__":
    main()
