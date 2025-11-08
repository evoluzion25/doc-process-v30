"""
Gemini Pro 2.5 Transcript Improvement Script
Improves raw transcript formatting to match professional court transcript standards
"""

import os
import sys
from pathlib import Path
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

def improve_transcript(reference_path, raw_path, output_path):
    """
    Use Gemini Pro 2.5 to improve transcript formatting
    
    Args:
        reference_path: Path to properly formatted reference transcript
        raw_path: Path to raw transcript needing improvement
        output_path: Path to save improved transcript
    """
    secrets = load_secrets()
    genai.configure(api_key=secrets['GOOGLEAISTUDIO_API_KEY'])
    
    # Read files
    with open(reference_path, 'r', encoding='utf-8') as f:
        reference_text = f.read()
    
    with open(raw_path, 'r', encoding='utf-8') as f:
        raw_text = f.read()
    
    # Create prompt
    prompt = f"""You are a professional court transcript formatter. Your task is to improve a raw audio transcription to match the formatting and quality of professional court transcripts.

REFERENCE TRANSCRIPT (proper format):
{reference_text[:5000]}

RAW TRANSCRIPT (needs improvement):
{raw_text}

INSTRUCTIONS:
1. Preserve ALL line numbers exactly as they are - they are essential for legal citations
2. Fix speaker attribution errors (e.g., "The Court:" vs unclear labels)
3. Correct obvious transcription errors while maintaining the actual spoken words
4. Improve punctuation and capitalization
5. Format dialogue consistently with proper indentation
6. Ensure proper page breaks and page numbering
7. Maintain the header structure exactly as shown in reference
8. Keep all metadata sections (document info, table of contents, etc.)
9. Fix run-on sentences and unclear speaker transitions
10. Do NOT add content that wasn't spoken
11. Do NOT remove any spoken content
12. Ensure speaker labels are clear: "The Court:", "Mr. Ryan:", "Mr. Reedy:", "The Clerk:"

OUTPUT REQUIREMENTS:
- Output the complete improved transcript
- Preserve the exact line numbering system
- Use the same header/footer format as the reference
- Maintain professional court transcript formatting throughout
- Keep all page markers [Page X BEGIN] and [Page X END]

Generate the complete improved transcript now:
"""
    
    # Configure model
    model = genai.GenerativeModel(
        model_name='gemini-2.0-flash-exp',
        generation_config={
            'temperature': 0.1,  # Low temperature for accuracy
            'top_p': 0.95,
            'top_k': 40,
            'max_output_tokens': 8192,
        }
    )
    
    print("Processing transcript with Gemini Pro 2.5...")
    print(f"Reference: {reference_path}")
    print(f"Raw input: {raw_path}")
    print(f"Output: {output_path}")
    print("\nSending to Gemini API...")
    
    # Generate improved transcript
    response = model.generate_content(prompt)
    improved_text = response.text
    
    # Save output
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(improved_text)
    
    print(f"\nImproved transcript saved to: {output_path}")
    print(f"Output size: {len(improved_text)} characters")
    
    return improved_text

if __name__ == "__main__":
    reference = r"E:\01_prjct_active\03_reedy-v-fremont_v1\04_documents\01_fremont\09_9c1_23-0406-ck\04_Hearings\x2_cleaned\20250925_9c1_Hearing_o_g1.txt"
    raw = r"E:\01_prjct_active\03_reedy-v-fremont_v1\04_documents\01_fremont\09_9c1_23-0406-ck\04_Hearings\x2_cleaned\20251105_9c1_Hearing_o_g1_1.txt"
    output = r"E:\01_prjct_active\03_reedy-v-fremont_v1\04_documents\01_fremont\09_9c1_23-0406-ck\04_Hearings\x2_cleaned\20251105_9c1_Hearing_o_g1_1_2.txt"
    
    improve_transcript(reference, raw, output)
