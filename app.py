"""
Marksheet Marks Extractor - Web App
A Streamlit app to extract marks from marksheet images using Claude Vision API
"""

import streamlit as st
import anthropic
import base64
import json
import pandas as pd
from io import BytesIO

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
    
    .subject-row {
        background: white;
        padding: 0.75rem 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        display: flex;
        justify-content: space-between;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    
    .upload-section {
        background: linear-gradient(145deg, #f0f9ff 0%, #e0f2fe 100%);
        padding: 2rem;
        border-radius: 16px;
        border: 2px dashed #3d7ab5;
        text-align: center;
        margin: 1rem 0;
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
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
<div class="main-header">
    <h1>📚 Marksheet Extractor</h1>
    <p>Upload a marksheet image and get structured data instantly</p>
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


def extract_marks(image_bytes, media_type, api_key):
    """Extract marks from image using Claude Vision API."""
    image_data = base64.standard_b64encode(image_bytes).decode("utf-8")
    
    client = anthropic.Anthropic(api_key=api_key)
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_data
                    }
                },
                {
                    "type": "text",
                    "text": """Extract all marks from this marksheet image. 
                    
Return ONLY a valid JSON object (no markdown, no explanation) with these fields:
{
    "student_name": "Name of the student",
    "roll_number": "Roll number if present",
    "class": "Class/Grade if present",
    "school": "School/College name if present",
    "exam": "Exam name if present",
    "subjects": [
        {
            "subject_name": "Subject name",
            "marks_obtained": number,
            "max_marks": number
        }
    ],
    "total_marks_obtained": number,
    "total_max_marks": number,
    "percentage": number,
    "grade": "Grade if present",
    "result": "Pass/Fail if present"
}

If any field is not found in the image, use null for that field."""
                }
            ]
        }]
    )
    
    return response.content[0].text


# API Key input (in sidebar)
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    api_key = st.text_input(
        "Anthropic API Key",
        type="password",
        placeholder="sk-ant-api03-...",
        help="Get your API key from console.anthropic.com"
    )
    
    st.markdown("---")
    st.markdown("### 💡 How to use")
    st.markdown("""
    1. Enter your Anthropic API key
    2. Upload a marksheet image
    3. Click 'Extract Marks'
    4. Download JSON or view results
    """)
    
    st.markdown("---")
    st.markdown("### 📊 Supported Formats")
    st.markdown("JPG, JPEG, PNG, GIF, WEBP")


# Main content
col1, col2 = st.columns([1, 1])

with col1:
    st.markdown("### 📤 Upload Marksheet")
    uploaded_file = st.file_uploader(
        "Choose an image file",
        type=['jpg', 'jpeg', 'png', 'gif', 'webp'],
        help="Upload a clear image of the marksheet"
    )

with col2:
    if uploaded_file:
        st.markdown("### 🖼️ Preview")
        st.image(uploaded_file, use_container_width=True)

# Process button
if uploaded_file and api_key:
    if st.button("🚀 Extract Marks", use_container_width=True):
        with st.spinner("🔍 Analyzing marksheet..."):
            try:
                # Get image bytes and media type
                image_bytes = uploaded_file.getvalue()
                media_type = get_media_type(uploaded_file.name)
                
                # Extract marks
                result = extract_marks(image_bytes, media_type, api_key)
                
                # Parse JSON
                # Remove markdown code blocks if present
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
                
            except json.JSONDecodeError as e:
                st.error(f"Failed to parse response as JSON: {e}")
                st.code(result)
            except anthropic.APIError as e:
                st.error(f"API Error: {e}")

elif uploaded_file and not api_key:
    st.warning("⚠️ Please enter your Anthropic API key in the sidebar")

# Display results
if 'extracted_data' in st.session_state:
    data = st.session_state['extracted_data']
    
    st.markdown("---")
    st.markdown("## 📋 Extracted Results")
    
    # Student info card
    st.markdown(f"""
    <div class="result-card">
        <h3 style="margin:0; color:#1e3a5f;">👤 {data.get('student_name', 'N/A')}</h3>
        <p style="margin:0.5rem 0 0 0; color:#64748b;">
            Roll No: {data.get('roll_number', 'N/A')} | 
            {data.get('school', 'N/A')}
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Stats row
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"""
        <div class="stat-box">
            <div class="stat-number">{data.get('total_marks_obtained', 'N/A')}/{data.get('total_max_marks', 'N/A')}</div>
            <div class="stat-label">Total Marks</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        percentage = data.get('percentage', 0)
        st.markdown(f"""
        <div class="stat-box">
            <div class="stat-number">{percentage}%</div>
            <div class="stat-label">Percentage</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        result = data.get('result', 'N/A')
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
    
    # Download buttons
    st.markdown("### 💾 Download Data")
    col1, col2 = st.columns(2)
    
    with col1:
        st.download_button(
            label="📥 Download JSON",
            data=st.session_state['raw_json'],
            file_name=f"{data.get('student_name', 'marksheet').replace(' ', '_')}.json",
            mime="application/json",
            use_container_width=True
        )
    
    with col2:
        if data.get('subjects'):
            csv = subjects_df.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"{data.get('student_name', 'marksheet').replace(' ', '_')}.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    # Raw JSON expander
    with st.expander("🔍 View Raw JSON"):
        st.code(st.session_state['raw_json'], language='json')

# Footer
st.markdown("""
<div class="footer">
    <p>Built for Canada Nagarathar Sangam - Education Committee</p>
</div>
""", unsafe_allow_html=True)

