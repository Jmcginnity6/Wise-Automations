import streamlit as st
import subprocess
import pathlib
import sys
import os

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
    """
    Load credentials from Streamlit secrets (cloud) or .env (local).
    Returns True if all required variables are set.
    """
    # Try Streamlit secrets first (for cloud deployment)
    try:
        for key in REQUIRED_ENV_VARS:
            if key in st.secrets:
                os.environ[key] = st.secrets[key]
    except Exception:
        pass

    # Fall back to .env file (for local development)
    env_path = ROOT / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)

    # Check if all required variables are set
    missing = [k for k in REQUIRED_ENV_VARS if not os.environ.get(k)]
    return len(missing) == 0


def get_missing_credentials() -> list[str]:
    """Return list of missing credential names."""
    return [k for k in REQUIRED_ENV_VARS if not os.environ.get(k)]


# ----------------------------
# Helper Functions
# ----------------------------
def get_download_folders() -> list[pathlib.Path]:
    """Get all download folders sorted by date (newest first)."""
    if not DOWNLOADS_DIR.exists():
        return []
    folders = sorted(DOWNLOADS_DIR.glob("Downloaded_*"), reverse=True)
    return folders


def get_latest_download_folder() -> pathlib.Path | None:
    """Get the most recent download folder."""
    folders = get_download_folders()
    return folders[0] if folders else None


def count_marked_files(folder: pathlib.Path) -> int:
    """Count files ending with ' Marked.pdf' in folder."""
    if not folder or not folder.exists():
        return 0
    return len(list(folder.glob("*Marked.pdf")))


def count_total_files(folder: pathlib.Path) -> int:
    """Count all PDF files in folder (excluding temp)."""
    if not folder or not folder.exists():
        return 0
    return len([f for f in folder.glob("*.pdf") if not f.name.startswith("_")])


def run_script(script_name: str, args: list[str] | None = None):
    """Run a Python script and display output in real-time."""
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
        # Show last 50 lines to keep it readable
        output_box.code("\n".join(lines[-50:]), language="text")

    proc.wait()

    if proc.returncode == 0:
        st.success(f"{script_name} completed successfully!")
        return True
    else:
        st.error(f"{script_name} failed (exit code {proc.returncode})")
        return False


# ----------------------------
# Main App
# ----------------------------
def main():
    st.title("📝 Wise Marker App")
    st.write("Download student submissions, mark them, then upload feedback.")

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

    # Workflow instructions
    with st.expander("📋 How to use this app", expanded=False):
        st.markdown("""
        1. **Download** - Click to download all submissions from the last 7 days
        2. **Mark** - Open the PDFs, add your feedback, save as `filename Marked.pdf`
        3. **Upload** - Click to upload all marked files back to Wise

        **Important:** When saving marked files, add ` Marked` before `.pdf`
        - Example: `Test.pdf` → `Test Marked.pdf`
        """)

    st.divider()

    # Two-column layout for actions
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("⬇️ Download")
        if st.button("Download Last 7 Days", use_container_width=True, type="primary"):
            with st.spinner("Downloading submissions..."):
                run_script("main.py")

    with col2:
        st.subheader("⬆️ Upload")
        latest_folder = get_latest_download_folder()

        if latest_folder:
            marked_count = count_marked_files(latest_folder)
            total_count = count_total_files(latest_folder)

            st.caption(f"Folder: `{latest_folder.name}`")
            st.caption(f"Files: {marked_count} marked / {total_count} total")

            if marked_count == 0:
                st.warning("No marked files found yet.")

            if st.button("Upload Marked Files", use_container_width=True, disabled=(marked_count == 0)):
                with st.spinner("Uploading marked files..."):
                    run_script("upload_marked.py", [str(latest_folder)])
        else:
            st.info("No downloads yet. Download submissions first.")
            st.button("Upload Marked Files", use_container_width=True, disabled=True)

    st.divider()

    # Download folder info
    st.subheader("📁 Download Folders")

    folders = get_download_folders()
    if folders:
        for folder in folders[:5]:  # Show last 5 folders
            total = count_total_files(folder)
            marked = count_marked_files(folder)

            col_name, col_stats = st.columns([3, 1])
            with col_name:
                st.text(folder.name)
            with col_stats:
                if marked > 0:
                    st.text(f"✅ {marked}/{total}")
                else:
                    st.text(f"📄 {total}")

        st.caption(f"Location: `{DOWNLOADS_DIR}`")
    else:
        st.info("No downloads yet.")


if __name__ == "__main__":
    main()
