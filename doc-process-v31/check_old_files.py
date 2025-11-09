"""Check old files for text extraction quality and potential OCR issues"""
import fitz  # PyMuPDF
from pathlib import Path

base_dir = Path(r"G:\Shared drives\12 - legal\a0_fremont_lg\_reedy-v-fremont_all\05_evidence\01_fremont\09_9c1_23-0406-ck\09_Pleadings_plaintiff")
clean_dir = base_dir / "03_doc-clean"

# Files created before PIL preprocessing (Nov 8, 2025)
old_files = [
    "20240913_9c1_FIC_MSD_No_Coverage_o.pdf",
    "20230803_9c1_FIC_Accepts_Reedy_Insured_o.pdf",
    "20250225_9c1_FIC_Motion_New_Umpire_Exhibits_o.pdf",
    "20231103_9c1_FIC_Motion_Enforce_Umpire_Exhibits_o.pdf",
    "20240611_9c1_FIC_Response_Supplemental_o.pdf",
    "20241210_9c1_FIC_MSD_Supplement_2_Restraining_o.pdf",
    "20250414_9c1_FIC_Response_RR_Objection_Sanctions_o.pdf",
    "20250502_9c1_FIC_7d_Order_Altered_4_o.pdf",
    "20241118_9c1_FIC_MSD_Supplement_1_Abandonment_o.pdf",
    "20240611_9c1_FIC_Response_Combined_Motion_o.pdf"
]

print("\n=== ANALYZING OLD FILES FOR OCR QUALITY ===\n")

reprocess_needed = []

for filename in old_files:
    pdf_path = clean_dir / filename
    
    if not pdf_path.exists():
        print(f"[SKIP] {filename} - Not found")
        continue
    
    try:
        doc = fitz.open(str(pdf_path))
        num_pages = len(doc)
        
        # Check page 1 text extraction
        page1_text = doc[0].get_text()
        page1_chars = len(page1_text)
        
        # Check for empty or nearly empty pages
        empty_pages = []
        total_chars = 0
        for page_num in range(num_pages):
            text = doc[page_num].get_text()
            total_chars += len(text)
            if len(text) < 50:  # Less than 50 chars = likely OCR failure
                empty_pages.append(page_num + 1)
        
        # Calculate average chars per page
        avg_chars = total_chars / num_pages if num_pages > 0 else 0
        
        doc.close()
        
        # Determine if reprocessing needed
        needs_reprocess = False
        issues = []
        
        if page1_chars < 100:
            issues.append("Page 1 nearly empty")
            needs_reprocess = True
        
        if empty_pages:
            issues.append(f"{len(empty_pages)} empty pages: {empty_pages[:3]}")
            needs_reprocess = True
        
        if avg_chars < 500:
            issues.append(f"Low avg chars/page: {avg_chars:.0f}")
            needs_reprocess = True
        
        status = "[REPROCESS]" if needs_reprocess else "[OK]"
        issue_str = ", ".join(issues) if issues else "Good OCR quality"
        
        print(f"{status} {filename}")
        print(f"  Page 1: {page1_chars} chars | Avg: {avg_chars:.0f} chars/page | Pages: {num_pages}")
        print(f"  Issues: {issue_str}\n")
        
        if needs_reprocess:
            reprocess_needed.append(filename)
    
    except Exception as e:
        print(f"[ERROR] {filename}: {e}\n")

print(f"\n=== SUMMARY ===")
print(f"Total old files checked: {len(old_files)}")
print(f"Files needing reprocessing: {len(reprocess_needed)}")

if reprocess_needed:
    print("\n=== FILES TO REPROCESS ===")
    for f in reprocess_needed:
        print(f"  - {f}")
