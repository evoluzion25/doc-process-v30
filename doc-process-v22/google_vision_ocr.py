#!/usr/bin/env python3
"""Google Vision OCR for problematic PDFs"""
from google.cloud import vision
from pathlib import Path
import os

# Load secrets and fix credentials path
secrets_file = Path("E:/00_dev_1/01_secrets/secrets_global")
with open(secrets_file, 'r') as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            key, value = line.strip().split('=', 1)
            os.environ[key] = value.strip('"')

# Override with correct path
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = "E:\\00_dev_1\\01_secrets\\gcp-credentials.json"

# Initialize client
client = vision.ImageAnnotatorClient()

# Target PDFs
pdf_files = [
    Path(r"E:\01_prjct_active\02_legal_system_v1.2\x_docs\03_kazoo-county\08_3c2-24-002200-ck\20240212_3c2_RR_Complaint-v1_o.pdf"),
    Path(r"E:\01_prjct_active\02_legal_system_v1.2\x_docs\03_kazoo-county\08_3c2-24-002200-ck\20240312_3c2_FIC_Impermissable-Deposition_o.pdf")
]

output_dir = Path(r"E:\01_prjct_active\02_legal_system_v1.2\x_docs\03_kazoo-county\08_3c2-24-002200-ck\x1_converted")
output_dir.mkdir(exist_ok=True)

for pdf in pdf_files:
    if not pdf.exists():
        print(f"[SKIP] {pdf.name} - not found")
        continue
        
    print(f"Processing {pdf.name}...")
    
    # Read PDF
    with open(pdf, 'rb') as f:
        content = f.read()
    
    # Process in batches of 5 pages (API limit)
    text_pages = []
    page_num = 1
    batch_size = 5
    
    while True:
        # Create request for next 5 pages
        request = vision.AnnotateFileRequest(
            input_config=vision.InputConfig(
                content=content,
                mime_type='application/pdf'
            ),
            features=[vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)],
            pages=list(range(page_num, page_num + batch_size))
        )
        
        # Process batch
        try:
            response = client.batch_annotate_files(requests=[request])
            
            # Extract text from this batch
            batch_pages = []
            for file_response in response.responses:
                for page_response in file_response.responses:
                    if page_response.full_text_annotation.text:
                        batch_pages.append(page_response.full_text_annotation.text)
            
            if not batch_pages:
                # No more pages
                break
                
            text_pages.extend(batch_pages)
            page_num += batch_size
            print(f"  Processed {len(text_pages)} pages...")
            
        except Exception as e:
            if "400" in str(e):
                # Reached end of document
                break
            raise
    
    # Save to _a.txt (converted format)
    output_path = output_dir / f"{pdf.stem.replace('_o', '_a')}.txt"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(text_pages))
    
    print(f"[OK] {output_path.name} ({len(text_pages)} pages)")

print("\n[OK] Google Vision processing complete")
