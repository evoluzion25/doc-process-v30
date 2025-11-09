"""
Test script to demonstrate new verification report column group format
"""

# Sample data matching actual verification results
manifest_rows = [
    {
        'file': '20240422_9c1_FIC_Payment_to_Reedy_o.pdf',
        'pdf_pages': 2,
        'url_accessible': 'YES',
        'mb': 0.42,
        'reduction_pct': 73.2,
        'formatted_pages': 2,
        'page_match': 'YES',
        'formatted_chars': 3456,
        'page_markers_valid': 'YES',
        'content_confidence': '46%',
        'status': 'WARNING'
    },
    {
        'file': '20250904_9c1_FIC_Motion_Enter_Lost_Order_o.pdf',
        'pdf_pages': 2,
        'url_accessible': 'YES',
        'mb': 0.13,
        'reduction_pct': 82.1,
        'formatted_pages': 2,
        'page_match': 'YES',
        'formatted_chars': 1234,
        'page_markers_valid': 'NO',
        'content_confidence': '48%',
        'status': 'WARNING'
    },
    {
        'file': '20250608_9c1_RR_Motion_Expand_Record_o.pdf',
        'pdf_pages': 39,
        'url_accessible': 'YES',
        'mb': 1.89,
        'reduction_pct': 91.5,
        'formatted_pages': 39,
        'page_match': 'YES',
        'formatted_chars': 98765,
        'page_markers_valid': 'YES',
        'content_confidence': '94%',
        'status': 'OK'
    },
]

# Generate report with new format
print("DETAILED DOCUMENT COMPARISON")
print("="*180)
print("                                         |---- PDF CONVERSION ----|  |---------- TXT CONVERSION ----------|")
print(f"{'Document Name':<40} | {'Pages':<6} {'URL OK':<7} {'PDF MB':<7} {'Reduce%':<8} | {'Pages':<6} {'Match':<6} {'Chars':<10} {'Markers':<8} {'Accuracy':<9} | {'Status':<8}")
print("-"*180)

for row in manifest_rows:
    doc_name = row['file'].replace('_o.pdf', '')
    if len(doc_name) > 38:
        doc_name = doc_name[:35] + "..."
    
    # PDF Conversion columns
    pdf_pages = str(row['pdf_pages'])
    url_ok = row['url_accessible']
    pdf_mb = f"{row['mb']:.2f}"
    reduction = f"{row['reduction_pct']:.1f}%" if row['reduction_pct'] else "N/A"
    
    # TXT Conversion columns
    txt_pages = str(row['formatted_pages'])
    page_match = row['page_match']
    chars = f"{row['formatted_chars']:,}"
    markers = row['page_markers_valid']
    accuracy = row['content_confidence']
    
    status = row['status']
    
    print(f"{doc_name:<40} | {pdf_pages:<6} {url_ok:<7} {pdf_mb:<7} {reduction:<8} | {txt_pages:<6} {page_match:<6} {chars:<10} {markers:<8} {accuracy:<9} | {status:<8}")

print("\n")
print("COLUMN GROUPS:")
print("\n")
print("PDF CONVERSION (Verifies online PDF quality):")
print("  Pages: Number of pages in cleaned/OCR'd PDF")
print("  URL OK: GCS public URL accessible (YES/NO) - verifies online availability")
print("  PDF MB: File size after OCR and compression")
print("  Reduce%: Size reduction from original (compression effectiveness)")
print("\n")
print("TXT CONVERSION (Verifies text extraction accuracy):")
print("  Pages: Number of [BEGIN PDF Page N] markers in TXT")
print("  Match: YES if PDF pages = TXT page markers (no missing pages)")
print("  Chars: Total character count (verifies content was extracted)")
print("  Markers: YES if [BEGIN PDF Page 1] exists (proper page marking)")
print("  Accuracy: Content match confidence from PDF vs TXT comparison (70%+ is passing)")
print("\n")
print("Status: OK = verified, WARNING = issues found, FAILED = error\n")
