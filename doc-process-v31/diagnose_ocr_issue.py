#!/usr/bin/env python3
"""
Diagnose why Phase 3 OCR may not be making all text selectable
"""
import PyPDF2
import sys
from pathlib import Path

def analyze_pdf(pdf_path, label):
    """Analyze a PDF and report text extraction results"""
    print(f"\n{'='*60}")
    print(f"{label}: {pdf_path.name}")
    print('='*60)
    
    try:
        with open(pdf_path, 'rb') as f:
            pdf = PyPDF2.PdfReader(f)
            page_count = len(pdf.pages)
            print(f"Total pages: {page_count}")
            
            total_chars = 0
            pages_with_text = 0
            pages_without_text = 0
            
            for i in range(page_count):
                try:
                    text = pdf.pages[i].extract_text()
                    char_count = len(text.strip())
                    total_chars += char_count
                    
                    if char_count > 50:  # Threshold for "has text"
                        pages_with_text += 1
                        status = "✓ HAS TEXT"
                    else:
                        pages_without_text += 1
                        status = "✗ NO TEXT"
                    
                    print(f"  Page {i+1:2d}: {char_count:5d} chars  {status}")
                    
                    # Show sample for first page
                    if i == 0 and char_count > 0:
                        print(f"    Sample: {text[:100]!r}...")
                        
                except Exception as e:
                    print(f"  Page {i+1:2d}: ERROR - {e}")
                    pages_without_text += 1
            
            print(f"\n  Summary:")
            print(f"    Total characters: {total_chars:,}")
            print(f"    Pages with text: {pages_with_text}/{page_count}")
            print(f"    Pages without text: {pages_without_text}/{page_count}")
            
            if pages_without_text > 0:
                print(f"\n  ⚠️  WARNING: {pages_without_text} pages have no extractable text!")
                return False
            else:
                print(f"\n  ✓ All pages have extractable text")
                return True
                
    except Exception as e:
        print(f"ERROR analyzing PDF: {e}")
        return False

def main():
    input_pdf = Path(r"G:\Shared drives\12 - legal\a0_fremont_lg\_reedy-v-fremont_all\05_evidence\01_fremont\09_9c1_23-0406-ck\09_Pleadings_plaintiff\02_doc-renamed\20230906_9c1_FIC_Amended_Petition_No_Coverage_r.pdf")
    output_pdf = Path(r"G:\Shared drives\12 - legal\a0_fremont_lg\_reedy-v-fremont_all\05_evidence\01_fremont\09_9c1_23-0406-ck\09_Pleadings_plaintiff\03_doc-clean\20230906_9c1_FIC_Amended_Petition_No_Coverage_o.pdf")
    
    print("\n" + "="*60)
    print("OCR DIAGNOSTIC TEST")
    print("="*60)
    
    if not input_pdf.exists():
        print(f"ERROR: Input PDF not found: {input_pdf}")
        return
    
    if not output_pdf.exists():
        print(f"ERROR: Output PDF not found: {output_pdf}")
        print("Please run Phase 3 first to generate the output PDF")
        return
    
    # Analyze both PDFs
    input_ok = analyze_pdf(input_pdf, "INPUT PDF (before OCR)")
    output_ok = analyze_pdf(output_pdf, "OUTPUT PDF (after OCR)")
    
    # Compare results
    print(f"\n{'='*60}")
    print("DIAGNOSIS")
    print('='*60)
    
    if input_ok and output_ok:
        print("✓ Both input and output PDFs have selectable text on all pages")
        print("  Phase 3 OCR is working correctly!")
    elif not input_ok and output_ok:
        print("✓ Input had issues, but output is fully searchable")
        print("  Phase 3 OCR successfully fixed the issues!")
    elif input_ok and not output_ok:
        print("✗ Input was fine, but output lost text selectability")
        print("  Phase 3 OCR is DEGRADING text quality!")
        print("\n  Possible causes:")
        print("  1. --force-ocr is re-rendering already good text")
        print("  2. Compression is removing text layer")
        print("  3. PDF/A conversion is corrupting text")
    else:
        print("✗ Both input and output have issues")
        print("  Phase 3 OCR is not improving text extraction")
        print("\n  Possible causes:")
        print("  1. OCR engine not detecting text regions")
        print("  2. Image quality too low for OCR")
        print("  3. Wrong OCR parameters (language, DPI, etc.)")
    
    print("\nRECOMMENDATIONS:")
    print("-"*60)
    
    if not output_ok:
        print("Phase 3 needs improvement:")
        print("  1. Test with --redo-ocr instead of --force-ocr")
        print("     (preserves existing text, only OCRs image-only pages)")
        print("  2. Add --skip-text flag to avoid re-OCRing pages with text")
        print("  3. Test without compression step (STEP 4)")
        print("  4. Increase --oversample to 450 (higher quality, larger file)")
        print("  5. Add --optimize 0 to disable lossy optimizations")

if __name__ == "__main__":
    main()
