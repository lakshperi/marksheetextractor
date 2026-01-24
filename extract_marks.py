#!/usr/bin/env python3
"""
Marksheet Marks Extractor using Claude Vision API
Usage: python extract_marks.py <image_or_pdf_path>
Supports: JPG, JPEG, PNG, GIF, WEBP, PDF
"""

import anthropic
import base64
import sys
import json
import os

# Try to import PyMuPDF for PDF support
try:
    import fitz  # PyMuPDF
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False


def pdf_to_image(pdf_path):
    """Convert first page of PDF to image bytes."""
    if not PDF_SUPPORT:
        print("Error: PyMuPDF not installed. Run: pip install PyMuPDF")
        sys.exit(1)
    
    pdf_document = fitz.open(pdf_path)
    page = pdf_document[0]  # First page
    mat = fitz.Matrix(2, 2)  # 2x zoom for better quality
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    pdf_document.close()
    return img_bytes


def extract_marks_with_ai(file_path):
    """Extract marks from a marksheet image or PDF using Claude Vision API."""
    
    # Check if file exists
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    
    # Determine file type and get image data
    ext = file_path.lower().split('.')[-1]
    
    if ext == 'pdf':
        # Convert PDF to image
        print("Converting PDF to image...")
        image_data = base64.standard_b64encode(pdf_to_image(file_path)).decode("utf-8")
        media_type = "image/png"
    else:
        # Handle image files
        media_types = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'webp': 'image/webp'
        }
        media_type = media_types.get(ext, 'image/jpeg')
        
        # Read and encode the image
        with open(file_path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")
    
    # Create Anthropic client (uses ANTHROPIC_API_KEY env variable)
    client = anthropic.Anthropic()
    
    # Send request to Claude
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
    "school": "School name if present",
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


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_marks.py <image_or_pdf_path>")
        print("Example: python extract_marks.py marksheet.jpg")
        print("         python extract_marks.py marksheet.pdf")
        print("\nSupported formats: JPG, JPEG, PNG, GIF, WEBP, PDF")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    print(f"Processing: {file_path}")
    print("-" * 50)
    
    try:
        result = extract_marks_with_ai(file_path)
        
        # Try to parse and pretty-print the JSON
        try:
            parsed = json.loads(result)
            print(json.dumps(parsed, indent=2))
        except json.JSONDecodeError:
            # If it's not valid JSON, print raw response
            print(result)
            
    except anthropic.APIError as e:
        print(f"API Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
