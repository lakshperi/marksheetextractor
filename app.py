"""
Document Extractor - Multi-Document Support with Google Sheets Integration
Supports: Marksheets & Bank Passbooks
Google Vision (FREE OCR) + Claude (Smart Parsing) + Google Sheets (Auto-save)
"""

import streamlit as st
import anthropic
import json
import pandas as pd
import fitz  # PyMuPDF for PDF processing
from google.cloud import vision
from google.oauth2 import service_account
import gspread
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="Document Extractor",
    page_icon="📄",
    layout="centered"
)

# Custom CSS for beautiful UI
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
        text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
    }
    
    .main-header p {
        color: #b8d4e8;
        font-size: 1.1rem;
        margin-top: 0.5rem;
    }
    
    .result-card {
        background: linear-gradient(145deg, #f8fafc 0%, #e2e8f0 100%);
        padding: 1.5rem;
        border-radius: 12px;
        border-left: 4px solid #2d5a87;
        margin: 1rem 0;
    }
    
    .stat-box {
        background: white;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    
    .stat-number {
        font-size: 1.5rem;
        font-weight: 700;
        color: #1e3a5f;
    }
    
    .stat-label {
        color: #64748b;
        font-size: 0.85rem;
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
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(30, 58, 95, 0.4);
    }
    
    .footer {
        text-align: center;
        color: #94a3b8;
        padding: 2rem;
        font-size: 0.9rem;
    }
    
    .savings-badge {
        background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
        margin-left: 0.5rem;
    }
    
    .sheets-badge {
        background: linear-gradient(135deg, #4285f4 0%, #34a853 100%);
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
        margin-left: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
<div class="main-header">
    <h1>📄 Document Extractor</h1>
    <p>Extract data from Marksheets & Bank Passbooks</p>
    <p style="font-size: 0.85rem; opacity: 0.8;">
        <span class="savings-badge">70% Savings</span>
        <span class="sheets-badge">📊 Auto-save to Sheets</span>
    </p>
</div>
""", unsafe_allow_html=True)


def pdf_to_images(pdf_bytes):
    """Convert PDF pages to images and return as list of image bytes."""
    images = []
    try:
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            images.append(img_bytes)
        pdf_document.close()
    except Exception as e:
        st.error(f"Error processing PDF: {e}")
    return images


def is_pdf(filename):
    """Check if file is a PDF."""
    return filename.lower().endswith('.pdf')


def get_vision_client(credentials_json):
    """Create Google Vision client from credentials."""
    try:
        credentials_dict = json.loads(credentials_json)
        credentials = service_account.Credentials.from_service_account_info(credentials_dict)
        client = vision.ImageAnnotatorClient(credentials=credentials)
        return client
    except Exception as e:
        st.error(f"Error creating Vision client: {e}")
        return None


def get_sheets_client(credentials_json):
    """Create Google Sheets client from credentials."""
    try:
        credentials_dict = json.loads(credentials_json)
        credentials = service_account.Credentials.from_service_account_info(
            credentials_dict,
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
        )
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        st.error(f"Error creating Sheets client: {e}")
        return None


def get_or_create_spreadsheet(sheets_client, spreadsheet_id=None):
    """Get existing spreadsheet or return None if not found."""
    try:
        if spreadsheet_id:
            return sheets_client.open_by_key(spreadsheet_id)
        return None
    except Exception as e:
        st.warning(f"Could not open spreadsheet: {e}")
        return None


def ensure_worksheet_headers(worksheet, headers):
    """Ensure worksheet has correct headers."""
    try:
        existing = worksheet.row_values(1)
        if not existing or existing != headers:
            worksheet.clear()
            worksheet.append_row(headers)
    except Exception:
        worksheet.append_row(headers)


def save_marksheet_to_sheets(sheets_client, spreadsheet_id, data):
    """Save marksheet data to Google Sheets."""
    try:
        spreadsheet = sheets_client.open_by_key(spreadsheet_id)
        
        # Try to get or create Marksheets worksheet
        try:
            worksheet = spreadsheet.worksheet("Marksheets")
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title="Marksheets", rows=1000, cols=20)
        
        # Define headers
        headers = [
            "Timestamp", "Student Name", "Roll Number", "School/College", 
            "Class/Semester", "Exam", "Total Marks", "Max Marks", 
            "Percentage", "Result", "Subjects & Marks"
        ]
        
        # Ensure headers exist
        ensure_worksheet_headers(worksheet, headers)
        
        # Prepare subjects string
        subjects_str = ""
        if data.get('subjects'):
            subjects_str = " | ".join([
                f"{s.get('subject_name', 'N/A')}: {s.get('marks_obtained', 0)}/{s.get('max_marks', 100)}"
                for s in data['subjects']
            ])
        
        # Prepare row data
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
        
        # Append row
        worksheet.append_row(row, value_input_option='USER_ENTERED')
        return True, f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        
    except Exception as e:
        return False, str(e)


def save_passbook_to_sheets(sheets_client, spreadsheet_id, data):
    """Save passbook data to Google Sheets."""
    try:
        spreadsheet = sheets_client.open_by_key(spreadsheet_id)
        
        # Try to get or create Passbooks worksheet
        try:
            worksheet = spreadsheet.worksheet("Passbooks")
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title="Passbooks", rows=1000, cols=15)
        
        # Define headers
        headers = [
            "Timestamp", "Account Holder Name", "Account Number", "Bank Name",
            "Branch Name", "IFSC Code", "MICR Code", "Customer ID",
            "Account Type", "Branch Address", "Phone", "Email", "Nominee"
        ]
        
        # Ensure headers exist
        ensure_worksheet_headers(worksheet, headers)
        
        # Prepare row data
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            data.get('account_holder_name') or 'N/A',
            data.get('account_number') or 'N/A',
            data.get('bank_name') or 'N/A',
            data.get('branch_name') or 'N/A',
            data.get('ifsc_code') or 'N/A',
            data.get('micr_code') or 'N/A',
            data.get('customer_id') or 'N/A',
            data.get('account_type') or 'N/A',
            data.get('branch_address') or 'N/A',
            data.get('phone_number') or 'N/A',
            data.get('email') or 'N/A',
            data.get('nominee_name') or 'N/A'
        ]
        
        # Append row
        worksheet.append_row(row, value_input_option='USER_ENTERED')
        return True, f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        
    except Exception as e:
        return False, str(e)


def extract_text_with_google_vision(image_bytes, client):
    """Extract text from image using Google Cloud Vision API (FREE tier)."""
    image = vision.Image(content=image_bytes)
    response = client.document_text_detection(image=image)
    
    if response.error.message:
        raise Exception(response.error.message)
    
    return response.full_text_annotation.text


def parse_marksheet_with_claude(extracted_text, api_key):
    """Use Claude to parse marksheet text into structured JSON."""
    client = anthropic.Anthropic(api_key=api_key)
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""Here is text extracted from a marksheet/report card using OCR:

---
{extracted_text}
---

Parse this text and extract the marks information. Return ONLY a valid JSON object (no markdown, no explanation) with these fields:

{{
    "student_name": "Name of the student",
    "roll_number": "Roll number or Register number if present",
    "class": "Class/Grade/Semester if present",
    "school": "School/College name if present",
    "exam": "Exam name or Month/Year if present",
    "subjects": [
        {{
            "subject_name": "Subject name (can be long, include full name)",
            "marks_obtained": number (use TOTAL marks if CA/ESE/TOTAL columns exist, otherwise use the main marks column),
            "max_marks": number (usually 100)
        }}
    ],
    "total_marks_obtained": number (sum of all subject marks),
    "total_max_marks": number (sum of max marks),
    "percentage": number,
    "grade": "Grade if present",
    "result": "Pass/Fail if present"
}}

IMPORTANT INSTRUCTIONS:
1. If the marksheet has columns like CA (Continuous Assessment), ESE (End Semester Exam), and TOTAL - use the TOTAL column value for marks_obtained
2. Extract ALL subjects - do not skip any subject even if the name is very long
3. Subject names like "Software Project Management and Entrepreneurship" should be extracted fully
4. If marks are shown as "100" use 100 as the number, not 0
5. Look for rows that have subject codes (like CSN51, CSN52, etc.) to identify subjects
6. The "Total" row at the bottom is the overall total, not a subject - use it for total_marks_obtained
7. All marks_obtained values must be actual numbers from the marksheet, never 0 unless actually 0"""
        }]
    )
    
    return response.content[0].text


def parse_passbook_with_claude(extracted_text, api_key):
    """Use Claude to parse passbook text into structured JSON."""
    client = anthropic.Anthropic(api_key=api_key)
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""Here is text extracted from a bank passbook using OCR:

---
{extracted_text}
---

Parse this text and extract the bank account information. Return ONLY a valid JSON object (no markdown, no explanation) with these fields:

{{
    "account_holder_name": "Name of the account holder",
    "account_number": "Bank account number",
    "ifsc_code": "IFSC code of the branch",
    "micr_code": "MICR code if present",
    "customer_id": "Customer ID/Customer number if present",
    "branch_name": "Name of the bank branch",
    "branch_address": "Full address of the branch",
    "bank_name": "Name of the bank",
    "account_type": "Type of account (Savings/Current) if present",
    "opening_date": "Account opening date if present",
    "nominee_name": "Nominee name if present",
    "phone_number": "Phone number if present",
    "email": "Email address if present"
}}

If any field is not found in the text, use null for that field.
Look carefully for IFSC code (11 characters, starts with 4 letters), MICR code (9 digits), and account numbers."""
        }]
    )
    
    return response.content[0].text


# Get credentials from secrets
def get_google_credentials():
    try:
        return st.secrets["GOOGLE_CREDENTIALS"]
    except (KeyError, FileNotFoundError):
        return None


def get_anthropic_key():
    try:
        return st.secrets["ANTHROPIC_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None


def get_spreadsheet_id():
    try:
        return st.secrets["GOOGLE_SPREADSHEET_ID"]
    except (KeyError, FileNotFoundError):
        return None


# Check if credentials are configured
google_creds = get_google_credentials()
anthropic_key = get_anthropic_key()
spreadsheet_id = get_spreadsheet_id()

# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    
    # Google credentials
    if google_creds:
        st.success("✅ Google Cloud configured")
        credentials_json = google_creds
    else:
        st.markdown("**Google Cloud Credentials**")
        credentials_file = st.file_uploader(
            "Upload service account JSON",
            type=['json'],
            help="For FREE OCR and Sheets"
        )
        credentials_json = credentials_file.getvalue().decode('utf-8') if credentials_file else None
        if credentials_json:
            st.success("✅ Google credentials loaded")
    
    # Anthropic API key
    if anthropic_key:
        st.success("✅ Claude API configured")
        api_key = anthropic_key
    else:
        api_key = st.text_input(
            "Anthropic API Key",
            type="password",
            placeholder="sk-ant-api03-...",
            help="For smart text parsing"
        )
        if api_key:
            st.success("✅ API key entered")
    
    # Google Spreadsheet ID
    st.markdown("---")
    st.markdown("### 📊 Google Sheets")
    
    if spreadsheet_id:
        st.success("✅ Spreadsheet configured")
        sheet_id = spreadsheet_id
        st.markdown(f"[📊 Open Spreadsheet](https://docs.google.com/spreadsheets/d/{sheet_id})")
    else:
        sheet_id = st.text_input(
            "Spreadsheet ID",
            placeholder="1abc...xyz",
            help="The ID from your Google Sheets URL"
        )
        if sheet_id:
            st.success("✅ Spreadsheet ID entered")
        st.markdown("*Get ID from: docs.google.com/spreadsheets/d/**ID**/edit*")
    
    st.markdown("---")
    st.markdown("### 💰 Cost: ~$0.003/doc")
    
    st.markdown("---")
    st.markdown("### 📊 Supported Formats")
    st.markdown("JPG, JPEG, PNG, GIF, WEBP, PDF")


# Document Type Selection
st.markdown("### 📋 Select Document Type")

col1, col2 = st.columns(2)

with col1:
    marksheet_selected = st.button("📚 Marksheet", use_container_width=True, key="btn_marksheet")
    
with col2:
    passbook_selected = st.button("🏦 Bank Passbook", use_container_width=True, key="btn_passbook")

# Initialize session state
if 'doc_type' not in st.session_state:
    st.session_state['doc_type'] = None

if marksheet_selected:
    st.session_state['doc_type'] = 'marksheet'
    if 'extracted_data' in st.session_state:
        del st.session_state['extracted_data']

if passbook_selected:
    st.session_state['doc_type'] = 'passbook'
    if 'extracted_data' in st.session_state:
        del st.session_state['extracted_data']

# Show selected document type
if st.session_state['doc_type']:
    doc_type = st.session_state['doc_type']
    
    if doc_type == 'marksheet':
        st.info("📚 **Selected: Marksheet** - Will extract student details and marks")
    else:
        st.info("🏦 **Selected: Bank Passbook** - Will extract account details")
    
    st.markdown("---")
    
    # Upload section
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown(f"### 📤 Upload {'Marksheet' if doc_type == 'marksheet' else 'Passbook'}")
        uploaded_file = st.file_uploader(
            "Choose an image or PDF file",
            type=['jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf'],
            help=f"Upload a clear image or PDF"
        )
    
    with col2:
        if uploaded_file:
            st.markdown("### 🖼️ Preview")
            if is_pdf(uploaded_file.name):
                pdf_images = pdf_to_images(uploaded_file.getvalue())
                if pdf_images:
                    st.image(pdf_images[0], use_container_width=True)
                    if len(pdf_images) > 1:
                        st.caption(f"📄 PDF has {len(pdf_images)} pages")
            else:
                st.image(uploaded_file, use_container_width=True)
    
    # Process button
    if uploaded_file and credentials_json and api_key:
        if st.button(f"🚀 Extract & Save to Sheets", use_container_width=True):
            
            with st.spinner("Step 1/3: Extracting text (FREE)..."):
                try:
                    vision_client = get_vision_client(credentials_json)
                    if not vision_client:
                        st.error("Failed to create Vision client")
                        st.stop()
                    
                    if is_pdf(uploaded_file.name):
                        pdf_images = pdf_to_images(uploaded_file.getvalue())
                        if not pdf_images:
                            st.error("Could not extract images from PDF")
                            st.stop()
                        image_bytes = pdf_images[0]
                    else:
                        image_bytes = uploaded_file.getvalue()
                    
                    extracted_text = extract_text_with_google_vision(image_bytes, vision_client)
                    st.success("✅ Text extracted (FREE)")
                    
                except Exception as e:
                    st.error(f"Vision Error: {e}")
                    st.stop()
            
            with st.spinner("Step 2/3: Parsing with Claude..."):
                try:
                    if doc_type == 'marksheet':
                        result = parse_marksheet_with_claude(extracted_text, api_key)
                    else:
                        result = parse_passbook_with_claude(extracted_text, api_key)
                    
                    clean_result = result.strip()
                    if clean_result.startswith("```json"):
                        clean_result = clean_result[7:]
                    if clean_result.startswith("```"):
                        clean_result = clean_result[3:]
                    if clean_result.endswith("```"):
                        clean_result = clean_result[:-3]
                    clean_result = clean_result.strip()
                    
                    data = json.loads(clean_result)
                    
                    st.session_state['extracted_data'] = data
                    st.session_state['raw_json'] = json.dumps(data, indent=2)
                    st.session_state['raw_text'] = extracted_text
                    st.session_state['result_type'] = doc_type
                    
                    st.success("✅ Data parsed")
                    
                except json.JSONDecodeError as e:
                    st.error(f"Parse error: {e}")
                    st.code(result)
                    st.stop()
                except anthropic.APIError as e:
                    st.error(f"Claude Error: {e}")
                    st.stop()
            
            # Save to Google Sheets
            if sheet_id:
                with st.spinner("Step 3/3: Saving to Google Sheets..."):
                    try:
                        sheets_client = get_sheets_client(credentials_json)
                        if sheets_client:
                            if doc_type == 'marksheet':
                                success, result_url = save_marksheet_to_sheets(sheets_client, sheet_id, data)
                            else:
                                success, result_url = save_passbook_to_sheets(sheets_client, sheet_id, data)
                            
                            if success:
                                st.success(f"✅ Saved to Google Sheets!")
                                st.markdown(f"[📊 Open Spreadsheet]({result_url})")
                            else:
                                st.warning(f"Could not save to Sheets: {result_url}")
                        else:
                            st.warning("Could not connect to Google Sheets")
                    except Exception as e:
                        st.warning(f"Sheets error: {e}")
            else:
                st.info("💡 Add Spreadsheet ID in sidebar to auto-save to Google Sheets")
    
    elif uploaded_file:
        if not credentials_json:
            st.warning("⚠️ Please add Google Cloud credentials")
        if not api_key:
            st.warning("⚠️ Please add Anthropic API key")

else:
    st.markdown("👆 **Please select a document type above to continue**")


# Display Results
if 'extracted_data' in st.session_state and 'result_type' in st.session_state:
    data = st.session_state['extracted_data']
    result_type = st.session_state['result_type']
    
    st.markdown("---")
    st.markdown("## 📋 Extracted Results")
    
    if result_type == 'marksheet':
        # Marksheet Results
        st.markdown(f"""
        <div class="result-card">
            <h3 style="margin:0; color:#1e3a5f;">👤 {data.get('student_name') or 'N/A'}</h3>
            <p style="margin:0.5rem 0 0 0; color:#64748b;">
                Roll No: {data.get('roll_number') or 'N/A'} | 
                {data.get('school') or 'N/A'}
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(f"""
            <div class="stat-box">
                <div class="stat-number">{data.get('total_marks_obtained') or 'N/A'}/{data.get('total_max_marks') or 'N/A'}</div>
                <div class="stat-label">Total Marks</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="stat-box">
                <div class="stat-number">{data.get('percentage') or 0}%</div>
                <div class="stat-label">Percentage</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            result = data.get('result') or 'N/A'
            result_color = "#22c55e" if result and "PASS" in str(result).upper() else "#ef4444"
            st.markdown(f"""
            <div class="stat-box">
                <div class="stat-number" style="color:{result_color}">{result}</div>
                <div class="stat-label">Result</div>
            </div>
            """, unsafe_allow_html=True)
        
        # Subjects table
        if data.get('subjects'):
            st.markdown("### 📝 Subject-wise Marks")
            subjects_df = pd.DataFrame(data['subjects'])
            subjects_df.columns = ['Subject', 'Marks Obtained', 'Max Marks']
            subjects_df['Marks Obtained'] = pd.to_numeric(subjects_df['Marks Obtained'], errors='coerce').fillna(0)
            subjects_df['Max Marks'] = pd.to_numeric(subjects_df['Max Marks'], errors='coerce').fillna(100)
            subjects_df['Percentage'] = (subjects_df['Marks Obtained'] / subjects_df['Max Marks'] * 100).round(1)
            st.dataframe(subjects_df, use_container_width=True, hide_index=True)
    
    else:
        # Passbook Results
        st.markdown(f"""
        <div class="result-card">
            <h3 style="margin:0; color:#1e3a5f;">🏦 {data.get('bank_name') or 'Bank'}</h3>
            <p style="margin:0.5rem 0 0 0; color:#64748b;">
                {data.get('branch_name') or 'N/A'}
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("### 👤 Account Holder Details")
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"""
            <div class="stat-box">
                <div class="stat-number" style="font-size:1.2rem">{data.get('account_holder_name') or 'N/A'}</div>
                <div class="stat-label">Account Holder Name</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="stat-box">
                <div class="stat-number" style="font-size:1.2rem">{data.get('account_number') or 'N/A'}</div>
                <div class="stat-label">Account Number</div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("### 🏛️ Bank Details")
        
        bank_details = [
            ("IFSC Code", data.get('ifsc_code')),
            ("MICR Code", data.get('micr_code')),
            ("Customer ID", data.get('customer_id')),
            ("Branch Name", data.get('branch_name')),
            ("Account Type", data.get('account_type')),
            ("Opening Date", data.get('opening_date')),
        ]
        
        col1, col2 = st.columns(2)
        for i, (label, value) in enumerate(bank_details):
            with col1 if i % 2 == 0 else col2:
                st.markdown(f"**{label}:** {value or 'N/A'}")
        
        if data.get('branch_address'):
            st.markdown("### 📍 Branch Address")
            st.info(data.get('branch_address'))
    
    # Download buttons
    st.markdown("### 💾 Download Data")
    col1, col2 = st.columns(2)
    
    with col1:
        filename = data.get('student_name') or data.get('account_holder_name') or 'document'
        st.download_button(
            label="📥 Download JSON",
            data=st.session_state['raw_json'],
            file_name=f"{filename.replace(' ', '_')}.json",
            mime="application/json",
            use_container_width=True
        )
    
    with col2:
        if result_type == 'marksheet' and data.get('subjects'):
            csv = pd.DataFrame(data['subjects']).to_csv(index=False)
        else:
            csv = pd.DataFrame([data]).to_csv(index=False)
        
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"{filename.replace(' ', '_')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with st.expander("🔍 View Raw JSON"):
        st.code(st.session_state['raw_json'], language='json')
    
    with st.expander("📄 View Extracted OCR Text"):
        st.text(st.session_state.get('raw_text', 'No text'))

# Footer
st.markdown("""
<div class="footer">
    <p>Built for Canada Nagarathar Sangam - Education Committee</p>
    <p style="font-size: 0.8rem;">Auto-saves to Google Sheets 📊</p>
</div>
""", unsafe_allow_html=True)

