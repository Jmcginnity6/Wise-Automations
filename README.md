# Wise Marker App

A Streamlit app for JMCG Maths Mentors to download student submissions from Wise, mark them, and upload feedback.

## Features

- Download all submissions from the last 7 days
- Automatic PDF conversion for image submissions
- Upload marked PDFs back to Wise as feedback
- Progress tracking for marked files

## Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file with your credentials:
   ```
   WISE_API_KEY=your-api-key
   WISE_NAMESPACE=your-namespace
   WISE_INSTITUTE_ID=your-institute-id
   WISE_BASIC_USER=your-username
   WISE_BASIC_PASS=your-password
   ```

3. Run the app:
   ```bash
   streamlit run app.py
   ```

## Deploy to Streamlit Cloud (Get a Shareable URL)

### Step 1: Push to GitHub

Make sure your code is pushed to GitHub. The `.gitignore` file will prevent your `.env` file from being uploaded.

```bash
git add .
git commit -m "Ready for deployment"
git push
```

### Step 2: Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with your GitHub account
3. Click **"New app"**
4. Select your repository: `JMCGMathsMentorsSubmissionAutomations`
5. Set the main file path: `Wise Automations/app.py`
6. Click **"Deploy"**

### Step 3: Add Secrets

1. Once deployed, click the **"Settings"** gear icon
2. Go to **"Secrets"** section
3. Add your credentials in TOML format:

```toml
WISE_API_KEY = "your-api-key"
WISE_NAMESPACE = "your-namespace"
WISE_INSTITUTE_ID = "your-institute-id"
WISE_BASIC_USER = "your-username"
WISE_BASIC_PASS = "your-password"
```

4. Click **"Save"**

### Step 4: Share with Mentors

Your app will be available at a URL like:
```
https://your-app-name.streamlit.app
```

Share this URL with your mentors!

## Workflow

1. **Download** - Click to download all submissions from the last 7 days
2. **Mark** - Open the PDFs locally, add feedback, save as `filename Marked.pdf`
3. **Upload** - Click to upload all marked files back to Wise

### Important: File Naming

When saving marked files, add ` Marked` (with a space) before `.pdf`:
- `Test.pdf` → `Test Marked.pdf`
- `Homework.pdf` → `Homework Marked.pdf`

## File Structure

```
Wise Automations/
├── app.py              # Streamlit web interface
├── main.py             # Download script
├── upload_marked.py    # Upload script
├── requirements.txt    # Python dependencies
├── .env                # Local credentials (not in git)
├── .gitignore          # Git ignore rules
├── .streamlit/
│   └── secrets.toml.example  # Template for cloud secrets
└── downloads/          # Downloaded submissions (not in git)
```
