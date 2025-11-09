import PyPDF2

output = r"E:\00_dev_1\test_simple_force_ocr.pdf"

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

has_fremont = "FREMONT INSURANCE" in page1_text
has_amended = "AMENDED PETITION" in page1_text
header_found = has_fremont and has_amended

print(f"  'FREMONT INSURANCE' found: {has_fremont}")
print(f"  'AMENDED PETITION' found: {has_amended}")
print(f"\n  [{'SUCCESS' if header_found else 'FAIL'}] Header {'FOUND' if header_found else 'NOT FOUND'}")

print("\n=== PAGE 5 VALIDATION ===")
page5_chars = pages[4][1]
print(f"  [{'SUCCESS' if page5_chars > 50 else 'FAIL'}] Page 5: {page5_chars} chars")

print("\n=== SUMMARY ===")
if header_found and page5_chars > 50:
    print("  [SUCCESS] All tests passed!")
elif header_found:
    print("  [PARTIAL] Header found but Page 5 still empty")
elif page5_chars > 50:
    print("  [PARTIAL] Page 5 has text but header missing")
else:
    print("  [FAIL] Both header and Page 5 have issues")
