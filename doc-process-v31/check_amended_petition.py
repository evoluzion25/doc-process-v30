"""Check if the Amended Petition PDF has searchable text in the header"""
import fitz

pdf_path = r"G:\Shared drives\12 - legal\a0_fremont_lg\_reedy-v-fremont_all\05_evidence\01_fremont\09_9c1_23-0406-ck\09_Pleadings_plaintiff\03_doc-clean\20230906_9c1_FIC_Amended_Petition_No_Coverage_o.pdf"

doc = fitz.open(pdf_path)
page1 = doc[0]
text = page1.get_text()

print(f"Page 1 has {len(text)} characters")
print("\n" + "=" * 80)
print("FIRST 800 CHARACTERS:")
print("=" * 80)
print(text[:800])
print("=" * 80)

# Check for key terms
key_terms = ["AMENDED PETITION", "FREMONT INSURANCE", "INSURANCE COMPANY"]
print("\nKEY TERMS CHECK:")
for term in key_terms:
    if term in text:
        print(f"  ✓ '{term}' FOUND")
    else:
        print(f"  ✗ '{term}' NOT FOUND")

doc.close()
