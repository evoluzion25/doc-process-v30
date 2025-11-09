"""Compare page sizes between original and PIL-processed PDF"""
import fitz

original = r"G:\Shared drives\12 - legal\a0_fremont_lg\_reedy-v-fremont_all\05_evidence\01_fremont\09_9c1_23-0406-ck\09_Pleadings_plaintiff\02_doc-renamed\20230906_9c1_FIC_Amended_Petition_No_Coverage_r.pdf"
processed = r"G:\Shared drives\12 - legal\a0_fremont_lg\_reedy-v-fremont_all\05_evidence\01_fremont\09_9c1_23-0406-ck\09_Pleadings_plaintiff\03_doc-clean\20230906_9c1_FIC_Amended_Petition_No_Coverage_o.pdf"

doc1 = fitz.open(original)
doc2 = fitz.open(processed)

print("\n=== PDF PAGE SIZE COMPARISON ===\n")
print("Original PDF:")
print(f"  Page size: {doc1[0].rect.width:.1f} x {doc1[0].rect.height:.1f} points")
print(f"  DPI equivalent: {doc1[0].rect.width/8.5:.0f} DPI (width)")

print("\nProcessed PDF (PIL preprocessing):")
print(f"  Page size: {doc2[0].rect.width:.1f} x {doc2[0].rect.height:.1f} points")
print(f"  DPI equivalent: {doc2[0].rect.width/8.5:.0f} DPI (width)")

ratio = doc1[0].rect.width / doc2[0].rect.width
print(f"\n[ISSUE] Page size ratio: {ratio:.2f}x")
print(f"  Processed PDF is {100/ratio:.1f}% of original size")
print(f"  User needs to zoom {ratio*100:.0f}% to match original")

doc1.close()
doc2.close()
