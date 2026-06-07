"""
Document Extractor - Dual Folder Batch Processing
Separate folders for Marksheets & Passbooks → Saves to different Sheet tabs
Skips already-processed files and watermarks new files in Google Drive
"""

import streamlit as st
import anthropic
import json
import pandas as pd
import fitz  # PyMuPDF for PDF processing
from google.cloud import vision
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from PIL import Image, ImageDraw, ImageFont
import gspread
from datetime import datetime
import io
import time

WATERMARK_TEXT = "PROCESSED"

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
    <p>Process only new files → Auto-save to Google Sheets → Watermark in Drive</p>
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
            'https://www.googleapis.com/auth/drive',
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
    """List all supported files in a Google Drive folder."""
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
    except:
        return None


def add_watermark_to_image(image_bytes, mime_type, text=WATERMARK_TEXT):
    """Add a diagonal watermark to an image file."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_size = max(img.size) // 12
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    stamp = Image.new("RGBA", (text_w + 20, text_h + 20), (0, 0, 0, 0))
    stamp_draw = ImageDraw.Draw(stamp)
    stamp_draw.text((10, 10), text, font=font, fill=(200, 40, 40, 120))
    stamp = stamp.rotate(45, expand=True)

    x = (img.width - stamp.width) // 2
    y = (img.height - stamp.height) // 2
    overlay.paste(stamp, (x, y), stamp)
    result = Image.alpha_composite(img, overlay)

    output = io.BytesIO()
    if mime_type == "image/png":
        result.save(output, format="PNG")
    else:
        result.convert("RGB").save(output, format="JPEG", quality=95)
    return output.getvalue()


def add_watermark_to_pdf(pdf_bytes, text=WATERMARK_TEXT):
    """Add a diagonal watermark to each page of a PDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page in doc:
        rect = page.rect
        page.insert_text(
            (rect.width / 2 - 100, rect.height / 2),
            text,
            fontsize=48,
            color=(0.85, 0.2, 0.2),
            rotate=45,
            overlay=True,
        )
    output = doc.tobytes()
    doc.close()
    return output


def apply_watermark_and_upload(drive_service, file_id, file_bytes, mime_type):
    """Watermark a file and upload it back to Google Drive."""
    if mime_type == "application/pdf":
        watermarked = add_watermark_to_pdf(file_bytes)
    elif mime_type.startswith("image/"):
        watermarked = add_watermark_to_image(file_bytes, mime_type)
    else:
        return False

    media = MediaIoBaseUpload(io.BytesIO(watermarked), mimetype=mime_type, resumable=True)
    drive_service.files().update(fileId=file_id, media_body=media).execute()
    return True


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

IMPORTANT: Use TOTAL column if CA/ESE/TOTAL exists. Extract ALL subjects with full names. Never use 0 unless actually 0."""
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
            first_row = worksheet.row_values(1)
            if not first_row or first_row[0] != "Timestamp":
                worksheet.insert_row(headers, 1)
                worksheet.format('A1:L1', {'textFormat': {'bold': True}})
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title="Marksheets", rows=1000, cols=20)
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
        return True
        
    except Exception as e:
        st.error(f"Sheets error: {e}")
        return False


# ============ PASSBOOK FUNCTIONS ============

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
        return True
        
    except Exception as e:
        st.error(f"Sheets error: {e}")
        return False


# ============ TRACKING PROCESSED FILES ============

def get_processed_file_ids(sheets_client, spreadsheet_id):
    """Get list of already processed file IDs from tracking sheet."""
    try:
        spreadsheet = sheets_client.open_by_key(spreadsheet_id)

        try:
            tracking_sheet = spreadsheet.worksheet("_ProcessedFiles")
            file_ids = tracking_sheet.col_values(1)[1:]
            return set(file_ids)
        except gspread.WorksheetNotFound:
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

        tracking_sheet.append_row([
            file_id,
            filename,
            doc_type,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])
        return True
    except Exception:
        return False


def filter_new_files(files, processed_ids):
    """Filter out already processed files."""
    new_files = [f for f in files if f['id'] not in processed_ids]
    skipped = len(files) - len(new_files)
    return new_files, skipped


# ============ BATCH PROCESSING ============

def process_batch(files, doc_type, drive_service, vision_client, sheets_client,
                  api_key, sheet_id, progress_bar, status_text):
    """Process a batch of new files only."""
    successful = 0
    failed = 0
    results = []

    for i, file in enumerate(files):
        filename = file['name']
        file_id = file['id']
        mime_type = file['mimeType']
        status_text.markdown(f"**Processing ({i+1}/{len(files)}):** {filename}")

        try:
            file_bytes = download_file(drive_service, file_id)

            if mime_type == 'application/pdf':
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
                save_marksheet_to_sheets(sheets_client, sheet_id, data, filename)
                name = data.get('student_name', 'Unknown')
            else:
                save_passbook_to_sheets(sheets_client, sheet_id, data, filename)
                name = data.get('account_holder_name', 'Unknown')

            mark_file_as_processed(sheets_client, sheet_id, file_id, filename, doc_type)

            try:
                apply_watermark_and_upload(drive_service, file_id, file_bytes, mime_type)
            except Exception as watermark_error:
                name = f"{name} (watermark failed: {str(watermark_error)[:30]})"

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
marksheet_folder = get_secret("MARKSHEET_FOLDER_ID")
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


processed_ids = get_processed_file_ids(sheets_client, sheet_id)
st.sidebar.markdown(f"**📊 Already processed:** {len(processed_ids)} files")

# Two columns for the two folder types
col1, col2 = st.columns(2)

# ============ MARKSHEETS SECTION ============
with col1:
    st.markdown("""
    <div class="folder-card">
        <h3>📚 Marksheets Folder</h3>
    </div>
    """, unsafe_allow_html=True)
    
    marksheet_folder_id = st.text_input(
        "Marksheets Folder ID",
        value=marksheet_folder or "",
        placeholder="Enter folder ID...",
        key="marksheet_folder"
    )
    
    marksheet_files = []
    marksheet_skipped = 0
    if marksheet_folder_id:
        try:
            all_marksheet_files = list_files_in_folder(drive_service, marksheet_folder_id)
            if all_marksheet_files:
                marksheet_files, marksheet_skipped = filter_new_files(all_marksheet_files, processed_ids)
                st.success(f"**{len(marksheet_files)}** new files to process")
                if marksheet_skipped > 0:
                    st.info(f"⏭️ Skipping {marksheet_skipped} already processed files")
                with st.expander(f"View new files ({len(marksheet_files)})"):
                    for f in marksheet_files:
                        st.markdown(f"- {f['name']}")
            else:
                st.info("No files found in folder")
        except Exception as e:
            st.error(f"Error: {e}")
    
    process_marksheets = st.button("🚀 Process New Marksheets", key="btn_marksheets",
                                    disabled=not marksheet_files, use_container_width=True)


# ============ PASSBOOKS SECTION ============
with col2:
    st.markdown("""
    <div class="folder-card">
        <h3>🏦 Passbooks Folder</h3>
    </div>
    """, unsafe_allow_html=True)
    
    passbook_folder_id = st.text_input(
        "Passbooks Folder ID",
        value=passbook_folder or "",
        placeholder="Enter folder ID...",
        key="passbook_folder"
    )
    
    passbook_files = []
    passbook_skipped = 0
    if passbook_folder_id:
        try:
            all_passbook_files = list_files_in_folder(drive_service, passbook_folder_id)
            if all_passbook_files:
                passbook_files, passbook_skipped = filter_new_files(all_passbook_files, processed_ids)
                st.success(f"**{len(passbook_files)}** new files to process")
                if passbook_skipped > 0:
                    st.info(f"⏭️ Skipping {passbook_skipped} already processed files")
                with st.expander(f"View new files ({len(passbook_files)})"):
                    for f in passbook_files:
                        st.markdown(f"- {f['name']}")
            else:
                st.info("No files found in folder")
        except Exception as e:
            st.error(f"Error: {e}")
    
    process_passbooks = st.button("🚀 Process New Passbooks", key="btn_passbooks",
                                   disabled=not passbook_files, use_container_width=True)


# ============ PROCESS ALL BUTTON ============
st.markdown("---")

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    process_all = st.button("🚀 Process ALL New Documents",
                            disabled=not (marksheet_files or passbook_files),
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


# Process Marksheets Only
if process_marksheets and marksheet_files:
    st.markdown("---")
    st.markdown("## Processing Marksheets...")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    successful, failed, results = process_batch(
        marksheet_files, "marksheet", drive_service, vision_client, 
        sheets_client, api_key, sheet_id, progress_bar, status_text
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
    
    # Process Marksheets
    if marksheet_files:
        st.markdown("## 📚 Processing Marksheets...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        successful, failed, results = process_batch(
            marksheet_files, "marksheet", drive_service, vision_client,
            sheets_client, api_key, sheet_id, progress_bar, status_text
        )
        
        status_text.empty()
        progress_bar.empty()
        show_results("marksheet", successful, failed, results)
        
        total_successful += successful
        total_failed += failed
    
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
            <div class="stat-number">{len(marksheet_files) + len(passbook_files)}</div>
            <div class="stat-label">New Files Processed</div>
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
    <p style="font-size: 0.8rem;">Marksheets → "Marksheets" tab | Passbooks → "Passbooks" tab | Processed files tracked in "_ProcessedFiles" tab</p>
</div>
""", unsafe_allow_html=True)

