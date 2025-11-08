#!/usr/bin/env python3
"""Check if page 1 title is being captured by OCR"""
import fitz
from pathlib import Path

input_pdf = Path(r"G:\Shared drives\12 - legal\a0_fremont_lg\_reedy-v-fremont_all\05_evidence\01_fremont\09_9c1_23-0406-ck\09_Pleadings_plaintiff\02_doc-renamed\20230906_9c1_FIC_Amended_Petition_No_Coverage_r.pdf")

print("="*70)
print("PAGE 1 TITLE CHECK")
print("="*70)

doc = fitz.open(input_pdf)
page = doc[0]

print("\n--- RAW TEXT EXTRACTION (first 1500 chars) ---")
text = page.get_text()
print(text[:1500])

print("\n--- TEXT BLOCKS (showing position and content) ---")
blocks = page.get_text("blocks")
print(f"Total blocks: {len(blocks)}\n")

for i, block in enumerate(blocks):
    x0, y0, x1, y1, text_content, block_no, block_type = block
    print(f"Block {i}:")
    print(f"  Position: ({x0:.1f}, {y0:.1f}) to ({x1:.1f}, {y1:.1f})")
    print(f"  Height from top: {y0:.1f} pts")
    print(f"  Content: {text_content.strip()[:100]}")
    print()

print("\n--- SEARCHING FOR TITLE ---")
if "FREMONT INSURANCE COMPANY'S AMENDED PETITION" in text.upper():
    print("✓ TITLE FOUND in extracted text")
else:
    print("✗ TITLE MISSING from extracted text")
    print("\nLikely causes:")
    print("1. Title may be an image/graphic, not text")
    print("2. Title in a header area that PyMuPDF doesn't extract")
    print("3. Title uses special encoding or non-standard font")

doc.close()

print("\n" + "="*70)
print("Recommendation: Check if title appears in OCR'd output")
print("="*70)
