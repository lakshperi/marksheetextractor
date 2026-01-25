"""
Document Extractor - Multi-Document Support
Supports: Marksheets & Bank Passbooks
Google Vision (FREE OCR) + Claude (Smart Parsing) = 70% Cost Savings
"""

import streamlit as st
import anthropic
import json
import pandas as pd
import fitz  # PyMuPDF for PDF processing
from google.cloud import vision
from google.oauth2 import service_account

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
    
    .doc-type-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        border: 2px solid #e2e8f0;
        text-align: center;
        cursor: pointer;
        transition: all 0.3s ease;
    }
    
    .doc-type-card:hover {
        border-color: #2d5a87;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    
    .doc-type-card.selected {
        border-color: #2d5a87;
        background: linear-gradient(145deg, #f0f9ff 0%, #e0f2fe 100%);
    }
    
    .info-row {
        display: flex;
        justify-content: space-between;
        padding: 0.5rem 0;
        border-bottom: 1px solid #e2e8f0;
    }
    
    .info-label {
        color: #64748b;
        font-weight: 500;
    }
    
    .info-value {
        color: #1e3a5f;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
<div class="main-header">
    <h1>📄 Document Extractor <span class="savings-badge">70% Savings</span></h1>
    <p>Extract data from Marksheets & Bank Passbooks</p>
    <p style="font-size: 0.85rem; opacity: 0.8;">Hybrid: Google Vision (FREE OCR) + Claude (Smart Parsing)</p>
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
    "roll_number": "Roll number if present",
    "class": "Class/Grade if present",
    "school": "School/College name if present",
    "exam": "Exam name if present",
    "subjects": [
        {{
            "subject_name": "Subject name",
            "marks_obtained": number,
            "max_marks": number
        }}
    ],
    "total_marks_obtained": number,
    "total_max_marks": number,
    "percentage": number,
    "grade": "Grade if present",
    "result": "Pass/Fail if present"
}}

If any field is not found in the text, use null for that field.
Extract ALL subjects with their marks that you can find in the text."""
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
    """Get Google Cloud credentials from Streamlit secrets."""
    try:
        return st.secrets["GOOGLE_CREDENTIALS"]
    except (KeyError, FileNotFoundError):
        return None


def get_anthropic_key():
    """Get Anthropic API key from Streamlit secrets."""
    try:
        return st.secrets["ANTHROPIC_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None


# Check if credentials are configured
google_creds = get_google_credentials()
anthropic_key = get_anthropic_key()

# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    
    # Google credentials
    if google_creds:
        st.success("✅ Google Vision configured")
        credentials_json = google_creds
    else:
        st.markdown("**Google Cloud Credentials**")
        credentials_file = st.file_uploader(
            "Upload service account JSON",
            type=['json'],
            help="For FREE OCR text extraction"
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
            help="For smart text parsing (~$0.003/document)"
        )
        if api_key:
            st.success("✅ API key entered")
    
    st.markdown("---")
    st.markdown("### 💰 Cost: ~$0.003/document")
    st.markdown("*Google Vision: FREE, Claude: ~$0.003*")
    
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

# Initialize session state for document type
if 'doc_type' not in st.session_state:
    st.session_state['doc_type'] = None

if marksheet_selected:
    st.session_state['doc_type'] = 'marksheet'
    # Clear previous results
    if 'extracted_data' in st.session_state:
        del st.session_state['extracted_data']

if passbook_selected:
    st.session_state['doc_type'] = 'passbook'
    # Clear previous results
    if 'extracted_data' in st.session_state:
        del st.session_state['extracted_data']

# Show selected document type
if st.session_state['doc_type']:
    doc_type = st.session_state['doc_type']
    
    if doc_type == 'marksheet':
        st.info("📚 **Selected: Marksheet** - Will extract student name, subjects, marks, percentage, etc.")
    else:
        st.info("🏦 **Selected: Bank Passbook** - Will extract account holder name, account number, IFSC, MICR, branch details, etc.")
    
    st.markdown("---")
    
    # Upload section
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown(f"### 📤 Upload {'Marksheet' if doc_type == 'marksheet' else 'Passbook'}")
        uploaded_file = st.file_uploader(
            "Choose an image or PDF file",
            type=['jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf'],
            help=f"Upload a clear image or PDF of the {'marksheet' if doc_type == 'marksheet' else 'passbook'}"
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
        if st.button(f"🚀 Extract {'Marks' if doc_type == 'marksheet' else 'Details'}", use_container_width=True):
            
            with st.spinner("Step 1/2: Extracting text with Google Vision (FREE)..."):
                try:
                    vision_client = get_vision_client(credentials_json)
                    if not vision_client:
                        st.error("Failed to create Google Vision client")
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
                    st.error(f"Google Vision Error: {e}")
                    st.stop()
            
            with st.spinner("Step 2/2: Parsing with Claude (~$0.003)..."):
                try:
                    if doc_type == 'marksheet':
                        result = parse_marksheet_with_claude(extracted_text, api_key)
                    else:
                        result = parse_passbook_with_claude(extracted_text, api_key)
                    
                    # Parse JSON
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
                    
                    st.success("✅ Data extracted successfully!")
                    
                except json.JSONDecodeError as e:
                    st.error(f"Failed to parse response: {e}")
                    st.code(result)
                except anthropic.APIError as e:
                    st.error(f"Claude API Error: {e}")
    
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
            # Convert to numeric to handle string values
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
        
        # Account holder info
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
        
        # Bank details
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
        
        # Address
        if data.get('branch_address'):
            st.markdown("### 📍 Branch Address")
            st.info(data.get('branch_address'))
        
        # Contact info
        if data.get('phone_number') or data.get('email') or data.get('nominee_name'):
            st.markdown("### 📞 Additional Info")
            if data.get('phone_number'):
                st.markdown(f"**Phone:** {data.get('phone_number')}")
            if data.get('email'):
                st.markdown(f"**Email:** {data.get('email')}")
            if data.get('nominee_name'):
                st.markdown(f"**Nominee:** {data.get('nominee_name')}")
    
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
        # Create CSV from data
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
    
    # Raw data expanders
    with st.expander("🔍 View Raw JSON"):
        st.code(st.session_state['raw_json'], language='json')
    
    with st.expander("📄 View Extracted OCR Text"):
        st.text(st.session_state.get('raw_text', 'No text extracted'))

# Footer
st.markdown("""
<div class="footer">
    <p>Built for Canada Nagarathar Sangam - Education Committee</p>
    <p style="font-size: 0.8rem;">Hybrid Mode: Google Vision (FREE) + Claude (Smart)</p>
</div>
""", unsafe_allow_html=True)

