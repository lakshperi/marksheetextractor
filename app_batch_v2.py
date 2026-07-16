"""
Document Extractor - Multi Folder Batch Processing
Separate folders for Aug-Dec Marksheets, Jan-May Marksheets & Passbooks → Saves to different Sheet tabs
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
    
    .stApp { font-family: 'Outfit', sans-serif; }
    
    .main-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 50%, #3d7ab5 100%);
        padding: 2rem;
        border-radius: 16px;
        margin-bottom: 2rem;
        text-align: center;
        box-shadow: 0 8px 32px rgba(30, 58, 95, 0.3);
    }
    
    .main-header h1 { color: white; font-size: 2.2rem; font-weight: 700; margin: 0; }
    .main-header p { color: #b8d4e8; font-size: 1rem; margin-top: 0.5rem; }
    
    .folder-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        margin-bottom: 1rem;
    }
    
    .folder-card h3 { margin: 0 0 1rem 0; color: #1e3a5f; }
    
    .stat-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    
    .stat-number { font-size: 2rem; font-weight: 700; color: #1e3a5f; }
    .stat-label { color: #64748b; font-size: 0.9rem; }
    
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
    
    .success-text { color: #22c55e; }
    .error-text { color: #ef4444; }
    
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
    <p>Aug-Dec & Jan-May Marksheets + Passbooks → Auto-save to Google Sheets</p>
</div>
""", unsafe_allow_html=True)


# ============ HELPER FUNCTIONS ============

def get_credentials(credentials_json):
    """Create credentials object with all required scopes."""
    credentials_dict = json.loads(credentials_json)
    return service_account.Credentials.from_service_account_info(
        credentials_dict,
        scopes=[
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive.readonly',
            'https://www.googleapis.com/auth/cloud-vision'
        ]
    )


def get_drive_service(credentials):
    return build('drive', 'v3', credentials=credentials)


def get_vision_client(credentials):
    return vision.ImageAnnotatorClient(credentials=credentials)


def get_sheets_client(credentials):
    return gspread.authorize(credentials)


def list_files_in_folder(drive_service, folder_id):
    """List all supported files in a Google Drive folder (including Shared Drives)."""
    if not folder_id:
        return []
    
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
            pageToken=page_token,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True
        ).execute()
        
        for file in response.get('files', []):
            if file['mimeType'] in supported_types:
                files.append(file)
        
        page_token = response.get('nextPageToken')
        if not page_token:
            break
    
    return files


def download_file(drive_service, file_id):
    """Download file content from Google Drive (including Shared Drives)."""
    request = drive_service.files().get_media(fileId=file_id, supportsAllDrives=True)
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
    except:
        return None


def extract_text_with_vision(image_bytes, vision_client):
    """Extract text using Google Vision."""
    image = vision.Image(content=image_bytes)
    response = vision_client.document_text_detection(image=image)
    
    if response.error.message:
        raise Exception(response.error.message)
    
    return response.full_text_annotation.text


# ============ MARKSHEET FUNCTIONS ============

def parse_marksheet_with_claude(extracted_text, api_key):
    """Parse marksheet text with Claude."""
    client = anthropic.Anthropic(api_key=api_key)
    
    response = client.messages.create(
        model="claude-haiku-4-5",
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

IMPORTANT: Use TOTAL column if CA/ESE/TOTAL exists. Extract ALL subjects with full names. Never use 0 unless actually 0."""
        }]
    )
    
    return response.content[0].text


def save_marksheet_to_sheets(sheets_client, spreadsheet_id, data, filename, tab_name="Marksheets"):
    """Save marksheet data to Google Sheets. Raises exception on failure."""
    spreadsheet = sheets_client.open_by_key(spreadsheet_id)
    
    headers = [
        "Timestamp", "Filename", "Student Name", "Roll Number", "School/College",
        "Class/Semester", "Exam", "Total Marks", "Max Marks",
        "Percentage", "Result", "Subjects & Marks"
    ]
    
    try:
        worksheet = spreadsheet.worksheet(tab_name)
        first_row = worksheet.row_values(1)
        if not first_row or first_row[0] != "Timestamp":
            worksheet.insert_row(headers, 1)
            worksheet.format('A1:L1', {'textFormat': {'bold': True}})
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=20)
        worksheet.append_row(headers)
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
    st.success(f"✅ Saved to tab: **{tab_name}**")


# ============ PASSBOOK FUNCTIONS ============

def parse_passbook_with_claude(extracted_text, api_key):
    """Parse passbook text with Claude."""
    client = anthropic.Anthropic(api_key=api_key)
    
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""Parse this bank passbook text. Return ONLY valid JSON:

{extracted_text}

Return this exact JSON structure:
{{
    "account_holder_name": "Name",
    "account_number": "Account number",
    "ifsc_code": "IFSC code (11 chars, starts with 4 letters)",
    "micr_code": "MICR code (9 digits)",
    "customer_id": "Customer ID/CIF number",
    "branch_name": "Branch name",
    "branch_address": "Full address",
    "bank_name": "Bank name",
    "account_type": "Savings/Current"
}}

Look carefully for IFSC (like SBIN0001234), MICR (9 digits), account numbers."""
        }]
    )
    
    return response.content[0].text


def save_passbook_to_sheets(sheets_client, spreadsheet_id, data, filename):
    """Save passbook data to Google Sheets. Raises exception on failure."""
    spreadsheet = sheets_client.open_by_key(spreadsheet_id)
    
    headers = [
        "Timestamp", "Filename", "Account Holder", "Account Number", "Bank Name",
        "Branch Name", "IFSC Code", "MICR Code", "Customer ID",
        "Account Type", "Branch Address"
    ]
    
    try:
        worksheet = spreadsheet.worksheet("Passbooks")
        first_row = worksheet.row_values(1)
        if not first_row or first_row[0] != "Timestamp":
            worksheet.insert_row(headers, 1)
            worksheet.format('A1:K1', {'textFormat': {'bold': True}})
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title="Passbooks", rows=1000, cols=15)
        worksheet.append_row(headers)
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


# ============ TRACKING PROCESSED FILES ============

def get_processed_file_ids(sheets_client, spreadsheet_id):
    """Get list of already processed file IDs from tracking sheet."""
    try:
        spreadsheet = sheets_client.open_by_key(spreadsheet_id)
        
        try:
            tracking_sheet = spreadsheet.worksheet("_ProcessedFiles")
            # Get all file IDs from column A (skip header)
            file_ids = tracking_sheet.col_values(1)[1:]  # Skip header row
            return set(file_ids)
        except gspread.WorksheetNotFound:
            # Create tracking sheet if it doesn't exist
            tracking_sheet = spreadsheet.add_worksheet(title="_ProcessedFiles", rows=5000, cols=4)
            tracking_sheet.append_row(["File ID", "Filename", "Document Type", "Processed At"])
            tracking_sheet.format('A1:D1', {'textFormat': {'bold': True}})
            return set()
    except Exception as e:
        st.warning(f"Could not access tracking sheet: {e}")
        return set()


def mark_file_as_processed(sheets_client, spreadsheet_id, file_id, filename, doc_type):
    """Mark a file as processed in the tracking sheet."""
    try:
        spreadsheet = sheets_client.open_by_key(spreadsheet_id)
        
        try:
            tracking_sheet = spreadsheet.worksheet("_ProcessedFiles")
        except gspread.WorksheetNotFound:
            tracking_sheet = spreadsheet.add_worksheet(title="_ProcessedFiles", rows=5000, cols=4)
            tracking_sheet.append_row(["File ID", "Filename", "Document Type", "Processed At"])
        
        row = [
            file_id,
            filename,
            doc_type,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ]
        tracking_sheet.append_row(row)
        return True
    except Exception as e:
        return False


def filter_new_files(files, processed_ids):
    """Filter out already processed files."""
    new_files = [f for f in files if f['id'] not in processed_ids]
    skipped = len(files) - len(new_files)
    return new_files, skipped


# ============ BATCH PROCESSING ============

def process_batch(files, doc_type, drive_service, vision_client, sheets_client, 
                  api_key, sheet_id, progress_bar, status_text, tab_name=None):
    """Process a batch of files."""
    successful = 0
    failed = 0
    results = []
    
    for i, file in enumerate(files):
        filename = file['name']
        file_id = file['id']
        status_text.markdown(f"**Processing ({i+1}/{len(files)}):** {filename}")
        
        try:
            file_bytes = download_file(drive_service, file['id'])
            
            if file['mimeType'] == 'application/pdf':
                image_bytes = pdf_to_image(file_bytes)
                if not image_bytes:
                    raise Exception("Could not convert PDF")
            else:
                image_bytes = file_bytes
            
            extracted_text = extract_text_with_vision(image_bytes, vision_client)
            
            if doc_type == "marksheet":
                result = parse_marksheet_with_claude(extracted_text, api_key)
            else:
                result = parse_passbook_with_claude(extracted_text, api_key)
            
            clean_result = result.strip()
            if clean_result.startswith("```"):
                clean_result = clean_result.split("\n", 1)[1] if "\n" in clean_result else clean_result[3:]
            if clean_result.endswith("```"):
                clean_result = clean_result[:-3]
            clean_result = clean_result.strip()
            
            data = json.loads(clean_result)
            
            if doc_type == "marksheet":
                save_marksheet_to_sheets(sheets_client, sheet_id, data, filename, tab_name or "Marksheets")
                name = data.get('student_name', 'Unknown')
            else:
                save_passbook_to_sheets(sheets_client, sheet_id, data, filename)
                name = data.get('account_holder_name', 'Unknown')
            
            mark_file_as_processed(sheets_client, sheet_id, file_id, filename, doc_type)
            
            successful += 1
            results.append({"file": filename, "status": "✅", "name": name})
            
        except Exception as e:
            failed += 1
            results.append({"file": filename, "status": "❌", "name": str(e)[:50]})
        
        progress_bar.progress((i + 1) / len(files))
        time.sleep(0.5)
    
    return successful, failed, results


# ============ GET SECRETS ============

def get_secret(key):
    try:
        return st.secrets[key]
    except:
        return None


google_creds = get_secret("GOOGLE_CREDENTIALS")
anthropic_key = get_secret("ANTHROPIC_API_KEY")
spreadsheet_id = get_secret("GOOGLE_SPREADSHEET_ID")
marksheet_folder = get_secret("MARKSHEET_FOLDER_ID_AUG_DEC")
marksheet_folder_jan_may = get_secret("MARKSHEET_FOLDER_ID_JAN_MAY")
passbook_folder = get_secret("PASSBOOK_FOLDER_ID")


# ============ SIDEBAR ============

with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    
    if google_creds:
        st.success("✅ Google Cloud")
        credentials_json = google_creds
    else:
        credentials_file = st.file_uploader("Google Credentials JSON", type=['json'])
        credentials_json = credentials_file.getvalue().decode('utf-8') if credentials_file else None
    
    if anthropic_key:
        st.success("✅ Claude API")
        api_key = anthropic_key
    else:
        api_key = st.text_input("Anthropic API Key", type="password")
    
    if spreadsheet_id:
        st.success("✅ Spreadsheet")
        sheet_id = spreadsheet_id
    else:
        sheet_id = st.text_input("Google Spreadsheet ID")
    
    st.markdown("---")
    if sheet_id:
        st.markdown(f"[📊 Open Spreadsheet](https://docs.google.com/spreadsheets/d/{sheet_id})")
    
    st.markdown("---")
    st.markdown("### 💡 Folder ID")
    st.markdown("Get from URL: `drive.google.com/drive/folders/`**`ID`**")


# ============ MAIN CONTENT ============

# Initialize services
services_ready = False
if credentials_json and api_key and sheet_id:
    try:
        credentials = get_credentials(credentials_json)
        drive_service = get_drive_service(credentials)
        vision_client = get_vision_client(credentials)
        sheets_client = get_sheets_client(credentials)
        services_ready = True
    except Exception as e:
        st.error(f"Failed to initialize: {e}")

if not services_ready:
    st.warning("⚠️ Please configure all settings in the sidebar")
    st.stop()


# Get already processed files
processed_ids = get_processed_file_ids(sheets_client, sheet_id)
st.sidebar.markdown(f"**📊 Already processed:** {len(processed_ids)} files")

# Helper to list and cache files in session state
def list_and_cache_files(folder_id, cache_key, processed_ids):
    """List files from Drive and cache in session state to survive reruns."""
    files = []
    new_files = []
    skipped = 0
    
    if not folder_id:
        return files, new_files, skipped
    
    try:
        all_files = list_files_in_folder(drive_service, folder_id)
        if all_files:
            new_files, skipped = filter_new_files(all_files, processed_ids)
            files = new_files
            st.session_state[cache_key] = files
        else:
            st.session_state[cache_key] = []
    except Exception as e:
        st.error(f"Error listing files: {e}")
        files = st.session_state.get(cache_key, [])
        new_files = files
    
    return files, new_files, skipped


# Three columns for the three folder types
col1, col2, col3 = st.columns(3)

# ============ AUG-DEC MARKSHEETS SECTION ============
with col1:
    st.markdown("""
    <div class="folder-card">
        <h3>📚 Aug - Dec Marksheets</h3>
    </div>
    """, unsafe_allow_html=True)
    
    marksheet_folder_id = st.text_input(
        "Aug-Dec Folder ID",
        value=marksheet_folder or "",
        placeholder="Enter folder ID...",
        key="marksheet_folder"
    )
    
    marksheet_files, marksheet_new_files, marksheet_skipped = list_and_cache_files(
        marksheet_folder_id, '_cache_marksheet_files', processed_ids
    )
    
    if marksheet_folder_id:
        if marksheet_new_files:
            st.success(f"**{len(marksheet_new_files)}** new files to process")
            if marksheet_skipped > 0:
                st.info(f"⏭️ Skipping {marksheet_skipped} already processed")
            with st.expander(f"View new files ({len(marksheet_new_files)})"):
                for f in marksheet_new_files:
                    st.markdown(f"- {f['name']}")
        elif not marksheet_files:
            st.info("No files found in folder")
    
    process_marksheets = st.button("🚀 Process Aug-Dec", key="btn_marksheets", 
                                    disabled=not marksheet_files, use_container_width=True)


# ============ JAN-MAY MARKSHEETS SECTION ============
with col2:
    st.markdown("""
    <div class="folder-card">
        <h3>📚 Jan - May Marksheets</h3>
    </div>
    """, unsafe_allow_html=True)
    
    marksheet_jm_folder_id = st.text_input(
        "Jan-May Folder ID",
        value=marksheet_folder_jan_may or "",
        placeholder="Enter folder ID...",
        key="marksheet_folder_jan_may"
    )
    
    marksheet_jm_files, marksheet_jm_new_files, marksheet_jm_skipped = list_and_cache_files(
        marksheet_jm_folder_id, '_cache_marksheet_jm_files', processed_ids
    )
    
    if marksheet_jm_folder_id:
        if marksheet_jm_new_files:
            st.success(f"**{len(marksheet_jm_new_files)}** new files to process")
            if marksheet_jm_skipped > 0:
                st.info(f"⏭️ Skipping {marksheet_jm_skipped} already processed")
            with st.expander(f"View new files ({len(marksheet_jm_new_files)})"):
                for f in marksheet_jm_new_files:
                    st.markdown(f"- {f['name']}")
        elif not marksheet_jm_files:
            st.info("No files found in folder")
    
    process_marksheets_jm = st.button("🚀 Process Jan-May", key="btn_marksheets_jm",
                                       disabled=not marksheet_jm_files, use_container_width=True)


# ============ PASSBOOKS SECTION ============
with col3:
    st.markdown("""
    <div class="folder-card">
        <h3>🏦 Passbooks</h3>
    </div>
    """, unsafe_allow_html=True)
    
    passbook_folder_id = st.text_input(
        "Passbooks Folder ID",
        value=passbook_folder or "",
        placeholder="Enter folder ID...",
        key="passbook_folder"
    )
    
    passbook_files, passbook_new_files, passbook_skipped = list_and_cache_files(
        passbook_folder_id, '_cache_passbook_files', processed_ids
    )
    
    if passbook_folder_id:
        if passbook_new_files:
            st.success(f"**{len(passbook_new_files)}** new files to process")
            if passbook_skipped > 0:
                st.info(f"⏭️ Skipping {passbook_skipped} already processed")
            with st.expander(f"View new files ({len(passbook_new_files)})"):
                for f in passbook_new_files:
                    st.markdown(f"- {f['name']}")
        elif not passbook_files:
            st.info("No files found in folder")
    
    process_passbooks = st.button("🚀 Process Passbooks", key="btn_passbooks",
                                   disabled=not passbook_files, use_container_width=True)


# ============ PROCESS ALL BUTTON ============
st.markdown("---")

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    process_all = st.button("🚀 Process ALL Documents", 
                            disabled=not (marksheet_files or marksheet_jm_files or passbook_files),
                            use_container_width=True)


# ============ PROCESSING LOGIC ============

def show_results(doc_type, successful, failed, results):
    """Display processing results."""
    st.markdown(f"### {'📚 Marksheets' if doc_type == 'marksheet' else '🏦 Passbooks'} Results")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"<p class='success-text'>✅ Successful: {successful}</p>", unsafe_allow_html=True)
    with col2:
        st.markdown(f"<p class='error-text'>❌ Failed: {failed}</p>", unsafe_allow_html=True)
    
    if results:
        df = pd.DataFrame(results)
        df.columns = ['Filename', 'Status', 'Name/Error']
        st.dataframe(df, use_container_width=True, hide_index=True)


# Process Aug-Dec Marksheets Only
if process_marksheets and marksheet_files:
    st.markdown("---")
    st.markdown("## Processing Aug-Dec Marksheets...")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    successful, failed, results = process_batch(
        marksheet_files, "marksheet", drive_service, vision_client, 
        sheets_client, api_key, sheet_id, progress_bar, status_text,
        tab_name="Marksheets Aug-Dec"
    )
    
    status_text.empty()
    progress_bar.empty()
    
    show_results("marksheet", successful, failed, results)
    st.markdown(f"[📊 Open Spreadsheet](https://docs.google.com/spreadsheets/d/{sheet_id})")


# Process Jan-May Marksheets Only
if process_marksheets_jm and marksheet_jm_files:
    st.markdown("---")
    st.markdown("## Processing Jan-May Marksheets...")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    successful, failed, results = process_batch(
        marksheet_jm_files, "marksheet", drive_service, vision_client,
        sheets_client, api_key, sheet_id, progress_bar, status_text,
        tab_name="Marksheets Jan-May"
    )
    
    status_text.empty()
    progress_bar.empty()
    
    show_results("marksheet", successful, failed, results)
    st.markdown(f"[📊 Open Spreadsheet](https://docs.google.com/spreadsheets/d/{sheet_id})")


# Process Passbooks Only
if process_passbooks and passbook_files:
    st.markdown("---")
    st.markdown("## Processing Passbooks...")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    successful, failed, results = process_batch(
        passbook_files, "passbook", drive_service, vision_client,
        sheets_client, api_key, sheet_id, progress_bar, status_text
    )
    
    status_text.empty()
    progress_bar.empty()
    
    show_results("passbook", successful, failed, results)
    st.markdown(f"[📊 Open Spreadsheet](https://docs.google.com/spreadsheets/d/{sheet_id})")


# Process All
if process_all:
    st.markdown("---")
    
    total_successful = 0
    total_failed = 0
    
    st.info(f"**Debug:** Aug-Dec files: {len(marksheet_files)} | Jan-May files: {len(marksheet_jm_files)} | Passbook files: {len(passbook_files)}")
    
    # Process Aug-Dec Marksheets
    if marksheet_files:
        st.markdown("## 📚 Processing Aug-Dec Marksheets...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        successful, failed, results = process_batch(
            marksheet_files, "marksheet", drive_service, vision_client,
            sheets_client, api_key, sheet_id, progress_bar, status_text,
            tab_name="Marksheets Aug-Dec"
        )
        
        status_text.empty()
        progress_bar.empty()
        show_results("marksheet", successful, failed, results)
        
        total_successful += successful
        total_failed += failed
    
    # Process Jan-May Marksheets
    if marksheet_jm_files:
        st.markdown("## 📚 Processing Jan-May Marksheets...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        successful, failed, results = process_batch(
            marksheet_jm_files, "marksheet", drive_service, vision_client,
            sheets_client, api_key, sheet_id, progress_bar, status_text,
            tab_name="Marksheets Jan-May"
        )
        
        status_text.empty()
        progress_bar.empty()
        show_results("marksheet", successful, failed, results)
        
        total_successful += successful
        total_failed += failed
    else:
        st.warning("⚠️ Jan-May marksheet file list is empty - nothing to process")
    
    # Process Passbooks
    if passbook_files:
        st.markdown("## 🏦 Processing Passbooks...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        successful, failed, results = process_batch(
            passbook_files, "passbook", drive_service, vision_client,
            sheets_client, api_key, sheet_id, progress_bar, status_text
        )
        
        status_text.empty()
        progress_bar.empty()
        show_results("passbook", successful, failed, results)
        
        total_successful += successful
        total_failed += failed
    
    # Final Summary
    st.markdown("---")
    st.markdown("## 🎉 All Processing Complete!")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{len(marksheet_files) + len(marksheet_jm_files) + len(passbook_files)}</div>
            <div class="stat-label">Total Files</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number" style="color:#22c55e">{total_successful}</div>
            <div class="stat-label">Successful</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number" style="color:#ef4444">{total_failed}</div>
            <div class="stat-label">Failed</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown(f"### [📊 Open Google Spreadsheet](https://docs.google.com/spreadsheets/d/{sheet_id})")


# Footer
st.markdown("""
<div class="footer">
    <p>Built for Canada Nagarathar Sangam - Education Committee</p>
    <p style="font-size: 0.8rem;">Aug-Dec → "Marksheets Aug-Dec" tab | Jan-May → "Marksheets Jan-May" tab | Passbooks → "Passbooks" tab</p>
</div>
""", unsafe_allow_html=True)

