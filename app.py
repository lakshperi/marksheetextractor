"""
Marksheet Marks Extractor - Hybrid Version
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
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
<div class="main-header">
    <h1>📚 Marksheet Extractor <span class="savings-badge">70% Savings</span></h1>
    <p>Upload a marksheet image and get structured data instantly</p>
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


def parse_text_with_claude(extracted_text, api_key):
    """Use Claude to intelligently parse the extracted text into structured JSON."""
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
            help="For smart text parsing (~$0.003/marksheet)"
        )
        if api_key:
            st.success("✅ API key entered")
    
    st.markdown("---")
    st.markdown("### 💰 Cost Breakdown")
    st.markdown("""
    | Step | Cost |
    |------|------|
    | Google Vision OCR | **FREE** |
    | Claude Text Parse | ~$0.003 |
    | **Total** | **~$0.003** |
    
    *vs $0.01 with image-only approach*
    """)
    
    st.markdown("---")
    st.markdown("### 💡 How it works")
    st.markdown("""
    1. **Google Vision** extracts text (FREE)
    2. **Claude** parses text to JSON (cheap)
    3. You get accurate results at 70% less cost!
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
if uploaded_file and credentials_json and api_key:
    if st.button("🚀 Extract Marks (Hybrid Mode)", use_container_width=True):
        
        # Progress indicators
        progress_container = st.container()
        
        with progress_container:
            # Step 1: Google Vision OCR
            with st.spinner("Step 1/2: Extracting text with Google Vision (FREE)..."):
                try:
                    vision_client = get_vision_client(credentials_json)
                    if not vision_client:
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
                    
                    # Extract text
                    extracted_text = extract_text_with_google_vision(image_bytes, vision_client)
                    st.success("✅ Text extracted with Google Vision (FREE)")
                    
                except Exception as e:
                    st.error(f"Google Vision Error: {e}")
                    st.stop()
            
            # Step 2: Claude parsing
            with st.spinner("Step 2/2: Parsing with Claude (~$0.003)..."):
                try:
                    result = parse_text_with_claude(extracted_text, api_key)
                    
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
                    
                    # Store in session state
                    st.session_state['extracted_data'] = data
                    st.session_state['raw_json'] = json.dumps(data, indent=2)
                    st.session_state['raw_text'] = extracted_text
                    
                    st.success("✅ Marks parsed successfully!")
                    
                except json.JSONDecodeError as e:
                    st.error(f"Failed to parse response as JSON: {e}")
                    st.code(result)
                except anthropic.APIError as e:
                    st.error(f"Claude API Error: {e}")

elif uploaded_file:
    if not credentials_json:
        st.warning("⚠️ Please add Google Cloud credentials in the sidebar")
    if not api_key:
        st.warning("⚠️ Please add Anthropic API key in the sidebar")

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
        result_color = "#22c55e" if result and "PASS" in str(result).upper() else "#ef4444"
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
        st.info("No subjects detected.")
    
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
    
    with st.expander("📄 View Extracted OCR Text (from Google Vision)"):
        st.text(st.session_state.get('raw_text', 'No text extracted'))

# Footer
st.markdown("""
<div class="footer">
    <p>Built for Canada Nagarathar Sangam - Education Committee</p>
    <p style="font-size: 0.8rem;">Hybrid Mode: Google Vision (FREE) + Claude (Smart)</p>
</div>
""", unsafe_allow_html=True)

