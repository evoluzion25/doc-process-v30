#!/usr/bin/env python3
"""
Test script: Process ONE file and validate OCR text layer
"""
import sys
from pathlib import Path

# Import from main script (rename with underscores)
import importlib.util
spec = importlib.util.spec_from_file_location("doc_process_v31", Path(__file__).parent / "doc-process-v31.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

process_pdf_clean = module.process_pdf_clean
test_pdf_text_extraction = module.test_pdf_text_extraction

def test_single_file():
    # Test file
    test_file = Path("G:/Shared drives/12 - legal/a0_fremont_lg/_reedy-v-fremont_all/05_evidence/01_fremont/09_9c1_23-0406-ck/09_Pleadings_plaintiff/02_doc-renamed/20230906_9c1_FIC_Amended_Petition_No_Coverage_r.pdf")
    output_dir = Path("G:/Shared drives/12 - legal/a0_fremont_lg/_reedy-v-fremont_all/05_evidence/01_fremont/09_9c1_23-0406-ck/09_Pleadings_plaintiff/03_doc-clean")
    
    print("\n" + "="*80)
    print("SINGLE FILE OCR TEST")
    print("="*80)
    print(f"\nInput: {test_file.name}")
    print(f"Size: {test_file.stat().st_size / (1024*1024):.1f} MB")
    
    # Delete existing output
    output_file = output_dir / f"{test_file.stem.replace('_r', '_o')}.pdf"
    if output_file.exists():
        output_file.unlink()
        print(f"\nDeleted existing output: {output_file.name}")
    
    # Process
    print("\n" + "-"*80)
    print("PROCESSING...")
    print("-"*80)
    result = process_pdf_clean(test_file, output_dir)
    
    print("\n" + "-"*80)
    print("RESULTS")
    print("-"*80)
    print(f"Status: {result.status}")
    if result.error:
        print(f"Error: {result.error}")
    
    # Test text extraction
    if output_file.exists():
        print(f"\nOutput file: {output_file.name}")
        print(f"Output size: {output_file.stat().st_size / (1024*1024):.1f} MB")
        
        print("\n" + "-"*80)
        print("TEXT EXTRACTION TEST")
        print("-"*80)
        has_text, sample, pages = test_pdf_text_extraction(output_file)
        print(f"Pages: {pages}")
        print(f"Has text layer: {'YES' if has_text else 'NO'}")
        
        if has_text:
            print(f"\nText sample (first 500 chars):")
            print("-" * 40)
            print(sample)
            print("-" * 40)
            print("\n✓ SUCCESS: OCR text layer created")
        else:
            print("\n✗ FAILED: No selectable text found")
            print(f"Error/Sample: {sample}")
    else:
        print("\n✗ FAILED: Output file not created")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    test_single_file()
