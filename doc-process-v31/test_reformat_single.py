"""Test reformatting a single file"""
from pathlib import Path
import os
import sys
import re
import google.generativeai as genai

# Load secrets
def load_secrets():
    secrets = {}
    secrets_file = Path('E:/00_dev_1/01_secrets/secrets_global')
    with open(secrets_file, 'r') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, val = line.strip().split('=', 1)
                secrets[key] = val.strip('"')
    return secrets

secrets = load_secrets()
GEMINI_API_KEY = secrets.get('GOOGLEAISTUDIO_API_KEY', '')
MODEL_NAME = "gemini-2.5-pro"
MAX_OUTPUT_TOKENS = 65536

# Import chunking function from main script
sys.path.insert(0, str(Path(__file__).parent))
from doc_process_v31 import _chunk_body_by_pages

def format_single_file_test(root_dir, base_name):
    """Format a single file for testing"""
    print(f"[START] Reformatting: {base_name}")
    
    convert_dir = root_dir / "04_doc-convert"
    format_dir = root_dir / "05_doc-format"
    
    convert_file = convert_dir / f"{base_name}_c.txt"
    formatted_file = format_dir / f"{base_name}_v31.txt"
    
    if not convert_file.exists():
        print(f"[ERROR] Converted file not found: {convert_file}")
        return
    
    # Read input text
    with open(convert_file, 'r', encoding='utf-8') as f:
        full_text = f.read()
    
    print(f"[INFO] Read {len(full_text)} characters from convert file")
    
    # Extract header, body, footer
    body_start = full_text.find("BEGINNING OF PROCESSED DOCUMENT")
    footer_start = full_text.find("=====================================================================\nEND OF PROCESSED DOCUMENT")
    
    if body_start < 0 or footer_start < 0:
        print(f"[ERROR] Template markers not found")
        return
    
    # Skip past the BEGINNING marker and separator line
    body_start_line = full_text.find("\n", body_start + len("BEGINNING OF PROCESSED DOCUMENT"))
    body_start_line = full_text.find("\n", body_start_line + 1)  # Skip the === line
    body_start_content = body_start_line + 1
    
    header = full_text[:body_start_content]
    raw_body = full_text[body_start_content:footer_start].strip()
    footer = full_text[footer_start:]
    
    print(f"[INFO] Extracted body: {len(raw_body)} characters")
    
    # Count pages
    page_count = len(re.findall(r'\[BEGIN PDF Page \d+\]', raw_body))
    print(f"[INFO] Document has {page_count} pages")
    
    # Initialize Gemini
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    
    # Use EXACT v31 prompt
    prompt = """You are correcting OCR output for a legal document. Your task is to:
1. Fix OCR errors and preserve legal terminology
2. CRITICAL: Preserve ALL page markers EXACTLY as they appear: '[BEGIN PDF Page N]' with blank lines before and after
3. NEVER remove or modify page markers, especially [BEGIN PDF Page 1] - it MUST be preserved
4. Format with lines under 65 characters and proper paragraph breaks
5. Render logo/header text on SINGLE lines (e.g., "MERRY FARNEN & RYAN" not multi-line)
6. Use standard bullet points (•) not filled circles (⚫)
7. Use full forwarded message marker: "---------- Forwarded message ---------"
8. Return only the corrected text with ALL page markers intact

IMPORTANT: The first page marker [BEGIN PDF Page 1] must appear at the start of the document body. Do not remove it."""
    
    print(f"[INFO] Sending to Gemini...")
    
    # Process
    response = model.generate_content(
        prompt + "\n\n" + raw_body,
        generation_config=genai.types.GenerationConfig(
            temperature=0.1,
            max_output_tokens=MAX_OUTPUT_TOKENS
        )
    )
    
    cleaned_body = response.text.strip()
    print(f"[INFO] Received {len(cleaned_body)} characters from Gemini")
    
    # Check if page markers preserved
    markers_in = len(re.findall(r'\[BEGIN PDF Page \d+\]', raw_body))
    markers_out = len(re.findall(r'\[BEGIN PDF Page \d+\]', cleaned_body))
    print(f"[INFO] Page markers: input={markers_in}, output={markers_out}")
    
    # Reassemble
    if not header.endswith("\n\n"):
        header = header.rstrip() + "\n\n"
    
    final_text = header + cleaned_body + "\n\n" + footer
    
    # Save
    with open(formatted_file, 'w', encoding='utf-8') as f:
        f.write(final_text)
    
    print(f"[OK] Saved to: {formatted_file}")
    print(f"[OK] Final size: {len(final_text)} characters")

# Run test
root_dir = Path('G:/Shared drives/12 - legal/a0_fremont_lg/_reedy-v-fremont_all/05_evidence/01_fremont/09_9c1_23-0406-ck/01_Plaintiff-fic')
base_name = '20230906_9c1_FIC_Amended_Petition_No_Coverage'

format_single_file_test(root_dir, base_name)
