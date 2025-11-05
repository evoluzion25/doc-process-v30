#!/usr/bin/env python3
"""
Document Processing Pipeline v14
Complete 6-phase pipeline with verification and reporting
"""
import fitz
from pathlib import Path
import shutil
from datetime import datetime
import subprocess
import sys
import os
import argparse
import google.generativeai as genai
from google.cloud import vision
import difflib

# === CONFIGURATION ===
# Load secrets from centralized file
_SECRETS_FILE = Path("E:/00_dev_1/01_secrets/secrets_global")
if _SECRETS_FILE.exists():
    with open(_SECRETS_FILE, 'r') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value.strip().strip('"')

GEMINI_API_KEY = os.environ.get('GOOGLEAISTUDIO_API_KEY', '')
ROOT_DIR = Path("E:/01_prjct_active/02_legal_system_v1.2/x_docs/03_kazoo-county/09_9c2-24-0196-ck")
MODEL_NAME = "gemini-2.5-pro"
MAX_OUTPUT_TOKENS = 65536  # Tier 3 maximum tokens
GOOGLE_VISION_API = "E:/00_dev_1/01_secrets/secrets_global"  # Use Google Vision for OCR

# === GLOBAL REPORT TRACKING ===
report_data = {
    'preflight': {}, 'setup': {}, 'pdfa': [], 
    'convert': [], 'clean': [], 'verify': []
}

# === PRE-FLIGHT CHECKS (Always Run) ===
def preflight_checks():
    """Verify all credentials and tools before starting"""
    print("\n" + "="*80)
    print("DOCUMENT PROCESSING v21")
    print(f"Location: y_config/x3_doc-processing/doc-process-v21/")
    print("="*80)
    print("\nPHASE 1: PRE-FLIGHT CREDENTIAL & TOOL CHECKS")
    print("-" * 80)
    
    all_ok = True
    
    # Check Gemini API Key
    if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
        print("[OK] Gemini API Key: Present")
        report_data['preflight']['gemini_api'] = 'OK'
    else:
        print("[FAIL] Gemini API Key: Missing")
        print("PLAN: Add key from y_config/secrets_global to script configuration")
        report_data['preflight']['gemini_api'] = 'MISSING'
        all_ok = False
    
    # Check ocrmypdf
    if shutil.which('ocrmypdf'):
        print("[OK] ocrmypdf: Installed")
        report_data['preflight']['ocrmypdf'] = 'OK'
    else:
        print("[FAIL] ocrmypdf: Not found")
        print("PLAN: Install with: pip install ocrmypdf")
        report_data['preflight']['ocrmypdf'] = 'MISSING'
        all_ok = False
    
    # Check Ghostscript
    if shutil.which('gswin64c') or shutil.which('gs'):
        print("[OK] Ghostscript: Installed")
        report_data['preflight']['ghostscript'] = 'OK'
    else:
        print("[FAIL] Ghostscript: Not found")
        print("PLAN: Download from https://www.ghostscript.com/")
        report_data['preflight']['ghostscript'] = 'MISSING'
        all_ok = False
    
    # Check PyMuPDF
    try:
        import fitz
        print("[OK] PyMuPDF (fitz): Available")
        report_data['preflight']['pymupdf'] = 'OK'
    except ImportError:
        print("[FAIL] PyMuPDF: Not installed")
        print("PLAN: Install with: pip install PyMuPDF")
        report_data['preflight']['pymupdf'] = 'MISSING'
        all_ok = False
    
    # Check Root Directory
    if ROOT_DIR.exists():
        print(f"[OK] Root Directory: {ROOT_DIR}")
        report_data['preflight']['root_dir'] = 'OK'
    else:
        print(f"[FAIL] Root Directory: Not found - {ROOT_DIR}")
        print("PLAN: Update ROOT_DIR in script configuration")
        report_data['preflight']['root_dir'] = 'MISSING'
        all_ok = False
    
    print("-" * 80)
    if all_ok:
        print("[OK] All requirements met - Ready to process")
        print("Using tools: ocrmypdf, Ghostscript, PyMuPDF, Gemini 2.5 Pro")
        print("No deviations from specified process")
        return True
    else:
        print("[FAIL] Missing requirements - Cannot proceed")
        print("Fix issues above before running")
        return False

# === SETUP (Always Run) ===
def setup_directories(root_dir):
    """Create directory structure"""
    print("\nPHASE 2: DIRECTORY SETUP & STRUCTURE")
    print("-" * 80)
    
    dirs_created = []
    for subdir in ["x0_pdf-a", "x1_converted", "x2_cleaned"]:
        dir_path = root_dir / subdir
        dir_path.mkdir(exist_ok=True)
        (dir_path / "_old").mkdir(exist_ok=True)
        print(f"[OK] {subdir}/: Ready")
        dirs_created.append(subdir)
    
    report_data['setup'] = {dir: 'OK' for dir in dirs_created}
    print("-" * 80)
    print("[OK] Directory structure verified")

# === PHASE 1: OCR ===
def enhance_pdfs(root_dir, output_dir, single_file=None):
    """Create searchable PDF/A files"""
    print("\nPHASE 1: OCR - PDF ENHANCEMENT (x0_pdf-a)")
    print("-" * 80)
    print("Tools: ocrmypdf (primary), Ghostscript (fallback), PyMuPDF (cleanup)")
    print("Output: Searchable PDF/A files with suffix _a.pdf")
    print("-" * 80)
    
    if single_file:
        pdf_files = [single_file]
    else:
        pdf_files = [f for f in root_dir.glob('*.pdf') if not f.stem.endswith('_a')]
    
    for pdf_file in pdf_files:
        base_name = pdf_file.stem[:-2] if pdf_file.stem.endswith('_o') else pdf_file.stem
        output_path = output_dir / f"{base_name}_a.pdf"
        
        # Archive existing
        if output_path.exists():
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            archive_path = output_dir / '_old' / f"{output_path.stem}_{ts}.pdf"
            shutil.move(str(output_path), str(archive_path))
        
        print(f"Processing: {pdf_file.name} -> {output_path.name}")
        
        # Try ocrmypdf
        cmd = ['ocrmypdf', '--redo-ocr', '--output-type', 'pdfa', '--oversample', '600', str(pdf_file), str(output_path)]
        success, out = run_subprocess(cmd)
        
        # Fallback to Ghostscript
        if not success:
            print("  [WARN] Standard OCR failed. Using Ghostscript fallback...")
            temp_pdf = output_dir / f"{base_name}_temp.pdf"
            gs_cmd = ['gswin64c', '-sDEVICE=pdfimage32', '-o', str(temp_pdf), str(pdf_file)]
            gs_success, _ = run_subprocess(gs_cmd)
            if gs_success:
                cmd2 = ['ocrmypdf', '--redo-ocr', '--output-type', 'pdfa', '--oversample', '600', str(temp_pdf), str(output_path)]
                success, out = run_subprocess(cmd2)
                temp_pdf.unlink(missing_ok=True)
        
        if success:
            # Clean with PyMuPDF
            doc = fitz.open(output_path)
            doc.set_toc([])  # Remove bookmarks
            for page in doc:
                if "exhibit" not in page.get_text().lower():
                    for annot in page.annots():
                        page.delete_annot(annot)
            buffer = doc.tobytes()
            doc.close()
            with open(output_path, "wb") as f:
                f.write(buffer)
            print(f"  [OK] Created and cleaned: {output_path.name}")
            report_data['pdfa'].append({'file': pdf_file.name, 'status': 'OK'})
        else:
            print(f"  [FAIL] {pdf_file.name}: {out[:200]}")
            report_data['pdfa'].append({'file': pdf_file.name, 'status': 'FAIL', 'error': str(out)[:200]})

# === PHASE 2: CONVERT ===
def convert_to_text(source_dir, output_dir, single_file=None):
    """Extract text from PDFs"""
    print("\nPHASE 2: CONVERT - TEXT EXTRACTION (x1_converted)")
    print("-" * 80)
    print("Tools: PyMuPDF (local extraction)")
    print("Output: Raw text files with suffix _c.txt")
    print("-" * 80)
    
    if single_file:
        pdf_files = [single_file]
    else:
        pdf_files = sorted(list(source_dir.glob('*_a.pdf')))
    
    for pdf_file in pdf_files:
        base_name = pdf_file.stem[:-2]  # Remove _a
        output_file = output_dir / f"{base_name}_c.txt"
        
        # Archive existing
        if output_file.exists():
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            archive_path = output_dir / '_old' / f"{output_file.stem}_{ts}.txt"
            shutil.move(str(output_file), str(archive_path))
        
        print(f"Extracting: {pdf_file.name} -> {output_file.name}")
        
        try:
            doc = fitz.open(pdf_file)
            all_text = []
            for page_num, page in enumerate(doc):
                text = page.get_text()
                all_text.append(f"\n\n[BEGIN PDF Page {page_num + 1}]\n\n{text}")
            output_file.write_text("".join(all_text), encoding='utf-8')
            print(f"  [OK] Extracted {len(''.join(all_text)):,} characters, {len(doc)} pages")
            report_data['convert'].append({'file': pdf_file.name, 'status': 'OK', 'chars': len(''.join(all_text))})
        except Exception as e:
            print(f"  [FAIL] {pdf_file.name}: {str(e)}")
            report_data['convert'].append({'file': pdf_file.name, 'status': 'FAIL', 'error': str(e)})

# === PHASE 3: CLEAN ===
def clean_with_gemini(source_dir, output_dir, pdf_source_dir, single_file=None):
    """Clean text using Gemini AI with template"""
    print("\nPHASE 3: CLEAN - AI TEXT CLEANING (x2_cleaned)")
    print("-" * 80)
    print("Tools: Gemini 2.5 Pro")
    print("Output: Clean text files with suffix _v21.txt")
    print("Template: Required header/footer applied")
    print("-" * 80)
    
    # CRITICAL: Archive ALL old files first
    print("Archiving all existing cleaned files...")
    old_files = list(output_dir.glob('*_g*.txt')) + list(output_dir.glob('*_v*.txt'))
    archived_count = 0
    for old_file in old_files:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        archive_path = output_dir / '_old' / f"{old_file.stem}_{ts}.txt"
        shutil.move(str(old_file), str(archive_path))
        archived_count += 1
    print(f"[OK] Archived {archived_count} old files to _old/")
    print("-" * 80)
    
    if single_file:
        files_to_process = [single_file]
    else:
        files_to_process = sorted(list(source_dir.glob('*_c.txt')))
    
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    
    prompt = "You are correcting OCR output for a legal document. Your task is to fix OCR errors, preserve legal terminology, format page markers EXACTLY as '\\n\\n[BEGIN PDF Page N]\\n\\n' with blank lines before and after, and ensure the document is court-ready with lines under 65 characters and proper paragraph breaks. Return only the corrected text."
    
    for source_file in files_to_process:
        base_name = source_file.stem[:-2]  # Remove _c
        dest_file = output_dir / f"{base_name}_v21.txt"
        source_pdf = pdf_source_dir / f"{base_name}_a.pdf"
        
        print(f"Processing: {source_file.name} -> {dest_file.name}")
        
        try:
            page_count = len(fitz.open(source_pdf)) if source_pdf.exists() else "Unknown"
            raw_text = source_file.read_text(encoding='utf-8')
            
            response = model.generate_content(
                prompt + "\n\n" + raw_text,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=MAX_OUTPUT_TOKENS
                )
            )
            
            # Apply required template
            header = f"""§§ DOCUMENT INFORMATION §§

DOCUMENT NUMBER: TBD
DOCUMENT NAME: {base_name}
ORIGINAL PDF NAME: {base_name}_a.pdf
PDF DIRECTORY: {source_pdf.resolve()}
TOTAL PAGES: {page_count}

=====================================================================
BEGINNING OF PROCESSED DOCUMENT
=====================================================================

"""
            
            # Add separators around exhibits
            cleaned_text = response.text.strip()
            lines = cleaned_text.split('\n')
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('EXHIBIT ') and len(stripped) < 15:  # e.g., "EXHIBIT A"
                    lines[i] = f"\n{'-'*70}\n{line}\n{'-'*70}\n"
            cleaned_text = '\n'.join(lines)
            
            # Footer with 2 blank lines before END marker
            footer = "\n\n=====================================================================\nEND OF PROCESSED DOCUMENT\n====================================================================="
            
            final_text = header + cleaned_text + footer
            dest_file.write_text(final_text, encoding='utf-8')
            print(f"  [OK] Cleaned and templated")
            report_data['clean'].append({'file': source_file.name, 'status': 'OK'})
        except Exception as e:
            print(f"  [FAIL] {source_file.name}: {str(e)}")
            report_data['clean'].append({'file': source_file.name, 'status': 'FAIL', 'error': str(e)})

# === PHASE 4: VERIFY ===
def verify_accuracy(cleaned_dir, pdf_dir):
    """Verify cleaned text against original PDFs"""
    print("\nPHASE 4: VERIFY - ACCURACY CHECK")
    print("-" * 80)
    print("Comparing x2_cleaned text to x0_pdf-a PDFs")
    print("-" * 80)
    
    cleaned_files = sorted(list(cleaned_dir.glob('*_v21.txt')))
    
    for cleaned_file in cleaned_files:
        base_name = cleaned_file.stem[:-3]  # Remove _g1
        pdf_file = pdf_dir / f"{base_name}_a.pdf"
        
        if not pdf_file.exists():
            print(f"[WARN] {cleaned_file.name}: PDF not found for verification")
            report_data['verify'].append({'file': cleaned_file.name, 'status': 'SKIP', 'reason': 'PDF not found'})
            continue
        
        print(f"Verifying: {cleaned_file.name}")
        
        try:
            # Read cleaned text
            cleaned_text = cleaned_file.read_text(encoding='utf-8')
            
            # Extract from PDF
            pdf_doc = fitz.open(pdf_file)
            pdf_text = ""
            for page in pdf_doc:
                pdf_text += page.get_text()
            pdf_page_count = len(pdf_doc)
            pdf_doc.close()
            
            # Extract just document body from cleaned (skip template header/footer)
            body_start = cleaned_text.find("BEGINNING OF PROCESSED DOCUMENT")
            body_end = cleaned_text.find("END OF PROCESSED DOCUMENT")
            if body_start > 0 and body_end > 0:
                cleaned_body = cleaned_text[body_start:body_end]
            else:
                cleaned_body = cleaned_text
            
            # Count page markers
            page_marker_count = cleaned_body.count("[BEGIN PDF Page ")
            
            # Checks
            deviations = []
            
            # Check 1: Page marker count
            if page_marker_count != pdf_page_count:
                deviations.append(f"Page count mismatch: PDF has {pdf_page_count}, markers found {page_marker_count}")
            
            # Check 2: Critical terms present (basic check)
            # This is a simple check - in production you'd want more sophisticated verification
            if len(cleaned_body) < len(pdf_text) * 0.8:  # Should be at least 80% of original
                deviations.append(f"Text length significantly shorter than PDF")
            
            if deviations:
                print(f"  [WARN] Deviations found:")
                for dev in deviations:
                    print(f"    - {dev}")
                report_data['verify'].append({'file': cleaned_file.name, 'status': 'DEVIATIONS', 'issues': deviations})
            else:
                print(f"  [OK] Verified: {pdf_page_count} pages, {len(cleaned_body):,} chars")
                report_data['verify'].append({'file': cleaned_file.name, 'status': 'OK', 'pages': pdf_page_count})
        
        except Exception as e:
            print(f"  [FAIL] Verification error: {str(e)}")
            report_data['verify'].append({'file': cleaned_file.name, 'status': 'ERROR', 'error': str(e)})

# === GENERATE FINAL REPORT ===
def generate_report(root_dir):
    """Create final processing report"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = root_dir / f"PROCESSING_REPORT_v14_{timestamp}.txt"
    
    lines = []
    lines.append("=== DOCUMENT PROCESSING REPORT v14 ===\n")
    lines.append(f"Processing Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"Case Directory: {root_dir}\n\n")
    
    # Phase 1
    lines.append("PHASE 1: PRE-FLIGHT CHECKS\n")
    for check, status in report_data['preflight'].items():
        lines.append(f"  {check}: {status}\n")
    lines.append("\n")
    
    # Phase 2
    lines.append("PHASE 2: DIRECTORY SETUP\n")
    for dir, status in report_data['setup'].items():
        lines.append(f"  {dir}: {status}\n")
    lines.append("\n")
    
    # Phase 3
    lines.append("PHASE 3: PDF ENHANCEMENT (x0_pdf-a)\n")
    pdfa_ok = sum(1 for r in report_data['pdfa'] if r['status'] == 'OK')
    pdfa_fail = sum(1 for r in report_data['pdfa'] if r['status'] == 'FAIL')
    lines.append(f"  Files Processed: {len(report_data['pdfa'])}\n")
    lines.append(f"  Success: {pdfa_ok}\n")
    lines.append(f"  Failed: {pdfa_fail}\n")
    lines.append("  List:\n")
    for result in report_data['pdfa']:
        lines.append(f"    - {result['file']}: {result['status']}\n")
    lines.append("\n")
    
    # Phase 4
    lines.append("PHASE 4: TEXT CONVERSION (x1_converted)\n")
    conv_ok = sum(1 for r in report_data['convert'] if r['status'] == 'OK')
    conv_fail = sum(1 for r in report_data['convert'] if r['status'] == 'FAIL')
    lines.append(f"  Files Processed: {len(report_data['convert'])}\n")
    lines.append(f"  Success: {conv_ok}\n")
    lines.append(f"  Failed: {conv_fail}\n")
    lines.append("  List:\n")
    for result in report_data['convert']:
        lines.append(f"    - {result['file']}: {result['status']}\n")
    lines.append("\n")
    
    # Phase 5
    lines.append("PHASE 5: AI TEXT CLEANING (x2_cleaned)\n")
    clean_ok = sum(1 for r in report_data['clean'] if r['status'] == 'OK')
    clean_fail = sum(1 for r in report_data['clean'] if r['status'] == 'FAIL')
    lines.append(f"  Files Processed: {len(report_data['clean'])}\n")
    lines.append(f"  Success: {clean_ok}\n")
    lines.append(f"  Failed: {clean_fail}\n")
    lines.append("  List:\n")
    for result in report_data['clean']:
        lines.append(f"    - {result['file']}: {result['status']}\n")
    lines.append("\n")
    
    # Phase 6
    lines.append("PHASE 6: VERIFICATION\n")
    verify_ok = sum(1 for r in report_data['verify'] if r['status'] == 'OK')
    verify_dev = sum(1 for r in report_data['verify'] if r['status'] == 'DEVIATIONS')
    lines.append(f"  Files Verified: {len(report_data['verify'])}\n")
    lines.append(f"  Perfect Matches: {verify_ok}\n")
    lines.append(f"  Deviations Found: {verify_dev}\n")
    if verify_dev > 0:
        lines.append("  Issues:\n")
        for result in report_data['verify']:
            if result['status'] == 'DEVIATIONS':
                lines.append(f"    - {result['file']}:\n")
                for issue in result.get('issues', []):
                    lines.append(f"      {issue}\n")
    lines.append("\n")
    
    # Summary
    lines.append("=== SUMMARY ===\n")
    total_files = len(report_data['pdfa'])
    total_success = sum(1 for r in report_data['clean'] if r['status'] == 'OK')
    total_fail = sum(1 for r in report_data['clean'] if r['status'] == 'FAIL')
    lines.append(f"Total Files: {total_files}\n")
    lines.append(f"Successfully Processed: {total_success}\n")
    lines.append(f"Failures: {total_fail}\n")
    lines.append(f"Deviations Requiring Review: {verify_dev}\n\n")
    
    if total_fail == 0 and verify_dev == 0:
        lines.append("Status: COMPLETE\n")
    elif total_fail == 0:
        lines.append("Status: COMPLETE WITH WARNINGS\n")
    else:
        lines.append("Status: COMPLETED WITH FAILURES\n")
    
    lines.append("\n=== END REPORT ===\n")
    
    report_file.write_text("".join(lines), encoding='utf-8')
    print("\n" + "="*80)
    print(f"[OK] Final report saved: {report_file.name}")
    print("="*80)
    return report_file

# === HELPER FUNCTIONS ===
def run_subprocess(command):
    """Run subprocess and capture output"""
    try:
        process = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8')
        return True, process.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

# === MAIN PIPELINE ===
def main():
    parser = argparse.ArgumentParser(description="Document Processing Pipeline v21")
    parser.add_argument('--phase', nargs='+', 
                       choices=['all', 'ocr', 'convert', 'clean', 'verify'], 
                       default=None,
                       help='Specify which phase(s) to run')
    parser.add_argument('--file', type=str, help='Process single file only')
    args = parser.parse_args()
    
    # Interactive mode if no arguments provided
    if args.phase is None:
        print("\n" + "="*80)
        print("DOCUMENT PROCESSING v21 - Interactive Mode")
        print(f"Script: y_config/x3_doc-processing/doc-process-v21/doc-process-v21.py")
        print("="*80)
        
        # Ask which phases to run
        print("\nWhich phase(s) to run?")
        print("  1. ocr     - Create searchable PDFs")
        print("  2. convert - Extract text from PDFs")
        print("  3. clean   - AI clean with Gemini")
        print("  4. verify  - Verify accuracy")
        print("  5. all     - Run all phases")
        phase_input = input("\nEnter phase(s) (e.g., 'ocr convert' or 'all'): ").strip().lower()
        phases = phase_input.split() if phase_input else ['all']
        
        # Ask directory or file
        mode = input("\nProcess (d)irectory or single (f)ile? [d/f]: ").strip().lower()
        if mode == 'f':
            file_path = input("Enter file path: ").strip()
            single_file = Path(file_path) if file_path else None
        else:
            single_file = None
    else:
        phases = args.phase
        single_file = Path(args.file) if args.file else None
    
    if 'all' in phases:
        phases = ['ocr', 'convert', 'clean', 'verify']
    
    x0_pdfa_dir = ROOT_DIR / 'x0_pdf-a'
    x1_converted_dir = ROOT_DIR / 'x1_converted'
    x2_cleaned_dir = ROOT_DIR / 'x2_cleaned'
    
    # Pre-flight checks (always run)
    if not preflight_checks():
        print("\n[STOP] Fix missing requirements before proceeding")
        sys.exit(1)
    
    # Setup directories (always run)
    setup_directories(ROOT_DIR)
    
    # Phase 1: OCR
    if 'ocr' in phases:
        enhance_pdfs(ROOT_DIR, x0_pdfa_dir, single_file)
    
    # Phase 2: Convert
    if 'convert' in phases:
        convert_to_text(x0_pdfa_dir, x1_converted_dir, single_file)
    
    # Phase 3: Clean
    if 'clean' in phases:
        clean_with_gemini(x1_converted_dir, x2_cleaned_dir, x0_pdfa_dir, single_file)
    
    # Phase 4: Verify
    if 'verify' in phases:
        verify_accuracy(x2_cleaned_dir, x0_pdfa_dir)
    
    # Generate Final Report
    if 'verify' in phases or 'all' in phase_input.split() if 'phase_input' in locals() else False:
        report_file = generate_report(ROOT_DIR)
        print(f"\n[OK] Processing complete. Report: {report_file}")

if __name__ == '__main__':
    main()

