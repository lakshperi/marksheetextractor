"""
Marksheet Marks Extractor - Web App
Using Google Cloud Vision API (FREE tier: 1000 images/month)
"""

import streamlit as st
import base64
import json
import pandas as pd
import re
import fitz  # PyMuPDF for PDF processing
from google.cloud import vision
from google.oauth2 import service_account

# Page configuration
st.set_page_config(
    page_title="Marksheet Extractor",
    page_icon="📚",
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
        font-size: 2rem;
        font-weight: 700;
        color: #1e3a5f;
    }
    
    .stat-label {
        color: #64748b;
        font-size: 0.9rem;
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
    
    .free-badge {
        background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
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
    <h1>📚 Marksheet Extractor <span class="free-badge">FREE</span></h1>
    <p>Upload a marksheet image and get structured data instantly</p>
    <p style="font-size: 0.85rem; opacity: 0.8;">Powered by Google Cloud Vision • 1,000 free extractions/month</p>
</div>
""", unsafe_allow_html=True)


def get_media_type(filename):
    """Get media type from filename."""
    ext = filename.lower().split('.')[-1]
    media_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp'
    }
    return media_types.get(ext, 'image/jpeg')


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
    """Extract text from image using Google Cloud Vision API."""
    image = vision.Image(content=image_bytes)
    
    # Use DOCUMENT_TEXT_DETECTION for better table/structure recognition
    response = client.document_text_detection(image=image)
    
    if response.error.message:
        raise Exception(response.error.message)
    
    return response.full_text_annotation.text


def parse_marksheet_text(text):
    """Parse extracted text into structured JSON format."""
    result = {
        "student_name": None,
        "roll_number": None,
        "class": None,
        "school": None,
        "exam": None,
        "subjects": [],
        "total_marks_obtained": None,
        "total_max_marks": None,
        "percentage": None,
        "grade": None,
        "result": None
    }
    
    lines = text.split('\n')
    lines = [line.strip() for line in lines if line.strip()]
    
    # Common patterns for marksheet parsing
    name_patterns = [
        r"(?:name|student|candidate)[\s:]+([A-Za-z\s\.]+)",
        r"^([A-Z][A-Z\s\.]+)$"  # All caps name on its own line
    ]
    
    roll_patterns = [
        r"(?:roll|reg|registration|enroll)[\s\.]*(?:no|number)?[\s:\.]*(\d+)",
        r"(\d{6,12})"  # 6-12 digit number
    ]
    
    # Extract student name
    for pattern in name_patterns:
        for line in lines[:15]:  # Check first 15 lines
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if len(name) > 3 and not any(char.isdigit() for char in name):
                    result["student_name"] = name.upper()
                    break
        if result["student_name"]:
            break
    
    # Extract roll number
    for pattern in roll_patterns:
        for line in lines[:20]:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                result["roll_number"] = match.group(1)
                break
        if result["roll_number"]:
            break
    
    # Extract school/college name
    school_keywords = ['college', 'school', 'university', 'institute', 'polytechnic']
    for line in lines[:10]:
        if any(keyword in line.lower() for keyword in school_keywords):
            result["school"] = line.strip()
            break
    
    # Extract subjects and marks
    # Look for patterns like "Subject Name    85    100" or "Subject Name: 85/100"
    subject_patterns = [
        r"([A-Za-z\s&]+?)[\s:]+(\d{1,3})[\s/]+(\d{2,3})",  # Subject: 85/100
        r"([A-Za-z\s&]+?)\s+(\d{1,3})\s+(\d{2,3})",  # Subject  85  100
    ]
    
    excluded_words = ['total', 'grand', 'aggregate', 'percentage', 'result', 'grade', 'rank', 'roll', 'name']
    
    for line in lines:
        for pattern in subject_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                subject_name = match.group(1).strip()
                # Filter out non-subject lines
                if (len(subject_name) > 2 and 
                    not any(word in subject_name.lower() for word in excluded_words) and
                    not subject_name.isdigit()):
                    try:
                        marks_obtained = int(match.group(2))
                        max_marks = int(match.group(3))
                        if marks_obtained <= max_marks and max_marks <= 200:
                            result["subjects"].append({
                                "subject_name": subject_name.upper(),
                                "marks_obtained": marks_obtained,
                                "max_marks": max_marks
                            })
                    except ValueError:
                        pass
                break
    
    # Extract total marks
    total_pattern = r"(?:total|grand\s*total|aggregate)[\s:]*(\d{1,4})[\s/]+(\d{1,4})"
    for line in lines:
        match = re.search(total_pattern, line, re.IGNORECASE)
        if match:
            result["total_marks_obtained"] = int(match.group(1))
            result["total_max_marks"] = int(match.group(2))
            break
    
    # Calculate total from subjects if not found
    if not result["total_marks_obtained"] and result["subjects"]:
        result["total_marks_obtained"] = sum(s["marks_obtained"] for s in result["subjects"])
        result["total_max_marks"] = sum(s["max_marks"] for s in result["subjects"])
    
    # Extract or calculate percentage
    percentage_pattern = r"(?:percentage|percent|%)[\s:]*(\d{1,2}\.?\d*)"
    for line in lines:
        match = re.search(percentage_pattern, line, re.IGNORECASE)
        if match:
            result["percentage"] = float(match.group(1))
            break
    
    if not result["percentage"] and result["total_marks_obtained"] and result["total_max_marks"]:
        result["percentage"] = round((result["total_marks_obtained"] / result["total_max_marks"]) * 100, 2)
    
    # Extract result (pass/fail)
    result_pattern = r"\b(pass|passed|fail|failed)\b"
    for line in lines:
        match = re.search(result_pattern, line, re.IGNORECASE)
        if match:
            result["result"] = "PASS" if "pass" in match.group(1).lower() else "FAIL"
            break
    
    # Infer result from percentage
    if not result["result"] and result["percentage"]:
        result["result"] = "PASS" if result["percentage"] >= 35 else "FAIL"
    
    # Extract grade
    grade_pattern = r"(?:grade)[\s:]*([A-F][+-]?|\b[A-F]\b)"
    for line in lines:
        match = re.search(grade_pattern, line, re.IGNORECASE)
        if match:
            result["grade"] = match.group(1).upper()
            break
    
    return result


# Get credentials from secrets or manual input
def get_credentials():
    """Get Google Cloud credentials from Streamlit secrets or return None."""
    try:
        return st.secrets["GOOGLE_CREDENTIALS"]
    except (KeyError, FileNotFoundError):
        return None

# Check if credentials are configured in secrets
secrets_credentials = get_credentials()

# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    
    if secrets_credentials:
        st.success("✅ Google Cloud configured")
        credentials_json = secrets_credentials
    else:
        st.markdown("**Google Cloud Credentials**")
        credentials_file = st.file_uploader(
            "Upload service account JSON",
            type=['json'],
            help="Upload your Google Cloud service account credentials file"
        )
        if credentials_file:
            credentials_json = credentials_file.getvalue().decode('utf-8')
            st.success("✅ Credentials loaded")
        else:
            credentials_json = None
    
    st.markdown("---")
    st.markdown("### 💰 Cost")
    st.markdown("""
    - **First 1,000/month:** FREE
    - **After that:** $1.50 per 1,000
    """)
    
    st.markdown("---")
    st.markdown("### 💡 How to use")
    st.markdown("""
    1. Upload a marksheet image or PDF
    2. Click 'Extract Marks'
    3. Download JSON or view results
    """)
    
    st.markdown("---")
    st.markdown("### 📊 Supported Formats")
    st.markdown("**Images:** JPG, JPEG, PNG, GIF, WEBP")
    st.markdown("**Documents:** PDF")


# Main content
col1, col2 = st.columns([1, 1])

with col1:
    st.markdown("### 📤 Upload Marksheet")
    uploaded_file = st.file_uploader(
        "Choose an image or PDF file",
        type=['jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf'],
        help="Upload a clear image or PDF of the marksheet"
    )

with col2:
    if uploaded_file:
        st.markdown("### 🖼️ Preview")
        if is_pdf(uploaded_file.name):
            pdf_images = pdf_to_images(uploaded_file.getvalue())
            if pdf_images:
                st.image(pdf_images[0], use_container_width=True)
                if len(pdf_images) > 1:
                    st.caption(f"📄 PDF has {len(pdf_images)} pages (showing page 1)")
        else:
            st.image(uploaded_file, use_container_width=True)

# Process button
if uploaded_file and credentials_json:
    if st.button("🚀 Extract Marks (FREE)", use_container_width=True):
        with st.spinner("🔍 Analyzing marksheet with Google Vision..."):
            try:
                # Create Vision client
                client = get_vision_client(credentials_json)
                if not client:
                    st.error("Failed to create Google Vision client")
                    st.stop()
                
                # Handle PDF files
                if is_pdf(uploaded_file.name):
                    pdf_images = pdf_to_images(uploaded_file.getvalue())
                    if not pdf_images:
                        st.error("Could not extract images from PDF")
                        st.stop()
                    image_bytes = pdf_images[0]
                else:
                    image_bytes = uploaded_file.getvalue()
                
                # Extract text using Google Vision
                extracted_text = extract_text_with_google_vision(image_bytes, client)
                
                # Parse the text into structured data
                data = parse_marksheet_text(extracted_text)
                
                # Store in session state
                st.session_state['extracted_data'] = data
                st.session_state['raw_json'] = json.dumps(data, indent=2)
                st.session_state['raw_text'] = extracted_text
                
            except Exception as e:
                st.error(f"Error: {e}")

elif uploaded_file and not credentials_json:
    st.warning("⚠️ Please upload Google Cloud credentials in the sidebar")

# Display results
if 'extracted_data' in st.session_state:
    data = st.session_state['extracted_data']
    
    st.markdown("---")
    st.markdown("## 📋 Extracted Results")
    
    # Student info card
    st.markdown(f"""
    <div class="result-card">
        <h3 style="margin:0; color:#1e3a5f;">👤 {data.get('student_name') or 'N/A'}</h3>
        <p style="margin:0.5rem 0 0 0; color:#64748b;">
            Roll No: {data.get('roll_number') or 'N/A'} | 
            {data.get('school') or 'N/A'}
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Stats row
    col1, col2, col3 = st.columns(3)
    
    with col1:
        total_obt = data.get('total_marks_obtained') or 'N/A'
        total_max = data.get('total_max_marks') or 'N/A'
        st.markdown(f"""
        <div class="stat-box">
            <div class="stat-number">{total_obt}/{total_max}</div>
            <div class="stat-label">Total Marks</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        percentage = data.get('percentage') or 0
        st.markdown(f"""
        <div class="stat-box">
            <div class="stat-number">{percentage}%</div>
            <div class="stat-label">Percentage</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        result = data.get('result') or 'N/A'
        result_color = "#22c55e" if result == "PASS" else "#ef4444"
        st.markdown(f"""
        <div class="stat-box">
            <div class="stat-number" style="color:{result_color}">{result}</div>
            <div class="stat-label">Result</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Subjects table
    st.markdown("### 📝 Subject-wise Marks")
    
    if data.get('subjects'):
        subjects_df = pd.DataFrame(data['subjects'])
        subjects_df.columns = ['Subject', 'Marks Obtained', 'Max Marks']
        subjects_df['Percentage'] = (subjects_df['Marks Obtained'] / subjects_df['Max Marks'] * 100).round(1)
        st.dataframe(
            subjects_df,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No subjects detected. Check the raw text below.")
    
    # Download buttons
    st.markdown("### 💾 Download Data")
    col1, col2 = st.columns(2)
    
    with col1:
        st.download_button(
            label="📥 Download JSON",
            data=st.session_state['raw_json'],
            file_name=f"{(data.get('student_name') or 'marksheet').replace(' ', '_')}.json",
            mime="application/json",
            use_container_width=True
        )
    
    with col2:
        if data.get('subjects'):
            csv = subjects_df.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"{(data.get('student_name') or 'marksheet').replace(' ', '_')}.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    # Raw data expanders
    with st.expander("🔍 View Raw JSON"):
        st.code(st.session_state['raw_json'], language='json')
    
    with st.expander("📄 View Raw OCR Text"):
        st.text(st.session_state.get('raw_text', 'No text extracted'))

# Footer
st.markdown("""
<div class="footer">
    <p>Built for Canada Nagarathar Sangam - Education Committee</p>
    <p style="font-size: 0.8rem;">Powered by Google Cloud Vision API</p>
</div>
""", unsafe_allow_html=True)

