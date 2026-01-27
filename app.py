import streamlit as st
import subprocess
import pathlib
import sys
import os

st.set_page_config(page_title="Wise Marker App", page_icon="✅", layout="centered")

st.title("Wise Marker App")
st.write("Download submissions, mark them, then upload the marked files back to Wise.")

root = pathlib.Path(__file__).resolve().parent
downloads_dir = root / "downloads"

st.info("Workflow:\n1) Click **Download last week**\n2) Mark files (save as `... Marked.pdf`)\n3) Click **Upload Marked**")

col1, col2 = st.columns(2)

def run_script(script_name: str):
    script_path = root / script_name
    if not script_path.exists():
        st.error(f"Missing {script_name} in this folder.")
        return

    st.write(f"Running `{script_name}`…")
    proc = subprocess.Popen(
        [sys.executable, str(script_path)],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    output_box = st.empty()
    lines = []
    for line in proc.stdout:
        lines.append(line.rstrip())
        output_box.code("\n".join(lines[-200:]))  # show last 200 lines

    proc.wait()
    if proc.returncode == 0:
        st.success(f"{script_name} finished.")
    else:
        st.error(f"{script_name} failed (exit code {proc.returncode}).")

with col1:
    if st.button("⬇️ Download last week", use_container_width=True):
        run_script("main.py")

with col2:
    if st.button("⬆️ Upload Marked", use_container_width=True):
        run_script("upload_marked.py")

st.divider()

st.subheader("Where files are saved")
st.write(f"`{downloads_dir}`")

if downloads_dir.exists():
    latest = sorted(downloads_dir.glob("Downloaded_*"), reverse=True)
    if latest:
        st.write("Latest download folder:")
        st.code(str(latest[0]))
        st.write("Tip: Mark files by adding ` Marked` before `.pdf` (example: `Test.pdf` → `Test Marked.pdf`).")
else:
    st.write("No downloads yet.")
