import PyPDF2
import sys

output = r"G:\Shared drives\12 - legal\a0_fremont_lg\_reedy-v-fremont_all\05_evidence\01_fremont\09_9c1_23-0406-ck\09_Pleadings_plaintiff\03_doc-clean\20230906_9c1_FIC_Amended_Petition_No_Coverage_o.pdf"

try:
    pdf = PyPDF2.PdfReader(open(output, 'rb'))
    
    print("\n=== PAGE TEXT CHARACTER COUNTS ===")
    pages = []
    for i in range(len(pdf.pages)):
        text = pdf.pages[i].extract_text().strip()
        char_count = len(text)
        pages.append((i+1, char_count))
        print(f"  Page {i+1}: {char_count} chars")
    
    print("\n=== HEADER VALIDATION ===")
    page1_text = pdf.pages[0].extract_text()
    
    # Check for header components
    has_fremont = "FREMONT INSURANCE" in page1_text
    has_amended = "AMENDED PETITION" in page1_text
    header_found = has_fremont and has_amended
    
    print(f"  'FREMONT INSURANCE' found: {has_fremont}")
    print(f"  'AMENDED PETITION' found: {has_amended}")
    print(f"\n  {'[SUCCESS]' if header_found else '[FAIL]'} Header {'FOUND' if header_found else 'NOT FOUND'} in page 1 text")
    
    print("\n=== PAGE 5 VALIDATION ===")
    page5_chars = pages[4][1]
    print(f"  {'[SUCCESS]' if page5_chars > 50 else '[FAIL]'} Page 5: {page5_chars} chars (was 0 before)")
    
    print("\n=== SUMMARY ===")
    if header_found and page5_chars > 50:
        print("  [SUCCESS] All tests passed!")
    elif header_found:
        print("  [PARTIAL] Header found but Page 5 still empty")
    elif page5_chars > 50:
        print("  [PARTIAL] Page 5 has text but header missing")
    else:
        print("  [FAIL] Both header and Page 5 have issues")
        
except Exception as e:
    print(f"[ERROR] {e}")
    sys.exit(1)
