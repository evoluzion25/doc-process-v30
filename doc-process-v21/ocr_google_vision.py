#!/usr/bin/env python3
"""
Google Vision OCR - High Quality PDF OCR
Uses Google Cloud Vision API for best-in-class OCR
"""
import os
from pathlib import Path
from google.cloud import vision
import io

# Load credentials - direct path
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "E:/00_dev_1/01_secrets/gcp-credentials.json"

# Configuration
ROOT_DIR = Path("E:/01_prjct_active/02_legal_system_v1.2/x_docs/03_kazoo-county/06_9c1-23-0406-ck/02_ROA")
OUTPUT_DIR = ROOT_DIR / "x0_pdf-a"
OUTPUT_DIR.mkdir(exist_ok=True)

def ocr_pdf_with_vision(pdf_path, output_txt_path):
    """Extract text from PDF using Google Vision API"""
    client = vision.ImageAnnotatorClient()
    
    with io.open(pdf_path, 'rb') as pdf_file:
        content = pdf_file.read()
    
    # Process PDF with Vision API
    input_config = vision.InputConfig(
        content=content,
        mime_type='application/pdf'
    )
    
    feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
    
    request = vision.AnnotateFileRequest(
        input_config=input_config,
        features=[feature]
    )
    
    response = client.batch_annotate_files(requests=[request])
    
    # Extract text from all pages
    full_text = []
    for idx, page in enumerate(response.responses[0].responses, 1):
        if page.full_text_annotation.text:
            full_text.append(f"[BEGIN PDF Page {idx}]\n\n")
            full_text.append(page.full_text_annotation.text)
            full_text.append(f"\n\n")
    
    # Save extracted text
    with open(output_txt_path, 'w', encoding='utf-8') as f:
        f.write(''.join(full_text))
    
    return len(full_text), sum(len(t) for t in full_text)

def main():
    """Process all PDFs with Google Vision OCR"""
    print("Google Vision OCR - High Quality Text Extraction")
    print("=" * 80)
    
    # Find all original PDFs
    pdf_files = list(ROOT_DIR.glob("*_o.pdf"))
    
    if not pdf_files:
        print(f"[WARN] No *_o.pdf files found in {ROOT_DIR}")
        return
    
    print(f"Found {len(pdf_files)} PDFs to process\n")
    
    for pdf_file in pdf_files:
        base_name = pdf_file.stem[:-2]  # Remove _o suffix
        output_txt = OUTPUT_DIR / f"{base_name}_a.txt"
        
        print(f"Processing: {pdf_file.name}")
        print(f"  → {output_txt.name}")
        
        try:
            pages, chars = ocr_pdf_with_vision(str(pdf_file), str(output_txt))
            print(f"  [OK] Extracted {chars:,} characters from {pages} pages\n")
        except Exception as e:
            print(f"  [FAIL] {e}\n")
    
    print("=" * 80)
    print("[DONE] Google Vision OCR complete")

if __name__ == "__main__":
    main()
