"""
Document Extractor - Batch Processing from Google Drive
Reads all files from a Drive folder, extracts data, saves to Google Sheets
"""

import streamlit as st
import anthropic
import json
import pandas as pd
import fitz  # PyMuPDF for PDF processing
from google.cloud import vision
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import gspread
from datetime import datetime
import io
import time

# Page configuration
st.set_page_config(
    page_title="Batch Document Extractor",
    page_icon="📁",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
    
    .stApp {
        font-family: 'Outfit', sans-serif;
    }
    
    .main-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 50%, #3d7ab5 100%);
        padding: 2rem;
        border-radius: 16px;
        margin-bottom: 2rem;
        text-align: center;
        box-shadow: 0 8px 32px rgba(30, 58, 95, 0.3);
    }
    
    .main-header h1 {
        color: white;
        font-size: 2.5rem;
        font-weight: 700;
        margin: 0;
    }
    
    .main-header p {
        color: #b8d4e8;
        font-size: 1.1rem;
        margin-top: 0.5rem;
    }
    
    .stat-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    
    .stat-number {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1e3a5f;
    }
    
    .stat-label {
        color: #64748b;
        font-size: 0.9rem;
    }
    
    .file-item {
        background: #f8fafc;
        padding: 0.75rem 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        border-left: 3px solid #3d7ab5;
    }
    
    .success-item {
        border-left-color: #22c55e;
    }
    
    .error-item {
        border-left-color: #ef4444;
    }
    
    .stButton > button {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
        color: white;
        border: none;
        padding: 0.75rem 2rem;
        font-size: 1.1rem;
        font-weight: 600;
        border-radius: 10px;
        width: 100%;
    }
    
    .footer {
        text-align: center;
        color: #94a3b8;
        padding: 2rem;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
<div class="main-header">
    <h1>📁 Batch Document Extractor</h1>
    <p>Process all files from Google Drive folder → Save to Google Sheets</p>
</div>
""", unsafe_allow_html=True)


def get_credentials(credentials_json):
    """Create credentials object with all required scopes."""
    credentials_dict = json.loads(credentials_json)
    credentials = service_account.Credentials.from_service_account_info(
        credentials_dict,
        scopes=[
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive.readonly',
            'https://www.googleapis.com/auth/cloud-vision'
        ]
    )
    return credentials


def get_drive_service(credentials):
    """Create Google Drive service."""
    return build('drive', 'v3', credentials=credentials)


def get_vision_client(credentials):
    """Create Google Vision client."""
    return vision.ImageAnnotatorClient(credentials=credentials)


def get_sheets_client(credentials):
    """Create Google Sheets client."""
    return gspread.authorize(credentials)


def list_files_in_folder(drive_service, folder_id):
    """List all supported files in a Google Drive folder."""
    supported_types = [
        'application/pdf',
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp'
    ]
    
    query = f"'{folder_id}' in parents and trashed = false"
    
    files = []
    page_token = None
    
    while True:
        response = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='nextPageToken, files(id, name, mimeType)',
            pageToken=page_token
        ).execute()
        
        for file in response.get('files', []):
            if file['mimeType'] in supported_types:
                files.append(file)
        
        page_token = response.get('nextPageToken')
        if not page_token:
            break
    
    return files


def download_file(drive_service, file_id):
    """Download file content from Google Drive."""
    request = drive_service.files().get_media(fileId=file_id)
    file_buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(file_buffer, request)
    
    done = False
    while not done:
        _, done = downloader.next_chunk()
    
    file_buffer.seek(0)
    return file_buffer.read()


def pdf_to_image(pdf_bytes):
    """Convert first page of PDF to image bytes."""
    try:
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = pdf_document[0]
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        pdf_document.close()
        return img_bytes
    except Exception as e:
        return None


def extract_text_with_vision(image_bytes, vision_client):
    """Extract text using Google Vision."""
    image = vision.Image(content=image_bytes)
    response = vision_client.document_text_detection(image=image)
    
    if response.error.message:
        raise Exception(response.error.message)
    
    return response.full_text_annotation.text


def parse_marksheet_with_claude(extracted_text, api_key):
    """Parse marksheet text with Claude."""
    client = anthropic.Anthropic(api_key=api_key)
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""Parse this marksheet text and extract marks. Return ONLY valid JSON:

{extracted_text}

Return this exact JSON structure:
{{
    "student_name": "Name",
    "roll_number": "Roll/Register number",
    "class": "Class/Semester",
    "school": "School/College name",
    "exam": "Exam name/Month Year",
    "subjects": [
        {{"subject_name": "Subject", "marks_obtained": number, "max_marks": number}}
    ],
    "total_marks_obtained": number,
    "total_max_marks": number,
    "percentage": number,
    "result": "PASS/FAIL"
}}

IMPORTANT: Use TOTAL column if CA/ESE/TOTAL exists. Extract ALL subjects. Never use 0 unless actually 0."""
        }]
    )
    
    return response.content[0].text


def parse_passbook_with_claude(extracted_text, api_key):
    """Parse passbook text with Claude."""
    client = anthropic.Anthropic(api_key=api_key)
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""Parse this bank passbook text. Return ONLY valid JSON:

{extracted_text}

Return this exact JSON structure:
{{
    "account_holder_name": "Name",
    "account_number": "Account number",
    "ifsc_code": "IFSC code",
    "micr_code": "MICR code",
    "customer_id": "Customer ID",
    "branch_name": "Branch name",
    "branch_address": "Address",
    "bank_name": "Bank name",
    "account_type": "Savings/Current"
}}"""
        }]
    )
    
    return response.content[0].text


def save_marksheet_to_sheets(sheets_client, spreadsheet_id, data, filename):
    """Save marksheet data to Google Sheets."""
    try:
        spreadsheet = sheets_client.open_by_key(spreadsheet_id)
        
        headers = [
            "Timestamp", "Filename", "Student Name", "Roll Number", "School/College",
            "Class/Semester", "Exam", "Total Marks", "Max Marks",
            "Percentage", "Result", "Subjects & Marks"
        ]
        
        try:
            worksheet = spreadsheet.worksheet("Marksheets")
            # Check if headers exist, if not add them
            first_row = worksheet.row_values(1)
            if not first_row or first_row[0] != "Timestamp":
                worksheet.insert_row(headers, 1)
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title="Marksheets", rows=1000, cols=20)
            worksheet.append_row(headers)
            # Format headers (bold)
            worksheet.format('A1:L1', {'textFormat': {'bold': True}})
        
        subjects_str = ""
        if data.get('subjects'):
            subjects_str = " | ".join([
                f"{s.get('subject_name', 'N/A')}: {s.get('marks_obtained', 0)}/{s.get('max_marks', 100)}"
                for s in data['subjects']
            ])
        
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            filename,
            data.get('student_name') or 'N/A',
            data.get('roll_number') or 'N/A',
            data.get('school') or 'N/A',
            data.get('class') or 'N/A',
            data.get('exam') or 'N/A',
            data.get('total_marks_obtained') or 0,
            data.get('total_max_marks') or 0,
            data.get('percentage') or 0,
            data.get('result') or 'N/A',
            subjects_str
        ]
        
        worksheet.append_row(row, value_input_option='USER_ENTERED')
        return True
        
    except Exception as e:
        return False


def save_passbook_to_sheets(sheets_client, spreadsheet_id, data, filename):
    """Save passbook data to Google Sheets."""
    try:
        spreadsheet = sheets_client.open_by_key(spreadsheet_id)
        
        headers = [
            "Timestamp", "Filename", "Account Holder", "Account Number", "Bank Name",
            "Branch Name", "IFSC Code", "MICR Code", "Customer ID",
            "Account Type", "Branch Address"
        ]
        
        try:
            worksheet = spreadsheet.worksheet("Passbooks")
            # Check if headers exist, if not add them
            first_row = worksheet.row_values(1)
            if not first_row or first_row[0] != "Timestamp":
                worksheet.insert_row(headers, 1)
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title="Passbooks", rows=1000, cols=15)
            worksheet.append_row(headers)
            # Format headers (bold)
            worksheet.format('A1:K1', {'textFormat': {'bold': True}})
        
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            filename,
            data.get('account_holder_name') or 'N/A',
            data.get('account_number') or 'N/A',
            data.get('bank_name') or 'N/A',
            data.get('branch_name') or 'N/A',
            data.get('ifsc_code') or 'N/A',
            data.get('micr_code') or 'N/A',
            data.get('customer_id') or 'N/A',
            data.get('account_type') or 'N/A',
            data.get('branch_address') or 'N/A'
        ]
        
        worksheet.append_row(row, value_input_option='USER_ENTERED')
        return True
        
    except Exception as e:
        return False


# Get secrets
def get_secret(key):
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return None


google_creds = get_secret("GOOGLE_CREDENTIALS")
anthropic_key = get_secret("ANTHROPIC_API_KEY")
spreadsheet_id = get_secret("GOOGLE_SPREADSHEET_ID")
default_folder_id = get_secret("GOOGLE_DRIVE_FOLDER_ID")

# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    
    if google_creds:
        st.success("✅ Google Cloud configured")
        credentials_json = google_creds
    else:
        credentials_file = st.file_uploader("Google Credentials JSON", type=['json'])
        credentials_json = credentials_file.getvalue().decode('utf-8') if credentials_file else None
    
    if anthropic_key:
        st.success("✅ Claude API configured")
        api_key = anthropic_key
    else:
        api_key = st.text_input("Anthropic API Key", type="password")
    
    if spreadsheet_id:
        st.success("✅ Spreadsheet configured")
        sheet_id = spreadsheet_id
    else:
        sheet_id = st.text_input("Google Spreadsheet ID")
    
    st.markdown("---")
    st.markdown("### 📊 Links")
    if sheet_id:
        st.markdown(f"[📊 Open Spreadsheet](https://docs.google.com/spreadsheets/d/{sheet_id})")
    
    st.markdown("---")
    st.markdown("### 💡 How to get Folder ID")
    st.markdown("""
    1. Open folder in Google Drive
    2. Copy ID from URL:
    `drive.google.com/drive/folders/`**`FOLDER_ID`**
    """)


# Main content
st.markdown("### 📁 Google Drive Folder")

col1, col2 = st.columns([3, 1])

with col1:
    folder_id = st.text_input(
        "Enter Google Drive Folder ID",
        value=default_folder_id or "",
        placeholder="1abc123xyz...",
        help="The folder ID from your Google Drive URL"
    )

with col2:
    doc_type = st.selectbox("Document Type", ["📚 Marksheets", "🏦 Passbooks"])

# Process button
if folder_id and credentials_json and api_key and sheet_id:
    
    # Initialize credentials and services
    try:
        credentials = get_credentials(credentials_json)
        drive_service = get_drive_service(credentials)
        vision_client = get_vision_client(credentials)
        sheets_client = get_sheets_client(credentials)
    except Exception as e:
        st.error(f"Failed to initialize services: {e}")
        st.stop()
    
    # List files
    with st.spinner("📂 Scanning folder..."):
        try:
            files = list_files_in_folder(drive_service, folder_id)
        except Exception as e:
            st.error(f"Could not access folder: {e}")
            st.error("Make sure the folder is shared with your service account email!")
            st.stop()
    
    if not files:
        st.warning("No supported files found in the folder (PDF, JPG, PNG, GIF, WEBP)")
    else:
        st.success(f"Found **{len(files)}** files to process")
        
        # Show file list
        with st.expander(f"📄 Files found ({len(files)})", expanded=True):
            for f in files:
                st.markdown(f"- {f['name']}")
        
        # Process button
        if st.button(f"🚀 Process All {len(files)} Files", use_container_width=True):
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            results_container = st.container()
            
            successful = 0
            failed = 0
            results = []
            
            for i, file in enumerate(files):
                filename = file['name']
                status_text.markdown(f"**Processing ({i+1}/{len(files)}):** {filename}")
                
                try:
                    # Download file
                    file_bytes = download_file(drive_service, file['id'])
                    
                    # Convert PDF to image if needed
                    if file['mimeType'] == 'application/pdf':
                        image_bytes = pdf_to_image(file_bytes)
                        if not image_bytes:
                            raise Exception("Could not convert PDF")
                    else:
                        image_bytes = file_bytes
                    
                    # Extract text with Vision
                    extracted_text = extract_text_with_vision(image_bytes, vision_client)
                    
                    # Parse with Claude
                    if "Marksheet" in doc_type:
                        result = parse_marksheet_with_claude(extracted_text, api_key)
                    else:
                        result = parse_passbook_with_claude(extracted_text, api_key)
                    
                    # Clean JSON
                    clean_result = result.strip()
                    if clean_result.startswith("```"):
                        clean_result = clean_result.split("\n", 1)[1] if "\n" in clean_result else clean_result[3:]
                    if clean_result.endswith("```"):
                        clean_result = clean_result[:-3]
                    clean_result = clean_result.strip()
                    
                    data = json.loads(clean_result)
                    
                    # Save to sheets
                    if "Marksheet" in doc_type:
                        save_marksheet_to_sheets(sheets_client, sheet_id, data, filename)
                        student_name = data.get('student_name', 'Unknown')
                    else:
                        save_passbook_to_sheets(sheets_client, sheet_id, data, filename)
                        student_name = data.get('account_holder_name', 'Unknown')
                    
                    successful += 1
                    results.append({"file": filename, "status": "✅", "name": student_name})
                    
                except Exception as e:
                    failed += 1
                    results.append({"file": filename, "status": "❌", "name": str(e)[:50]})
                
                # Update progress
                progress_bar.progress((i + 1) / len(files))
                
                # Small delay to avoid rate limits
                time.sleep(0.5)
            
            # Final status
            status_text.empty()
            progress_bar.empty()
            
            # Summary
            st.markdown("---")
            st.markdown("## 📊 Processing Complete!")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-number">{len(files)}</div>
                    <div class="stat-label">Total Files</div>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-number" style="color:#22c55e">{successful}</div>
                    <div class="stat-label">Successful</div>
                </div>
                """, unsafe_allow_html=True)
            
            with col3:
                st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-number" style="color:#ef4444">{failed}</div>
                    <div class="stat-label">Failed</div>
                </div>
                """, unsafe_allow_html=True)
            
            # Results table
            st.markdown("### 📋 Results")
            results_df = pd.DataFrame(results)
            results_df.columns = ['Filename', 'Status', 'Name/Error']
            st.dataframe(results_df, use_container_width=True, hide_index=True)
            
            # Link to spreadsheet
            st.markdown(f"### 📊 [Open Google Spreadsheet](https://docs.google.com/spreadsheets/d/{sheet_id})")

else:
    st.info("👆 Please configure all settings in the sidebar and enter a folder ID")
    
    st.markdown("### 📋 Setup Checklist")
    st.markdown(f"""
    - {'✅' if google_creds else '❌'} Google Cloud Credentials
    - {'✅' if anthropic_key else '❌'} Anthropic API Key  
    - {'✅' if sheet_id else '❌'} Google Spreadsheet ID
    - {'✅' if folder_id else '❌'} Google Drive Folder ID
    """)

# Footer
st.markdown("""
<div class="footer">
    <p>Built for Canada Nagarathar Sangam - Education Committee</p>
    <p style="font-size: 0.8rem;">Batch Processing: Drive → Vision → Claude → Sheets</p>
</div>
""", unsafe_allow_html=True)

