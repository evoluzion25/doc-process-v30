import PyPDF2

pdf = PyPDF2.PdfReader(open('E:/00_dev_1/test_simple_force_ocr.pdf', 'rb'))
text = pdf.pages[0].extract_text()

print("=== FULL PAGE 1 TEXT ===\n")
print(text)

print("\n\n=== SEARCH FOR HEADER ===")
if "AMENDED" in text:
    print("[FOUND] 'AMENDED' appears in page 1")
else:
    print("[NOT FOUND] 'AMENDED' does NOT appear in page 1")
    
if "PETITION" in text:
    print("[FOUND] 'PETITION' appears in page 1")
else:
    print("[NOT FOUND] 'PETITION' does NOT appear in page 1")
