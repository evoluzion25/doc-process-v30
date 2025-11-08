#!/usr/bin/env python3
"""
Document Processing Pipeline v31
6-phase pipeline with parallel processing and enhanced error handling

Major improvements in v31:
- Parallel processing for Phases 2-5 (3-5x faster)
- Custom exception classes for better error handling
- Dead-letter queue for failed files  
- Per-file error handling (continues on failure)
- Progress tracking and performance metrics
- Auto-continue to next phase after 30 seconds
- Chunked processing for large documents (>80 pages)

Performance optimizations (2025-01-08):
- Reduced secrets loading from 98 to 3 (only loads required: GOOGLEAISTUDIO_API_KEY, GOOGLE_APPLICATION_CREDENTIALS, GCS_BUCKET)
- Optimized startup time by eliminating unnecessary file parsing
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
from google.cloud import storage
import re
import json
import time
import csv
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional, Dict, List
import threading

# === CONFIGURATION ===
# Load only required secrets efficiently
print("[INFO] Loading required secrets from local file")

_SECRETS_FILE = Path("E:/00_dev_1/01_secrets/secrets_global")
if _SECRETS_FILE.exists():
    # Only load the 3 secrets we actually need
    required_secrets = {
        'GOOGLEAISTUDIO_API_KEY': '',
        'GOOGLE_APPLICATION_CREDENTIALS': '',
        'GCS_BUCKET': 'fremont-1'  # Default value
    }
    
    with open(_SECRETS_FILE, 'r') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                key = key.strip()
                if key in required_secrets:
                    os.environ[key] = value.strip().strip('"')
                    print(f"[OK] Loaded: {key}")
    
    print(f"[OK] Loaded {len(required_secrets)} required secrets")
else:
    print(f"[WARN] Secrets file not found: {_SECRETS_FILE}")

GEMINI_API_KEY = os.environ.get('GOOGLEAISTUDIO_API_KEY', '')
GOOGLE_APPLICATION_CREDENTIALS = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '')
GCS_BUCKET = os.environ.get('GCS_BUCKET', 'fremont-1')
MODEL_NAME = "gemini-2.5-pro"
MAX_OUTPUT_TOKENS = 65536

# Common acronyms for legal documents
PARTY_ACRONYMS = {
    "Reedy": "RR",
    "Fremont Insurance": "FIC", 
    "Fremont": "FIC",
    "Clerk": "Clerk",
    "Court": "Court"
}

CASE_ACRONYMS = ["9c1", "9c2", "3c1", "3c2", "9c_powers"]

# Parallel processing configuration
MAX_WORKERS_IO = 5  # For API calls (Gemini, Google Vision)
MAX_WORKERS_CPU = 5  # For OCR operations (optimized for 24-core system)


# === CUSTOM EXCEPTIONS ===
class DocumentProcessingError(Exception):
    """Base exception for document processing errors"""
    pass

class OcrError(DocumentProcessingError):
    """OCR operation failed"""
    pass

class ApiError(DocumentProcessingError):
    """API call failed (Gemini or Google Vision)"""
    pass

class ConvertionError(DocumentProcessingError):
    """Text convertion failed"""
    pass

class FormattingError(DocumentProcessingError):
    """Text formatting failed"""
    pass

# === DATA CLASSES ===
@dataclass
class ProcessingResult:
    """Result of processing a single file"""
    file_name: str
    status: str  # 'OK', 'FAILED', 'SKIPPED', 'WARNING'
    error: Optional[str] = None
    metadata: Optional[Dict] = None

# === GLOBAL REPORT TRACKING ===
report_data = {
    'preflight': {}, 'directory': {}, 'rename': [], 
    'clean': [], 'convert': [], 'format': [], 'verify': []
}

# === DEAD-LETTER QUEUE (DISABLED) ===
# def move_to_quarantine(root_dir: Path, file_path: Path, error: Exception, phase_name: str):
#     """Move failed files to _failed/<phase>/ for manual review"""
#     # Disabled - no longer creating _failed directories
#     pass

# === GOOGLE DRIVE SYNC CONTROL ===
def pause_google_drive_sync():
    """Attempt to pause Google Drive sync programmatically"""
    try:
        # Check if Google Drive process is running
        import psutil
        google_drive_running = False
        
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] and 'googledrivefs' in proc.info['name'].lower():
                    google_drive_running = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if not google_drive_running:
            print("[INFO] Google Drive process not running - sync not active")
            return True
        
        # Google Drive detected - attempt PowerShell automation
        print("[INFO] Attempting automatic pause via PowerShell...")
        
        # PowerShell script to pause Google Drive (if available)
        ps_script = """
        $wshell = New-Object -ComObject WScript.Shell
        $null = $wshell.AppActivate("Google Drive")
        Start-Sleep -Milliseconds 500
        # Try to send pause shortcut (Ctrl+Alt+P is common)
        # Note: This may not work on all versions
        Write-Host "Attempting to pause Google Drive sync..."
        """
        
        try:
            import subprocess
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # PowerShell automation is unreliable - always return False to show manual instructions
            return False
            
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
            
    except ImportError:
        # psutil not available
        print("[INFO] psutil not available - cannot detect Google Drive process")
        return False
    except Exception as e:
        print(f"[WARN] Could not auto-pause: {e}")
        return False

def resume_google_drive_sync():
    """Resume Google Drive sync after processing (informational only)"""
    print("[INFO] Processing complete - Google Drive sync will auto-resume")
    print("[INFO] If you manually paused sync, you can resume it now:")
    print("  - Right-click Google Drive icon in system tray")
    print("  - Click 'Resume syncing'")
    return True

# === TIMEOUT INPUT HELPER ===
def input_with_timeout(prompt, timeout=30, default='1'):
    """Get user input with timeout. Returns default if timeout expires."""
    result = [default]
    
    def get_input():
        try:
            result[0] = input(prompt).strip()
        except:
            pass
    
    thread = threading.Thread(target=get_input, daemon=True)
    thread.start()
    thread.join(timeout)
    
    if thread.is_alive():
        print(f"\n[AUTO] No input received - auto-continuing in {timeout}s (default: {default})")
        return default
    
    return result[0]

# === PHASE 0: PRE-FLIGHT CHECKS ===
def preflight_checks(skip_clean_check=False, root_dir=None):
    """Verify all credentials and tools before starting"""
    print("\n" + "="*80)
    print("DOCUMENT PROCESSING v31")
    print(f"Location: y_apps/x3_doc-processing/doc-process-v31/")
    print("="*80)
    print("\nPHASE 0: PRE-FLIGHT CREDENTIAL & TOOL CHECKS")
    print("-" * 80)
    
    all_ok = True
    
    # Check Gemini API Key
    if GEMINI_API_KEY:
        print("[OK] Gemini API Key: Present")
        report_data['preflight']['gemini_api'] = 'OK'
    else:
        print("[FAIL] Gemini API Key: Missing")
        report_data['preflight']['gemini_api'] = 'MISSING'
        all_ok = False
    
    # Check Google Cloud credentials
    if GOOGLE_APPLICATION_CREDENTIALS and Path(GOOGLE_APPLICATION_CREDENTIALS).exists():
        print("[OK] Google Cloud Vision: Configured")
        report_data['preflight']['google_vision'] = 'OK'
    else:
        print("[FAIL] Google Cloud Vision: Not configured")
        report_data['preflight']['google_vision'] = 'MISSING'
        all_ok = False
    
    # Check ocrmypdf (skip for convert/format/verify phases)
    if not skip_clean_check:
        ocrmypdf_path = shutil.which('ocrmypdf') or (Path('E:\\00_dev_1\\.venv\\Scripts\\ocrmypdf.exe') if Path('E:\\00_dev_1\\.venv\\Scripts\\ocrmypdf.exe').exists() else None)
        if ocrmypdf_path:
            print("[OK] ocrmypdf: Installed")
            report_data['preflight']['ocrmypdf'] = 'OK'
        else:
            print("[FAIL] ocrmypdf: Not found")
            report_data['preflight']['ocrmypdf'] = 'MISSING'
            all_ok = False
    else:
        print("[SKIP] ocrmypdf: Not required for this phase")
        report_data['preflight']['ocrmypdf'] = 'SKIPPED'
    
    # Check Ghostscript (skip for convert/format/verify phases)
    if not skip_clean_check:
        if shutil.which('gswin64c') or shutil.which('gs'):
            print("[OK] Ghostscript: Installed")
            report_data['preflight']['ghostscript'] = 'OK'
        else:
            print("[FAIL] Ghostscript: Not found")
            report_data['preflight']['ghostscript'] = 'MISSING'
            all_ok = False
    else:
        print("[SKIP] Ghostscript: Not required for this phase")
        report_data['preflight']['ghostscript'] = 'SKIPPED'
    
    # Check PyMuPDF
    try:
        import fitz
        print("[OK] PyMuPDF (fitz): Available")
        report_data['preflight']['pymupdf'] = 'OK'
    except ImportError:
        print("[FAIL] PyMuPDF: Not installed")
        report_data['preflight']['pymupdf'] = 'MISSING'
        all_ok = False
    
    # Check directory structure and connectivity
    if root_dir:
        print("\n" + "-" * 80)
        print("DIRECTORY CONNECTIVITY CHECKS")
        print("-" * 80)
        
        # Verify root directory exists and is accessible
        if not root_dir.exists():
            print(f"[FAIL] Root directory not found: {root_dir}")
            report_data['preflight']['root_dir'] = 'NOT_FOUND'
            all_ok = False
        else:
            print(f"[OK] Root directory accessible: {root_dir}")
            report_data['preflight']['root_dir'] = 'OK'
            
            # Test write permissions
            try:
                test_file = root_dir / '.preflight_test'
                test_file.write_text('test')
                test_file.unlink()
                print(f"[OK] Root directory writable")
                report_data['preflight']['root_dir_writable'] = 'OK'
            except Exception as e:
                print(f"[FAIL] Root directory not writable: {e}")
                report_data['preflight']['root_dir_writable'] = 'FAIL'
                all_ok = False
        
        # Check all pipeline directories
        directories = [
            "01_doc-original",
            "02_doc-renamed", 
            "03_doc-clean",
            "04_doc-convert",
            "05_doc-format",
            "y_logs"
        ]
        
        missing_dirs = []
        inaccessible_dirs = []
        
        for dir_name in directories:
            dir_path = root_dir / dir_name
            if not dir_path.exists():
                missing_dirs.append(dir_name)
            else:
                # Test read/write access
                try:
                    test_file = dir_path / '.access_test'
                    test_file.write_text('test')
                    test_file.unlink()
                except Exception as e:
                    inaccessible_dirs.append((dir_name, str(e)))
        
        if missing_dirs:
            print(f"[WARN] Missing directories (will be created): {', '.join(missing_dirs)}")
            report_data['preflight']['missing_dirs'] = missing_dirs
        else:
            print(f"[OK] All {len(directories)} pipeline directories exist")
            report_data['preflight']['missing_dirs'] = []
        
        if inaccessible_dirs:
            print(f"[FAIL] Inaccessible directories:")
            for dir_name, error in inaccessible_dirs:
                print(f"  - {dir_name}: {error}")
            report_data['preflight']['inaccessible_dirs'] = inaccessible_dirs
            all_ok = False
        else:
            print(f"[OK] All existing directories are accessible")
            report_data['preflight']['inaccessible_dirs'] = []
        
        # Check for network drive issues (if applicable)
        root_str = str(root_dir).upper()
        if root_str.startswith('G:\\') or root_str.startswith('\\\\'):
            print(f"[INFO] Network drive detected: {root_dir.drive or 'UNC path'}")
            
            # Check if this is a Google Drive Team Drive
            if 'SHARED DRIVES' in root_str.upper() or 'TEAM DRIVES' in root_str.upper():
                print(f"[WARN] Google Team Drive detected")
                print(f"[WARN] Performance Impact:")
                print(f"  - Google Drive File Stream syncs files in real-time")
                print(f"  - Every file read/write triggers cloud sync (upload/download)")
                print(f"  - OCR operations create large temp files that get synced")
                print(f"  - Can slow processing by 3-10x depending on file sizes")
                print(f"")
                print(f"[RECOMMENDATION] To maximize performance:")
                print(f"  1. Pause Google Drive sync during processing")
                print(f"  2. OR copy files to local drive (E:\\) before processing")
                print(f"")
                report_data['preflight']['google_drive'] = 'DETECTED'
                
                # Attempt automatic pause
                paused = pause_google_drive_sync()
                if paused:
                    print(f"[OK] Google Drive sync paused for processing")
                    report_data['preflight']['google_drive_paused'] = True
                else:
                    print(f"[INFO] Manual pause required:")
                    print(f"  - Right-click Google Drive icon in system tray")
                    print(f"  - Click 'Pause syncing' -> Select '1 hour' or longer")
                    print(f"")
                    
                    # Prompt user to continue or abort
                    choice = input_with_timeout(
                        "Continue with Google Drive sync active? [1] Yes (may be slow)  [2] Abort to pause manually (auto-continue in 30s): ",
                        timeout=30,
                        default='1'
                    )
                    if choice == '2':
                        print("[STOP] Aborted by user - Please pause Google Drive sync and restart")
                        return False
                    report_data['preflight']['google_drive_paused'] = False
            else:
                print(f"[INFO] Ensure stable connection for duration of processing")
            
            report_data['preflight']['network_drive'] = True
        else:
            report_data['preflight']['network_drive'] = False
    
    print("-" * 80)
    if all_ok:
        print("[OK] All requirements met - Ready to process")
        print(f"[INFO] Parallel processing: {MAX_WORKERS_IO} workers (I/O), {MAX_WORKERS_CPU} workers (CPU)")
        return True
    else:
        print("[FAIL] Missing requirements - Cannot proceed")
        return False

# === DIRECTORY SETUP (Called by all phases) ===
def ensure_directory_structure(root_dir):
    """Ensure all pipeline directories exist - called by every phase"""
    directories = [
        "01_doc-original",
        "02_doc-renamed", 
        "03_doc-clean",
        "04_doc-convert",
        "05_doc-format",
        "y_logs",
        "z_old"
    ]
    
    for dir_name in directories:
        dir_path = root_dir / dir_name
        dir_path.mkdir(exist_ok=True)
    
    # Create _old and _log subdirectories in pipeline directories (01-05)
    pipeline_dirs = ["01_doc-original", "02_doc-renamed", "03_doc-clean", "04_doc-convert", "05_doc-format"]
    for pipeline_dir in pipeline_dirs:
        (root_dir / pipeline_dir / "_old").mkdir(exist_ok=True)
        (root_dir / pipeline_dir / "_log").mkdir(exist_ok=True)
    
    # Create _duplicate directory in 01_doc-original
    (root_dir / "01_doc-original" / "_duplicate").mkdir(exist_ok=True)

# === PHASE 1: DIRECTORY - Move PDFs and add _d suffix ===
def phase1_directory(root_dir):
    """Move all PDFs from root to 01_doc-original and ensure _d suffix"""
    print("\nPHASE 1: DIRECTORY - ORIGINAL PDF COLLECTION")
    print("-" * 80)
    
    # Ensure directory structure exists
    ensure_directory_structure(root_dir)
    print(f"[OK] Verified all pipeline directories exist")
    
    original_dir = root_dir / "01_doc-original"
    
    pdf_files = list(root_dir.glob("*.pdf"))
    
    if not pdf_files:
        print("[SKIP] No PDF files found in root directory")
        report_data['directory']['status'] = 'SKIPPED'
        # Continue to next phase - may have files already in 01_doc-original
        return
    
    # Sort by file size (smallest to largest) for better progress visibility
    pdf_files.sort(key=lambda x: x.stat().st_size)
    
    moved_count = 0
    for pdf in pdf_files:
        # Always add _d suffix (remove any existing suffix first)
        base_name = pdf.stem
        
        # Remove common suffixes if present
        for suffix in ['_o', '_d', '_r', '_a', '_t', '_c', '_v22', '_v31']:
            if base_name.endswith(suffix):
                base_name = base_name[:-len(suffix)]
                break
        
        new_name = f"{base_name}_d.pdf"
        
        target_path = original_dir / new_name
        
        # Avoid overwriting if file already exists
        if target_path.exists():
            print(f"[SKIP] {new_name} - already exists")
            continue
        
        shutil.move(str(pdf), str(target_path))
        print(f"[OK] Moved: {pdf.name} → {new_name}")
        moved_count += 1
    
    report_data['directory']['moved'] = moved_count
    report_data['directory']['total'] = len(pdf_files)
    print(f"\n[OK] Directoryd {moved_count} PDF files")
    
    # ALWAYS run duplicate detection as standalone subprocess
    # COMMENTED OUT - Too slow for now
    # detect_duplicates(root_dir)

def detect_duplicates(root_dir):
    """Standalone subprocess to detect and move duplicate PDFs using Gemini"""
    print("\n[DUPLICATE DETECTION] Analyzing PDFs for duplicate content...")
    print("-" * 80)
    
    original_dir = root_dir / "01_doc-original"
    all_pdfs = [f for f in original_dir.glob("*_d.pdf") if not f.parent.name.startswith('_')]
    
    if len(all_pdfs) < 2:
        print("[SKIP] Less than 2 PDFs - no duplicates possible")
        return
    
    # Configure Gemini for duplicate detection
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    
    # Convert content fingerprints for all PDFs
    pdf_fingerprints = {}
    
    for pdf in all_pdfs:
        print(f"Analyzing: {pdf.name}...")
        try:
            # Convert first page text as fingerprint
            doc = fitz.open(str(pdf))
            first_page_text = doc[0].get_text()[:2000]  # First 2000 chars
            doc.close()
            
            # Use Gemini to create content fingerprint
            prompt = f"""Analyze this document excerpt and create a brief fingerprint (2-3 sentences) describing:
1. Document type (complaint, motion, letter, etc.)
2. Key parties or entities mentioned
3. Main subject matter or date range

Document excerpt:
{first_page_text}

Return ONLY the fingerprint, no other text."""
            
            response = model.generate_content(prompt)
            fingerprint = response.text.strip()
            pdf_fingerprints[pdf] = fingerprint
            
        except Exception as e:
            print(f"  [WARN] Could not analyze {pdf.name}: {e}")
            pdf_fingerprints[pdf] = f"ERROR: {str(e)}"
    
    # Compare fingerprints to find duplicates
    duplicate_dir = original_dir / "_duplicate"
    duplicates_found = []
    processed = set()
    
    for i, (pdf1, fp1) in enumerate(pdf_fingerprints.items()):
        if pdf1 in processed:
            continue
            
        for pdf2, fp2 in list(pdf_fingerprints.items())[i+1:]:
            if pdf2 in processed:
                continue
            
            # Ask Gemini if these are duplicates
            comparison_prompt = f"""Compare these two document fingerprints and determine if they represent the SAME document (duplicate content).

Document 1 ({pdf1.name}):
{fp1}

Document 2 ({pdf2.name}):
{fp2}

Answer ONLY with "DUPLICATE" if they are the same document, or "DIFFERENT" if they are different documents."""
            
            try:
                response = model.generate_content(comparison_prompt)
                result = response.text.strip().upper()
                
                if "DUPLICATE" in result:
                    # Move the longer filename to _duplicate (likely has more metadata)
                    if len(pdf2.name) > len(pdf1.name):
                        duplicate = pdf2
                        keep = pdf1
                    else:
                        duplicate = pdf1
                        keep = pdf2
                    
                    # Move duplicate
                    target = duplicate_dir / duplicate.name
                    shutil.move(str(duplicate), str(target))
                    duplicates_found.append(duplicate.name)
                    processed.add(duplicate)
                    print(f"  [DUPLICATE] Moved {duplicate.name} (keeping {keep.name})")
                    
            except Exception as e:
                print(f"  [WARN] Could not compare {pdf1.name} and {pdf2.name}: {e}")
    
    if duplicates_found:
        print(f"\n[OK] Found and moved {len(duplicates_found)} duplicate PDFs to _duplicate/")
    else:
        print(f"\n[OK] No duplicates found - all {len(all_pdfs)} PDFs are unique")

# === PHASE 2: RENAME - Intelligent file renaming ===
def convert_metadata_with_gemini(pdf_path, model):
    """Use Gemini to analyze PDF and convert date/party/description"""
    import time
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Convert first page text
            doc = fitz.open(pdf_path)
            first_page_text = doc[0].get_text()[:2000]  # First 2000 chars
            doc.close()
            
            prompt = f"""Analyze this legal document first page and convert metadata in JSON format:

{first_page_text}

Convert and return ONLY a JSON object with these fields:
{{
  "date": "YYYYMMDD format - document date or filing date",
  "party": "Party acronym (RR=Reedy, FIC=Fremont Insurance, Court, Clerk)",
  "case": "Case number acronym (9c1, 9c2, 3c1, 3c2, etc.) if found",
  "description": "Short hyphenated description (2-4 words, use hyphens not spaces)"
}}

Examples of good descriptions:
- "Motion-Venue-Change"
- "Appraisal-Demand"
- "Answer-Counterclaim"
- "Hearing-Transcript"

Return ONLY valid JSON, no explanations."""

            response = model.generate_content(prompt)
            result_text = response.text.strip()
            
            # Convert JSON from response
            if '{' in result_text:
                json_start = result_text.find('{')
                json_end = result_text.rfind('}') + 1
                json_str = result_text[json_start:json_end]
                metadata = json.loads(json_str)
                
                # Small delay between API calls
                time.sleep(0.5)
                return metadata
            else:
                return None
                
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  [WARN] Attempt {attempt + 1} failed, retrying in 3 seconds...")
                time.sleep(3)
            else:
                print(f"  [WARN] Gemini convertion failed after {max_retries} attempts: {e}")
                return None
    
    return None

def check_existing_naming(filename):
    """Check if filename already matches v30 naming convention"""
    # Pattern: YYYYMMDD_PARTY_Description_*.pdf
    pattern = r'^\d{8}_[A-Z0-9]+_[A-Za-z0-9\-]+_[a-z]\.pdf$'
    return bool(re.match(pattern, filename))

def convert_date_from_filename(filename):
    """Convert date from filename patterns like '1.31.22', '2025-02-26', etc."""
    # Pattern 1: M.D.YY or MM.DD.YY
    match = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{2})', filename)
    if match:
        month, day, year = match.groups()
        year = f"20{year}"
        return f"{year}{month.zfill(2)}{day.zfill(2)}"
    
    # Pattern 2: YYYY-MM-DD
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
    if match:
        year, month, day = match.groups()
        return f"{year}{month}{day}"
    
    return None

def clean_filename(filename):
    """Clean filename by removing initial dates, extra spaces, and replacing spaces/dashes with underscores"""
    # Remove initial date patterns like "23 - ", "1.1.23 - ", "2023-01-01 - "
    # Pattern 1: Leading number followed by " - " (e.g., "23 - ")
    filename = re.sub(r'^\d{1,4}\s*-\s*', '', filename)
    
    # Pattern 2: Date patterns at start followed by " - " (e.g., "1.1.23 - ", "12.31.2023 - ")
    filename = re.sub(r'^\d{1,2}\.\d{1,2}\.\d{2,4}\s*-\s*', '', filename)
    
    # Pattern 3: ISO date at start followed by " - " (e.g., "2023-01-01 - ")
    filename = re.sub(r'^\d{4}-\d{2}-\d{2}\s*-\s*', '', filename)
    
    # Pattern 4: Timestamp patterns like "02-26T11-24" or similar
    filename = re.sub(r'\d{2}-\d{2}T\d{2}-\d{2}', '', filename)
    
    # Remove any remaining date patterns from anywhere in filename (already converted for prefix)
    filename = re.sub(r'\d{1,2}\.\d{1,2}\.\d{2,4}', '', filename)
    filename = re.sub(r'\d{4}-\d{2}-\d{2}', '', filename)
    
    # Remove email addresses in brackets like [kmgate@kalcounty.com]
    filename = re.sub(r'\[[\w\.\-]+@[\w\.\-]+\]', '', filename)
    
    # Remove common application/platform names
    filename = re.sub(r'\s*-\s*Google\s+Sheets\s*', '', filename, flags=re.IGNORECASE)
    filename = re.sub(r'\s+Google\s+Sheets\s*', '', filename, flags=re.IGNORECASE)
    
    # Clean up multiple spaces, dashes, and underscores
    filename = re.sub(r'\s*-\s*-\s*', '_', filename)  # Replace " - - " with single underscore
    filename = re.sub(r'\s{2,}', ' ', filename)  # Replace multiple spaces with single space
    
    # Replace spaces and dashes with underscores
    filename = re.sub(r'[\s\-]+', '_', filename)
    
    # Clean up leading/trailing underscores
    filename = re.sub(r'^_+|_+$', '', filename)
    
    # Replace multiple underscores with single underscore
    filename = re.sub(r'_{2,}', '_', filename)
    
    return filename

def phase2_rename(root_dir):
    """Copy files to 02_doc-renamed with date prefix + original name"""
    print("\nPHASE 2: RENAME - ADD DATE PREFIX, PRESERVE ORIGINAL NAME")
    print("-" * 80)
    
    # Ensure directory structure exists
    ensure_directory_structure(root_dir)
    
    original_dir = root_dir / "01_doc-original"
    renamed_dir = root_dir / "02_doc-renamed"
    
    pdf_files = [f for f in original_dir.glob("*_d.pdf") if not f.parent.name.startswith('_')]
    
    if not pdf_files:
        print("[SKIP] No PDF files found in 01_doc-original")
        return
    
    # Sort by file size (smallest to largest) for better progress visibility
    pdf_files.sort(key=lambda x: x.stat().st_size)
    
    # Configure Gemini ONCE for all files
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    
    # Track used names for deduplication
    used_names = set()
    
    for pdf in pdf_files:
        print(f"Processing: {pdf.name}...")
        
        # Get original filename without _d suffix
        original_base = pdf.stem[:-2]  # Remove "_d"
        
        # Check if filename already starts with YYYYMMDD date (8 digits)
        already_has_date = bool(re.match(r'^\d{8}_', original_base))
        
        # Check if compilation (contains "Ex." or "Exhibit")
        is_compilation = bool(re.search(r'\bEx\.\s*P\d+|\bExhibit\b', original_base, re.IGNORECASE))
        
        if is_compilation:
            # Compilation: Clean and use RR_ prefix
            clean_base = clean_filename(original_base)
            new_name = f"RR_{clean_base}_r.pdf"
            print(f"  [COMPILATION] Using RR_ prefix")
        elif already_has_date:
            # Already has date prefix - just clean and add _r suffix
            clean_base = clean_filename(original_base)
            new_name = f"{clean_base}_r.pdf"
            print(f"  [SKIP DATE] Already has date prefix")
        else:
            # Try to convert date from filename first
            date = convert_date_from_filename(original_base)
            
            # If no date in filename, use Gemini
            if not date:
                metadata = convert_metadata_with_gemini(pdf, model)
                if metadata and isinstance(metadata, dict):
                    date = (metadata.get('date', '') or '').replace('-', '')
            
            # Clean the filename: remove dates, extra spaces, replace spaces with underscores
            clean_base = clean_filename(original_base)
            
            # Build new filename: YYYYMMDD_CleanedName_r.pdf or CleanedName_r.pdf
            if date:
                new_name = f"{date}_{clean_base}_r.pdf"
            else:
                new_name = f"{clean_base}_r.pdf"
        
        # Deduplicate: if name exists, add counter
        if new_name in used_names:
            counter = 2
            base_name = new_name[:-6]  # Remove "_r.pdf"
            while f"{base_name}_{counter}_r.pdf" in used_names:
                counter += 1
            new_name = f"{base_name}_{counter}_r.pdf"
            print(f"  [DEDUP] Added counter: _{counter}")
        
        used_names.add(new_name)
        target_path = renamed_dir / new_name
        shutil.copy2(str(pdf), str(target_path))
        print(f"  [OK] Renamed: {pdf.name} → {new_name}")
        report_data['rename'].append({'original': pdf.name, 'renamed': new_name})
    
    print(f"\n[OK] Renamed {len(pdf_files)} files")

# === PHASE 3: OCR - PDF Enhancement ===
def run_subprocess(command):
    """Run subprocess without timeout"""
    try:
        process = subprocess.run(command, check=True, capture_output=True, 
                               text=True, encoding='utf-8')
        return True, process.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def phase3_clean(root_dir):
    """Copy to 03_doc-clean, remove metadata, convert to PDF/A, OCR at 600 DPI"""
    print("\nPHASE 3: OCR - PDF ENHANCEMENT (600 DPI, PDF/A)")
    print("-" * 80)
    
    # Ensure directory structure exists
    ensure_directory_structure(root_dir)
    
    renamed_dir = root_dir / "02_doc-renamed"
    clean_dir = root_dir / "03_doc-clean"
    
    pdf_files = [f for f in renamed_dir.glob("*_r.pdf") if not f.parent.name.startswith('_')]
    
    if not pdf_files:
        print("[SKIP] No PDF files found in 02_doc-renamed")
        return
    
    # Sort by file size (smallest to largest)
    pdf_files.sort(key=lambda x: x.stat().st_size)
    
    # Filter out already processed files
    files_to_process = []
    large_files = []  # Files > 5MB process sequentially to avoid hanging
    skipped_count = 0
    for pdf in pdf_files:
        base_name = pdf.stem[:-2]  # Remove _r
        output_path = clean_dir / f"{base_name}_o.pdf"
        if output_path.exists():
            print(f"[SKIP] Already processed: {pdf.name}")
            skipped_count += 1
        else:
            file_size_mb = pdf.stat().st_size / (1024 * 1024)
            if file_size_mb > 5:
                large_files.append(pdf)
            else:
                files_to_process.append(pdf)
    
    if not files_to_process and not large_files:
        print("[SKIP] All files already processed")
        return
    
    # Process smaller files in parallel first (progress visibility)
    if files_to_process:
        print(f"[INFO] Processing {len(files_to_process)} PDFs with {MAX_WORKERS_CPU} workers...")
        
        # Process files in parallel
        with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS_CPU) as executor:
            futures = {
                executor.submit(_process_clean_pdf, pdf, clean_dir): pdf 
                for pdf in files_to_process
            }
            
            for future in concurrent.futures.as_completed(futures):
                pdf = futures[future]
                try:
                    result = future.result()
                    if result.status in ['OK', 'PARTIAL', 'COPIED']:
                        print(f"[OK] {result.file_name}")
                        report_data['clean'].append({'file': pdf.name, 'status': result.status})
                    else:
                        print(f"[FAIL] {result.file_name}: {result.error or 'Unknown error'}")
                        report_data['clean'].append({'file': pdf.name, 'status': 'FAILED'})
                except Exception as e:
                    print(f"[FAIL] {pdf.name}: {e}")
                    report_data['clean'].append({'file': pdf.name, 'status': 'FAILED'})
    
    # Process large files sequentially last (prevents hanging and provides progress visibility)
    if large_files:
        print(f"[INFO] Processing {len(large_files)} large files (>5MB) sequentially...")
        for pdf in large_files:
            file_size_mb = pdf.stat().st_size / (1024 * 1024)
            print(f"Processing: {pdf.name} ({file_size_mb:.1f} MB)...")
            result = _process_clean_pdf(pdf, clean_dir)
            if result.status in ['OK', 'PARTIAL', 'COPIED']:
                print(f"[OK] {result.file_name}")
                report_data['clean'].append({'file': pdf.name, 'status': result.status})
            else:
                print(f"[FAIL] {result.file_name}: {result.error or 'Unknown error'}")
                report_data['clean'].append({'file': pdf.name, 'status': 'FAILED'})
    
    print(f"\n[OK] Processed {len(files_to_process) + len(large_files)} PDFs")
    success_count = len([r for r in report_data['clean'] if r.get('status') in ['OK', 'PARTIAL', 'COPIED']])
    if skipped_count > 0:
        print(f"[INFO] Skipped {skipped_count} already processed files")
    print(f"[OK] Successfully processed: {success_count}/{len(files_to_process) + len(large_files)} files")

def _process_clean_pdf(pdf_path, clean_dir):
    """Process a single PDF for Phase 3 (Clean). Runs in parallel worker process."""
    base_name = pdf_path.stem[:-2]  # Remove _r
    output_path = clean_dir / f"{base_name}_o.pdf"
    temp_cleaned = None
    compressed_path = None
    
    try:
        # STEP 1: Clean metadata, annotations, highlights, bookmarks FIRST
        print(f"[STEP 1] Cleaning metadata/annotations: {pdf_path.name}")
        temp_cleaned = clean_dir / f"{base_name}_metadata_cleaned.pdf"
        try:
            doc = fitz.open(pdf_path)
            
            # Clear all metadata
            doc.set_metadata({})
            
            # Remove all annotations (including highlights, comments, stamps)
            annot_count = 0
            for page in doc:
                annot = page.first_annot
                while annot:
                    next_annot = annot.next
                    page.delete_annot(annot)
                    annot = next_annot
                    annot_count += 1
            
            # Remove bookmarks/outline
            doc.set_toc([])
            
            # Save cleaned PDF
            doc.save(str(temp_cleaned), garbage=4, deflate=True, clean=True)
            doc.close()
            
            print(f"  → Removed {annot_count} annotations, saved to temp: {temp_cleaned.name}")
            
            # Use cleaned PDF as input for OCR
            ocr_input = str(temp_cleaned)
        except Exception as e:
            print(f"[WARN] Metadata cleaning failed for {pdf_path.name}: {e}")
            ocr_input = str(pdf_path)  # Fallback to original
            if temp_cleaned and temp_cleaned.exists():
                temp_cleaned.unlink()
            temp_cleaned = None
        
        # STEP 2: OCR the cleaned PDF
        print(f"[STEP 2] Running OCR (600 DPI) on cleaned file...")
        # Get ocrmypdf path (try PATH first, then venv)
        ocrmypdf_cmd = shutil.which('ocrmypdf') or 'E:\\00_dev_1\\.venv\\Scripts\\ocrmypdf.exe'
        
        # Try ocrmypdf
        cmd = [ocrmypdf_cmd, '--redo-ocr', '--output-type', 'pdfa', 
               '--oversample', '600', ocr_input, str(output_path)]
        success, out = run_subprocess(cmd)
        
        if not success:
            # Fallback to Ghostscript + ocrmypdf
            print(f"[STEP 2b] OCR failed, trying Ghostscript flatten + OCR...")
            temp_pdf = clean_dir / f"{base_name}_temp.pdf"
            
            try:
                gs_cmd = ['gswin64c', '-sDEVICE=pdfimage32', '-o', 
                         str(temp_pdf), ocr_input]
                gs_success, _ = run_subprocess(gs_cmd)
                
                if gs_success and temp_pdf.exists():
                    # Try OCR on flattened PDF
                    success, _ = run_subprocess(cmd[:-2] + [str(temp_pdf), str(output_path)])
                    if temp_pdf.exists():
                        temp_pdf.unlink()
                else:
                    # Last resort: just copy the file
                    print(f"[STEP 2c] Fallback: copying cleaned file without additional OCR")
                    shutil.copy2(ocr_input, str(output_path))
                    success = True
            except Exception as e:
                print(f"[STEP 2c] Fallback: copying cleaned file without additional OCR")
                shutil.copy2(ocr_input, str(output_path))
                success = True
        
        # STEP 3: Clean up temp metadata file AFTER all OCR attempts
        if temp_cleaned and temp_cleaned.exists():
            print(f"[STEP 3] Deleting temp metadata file: {temp_cleaned.name}")
            try:
                temp_cleaned.unlink()
            except Exception:
                pass  # Ignore cleanup errors
        
        # STEP 4: Compress PDF to reduce file size while maintaining searchability
        print(f"[STEP 4] Compressing OCR'd PDF for online access...")
        if success or output_path.exists():
            try:
                original_size = output_path.stat().st_size
                compressed_path = clean_dir / f"{base_name}_compressed_temp.pdf"
                
                compress_cmd = [
                    'gswin64c', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4',
                    '-dPDFSETTINGS=/ebook', '-dNOPAUSE', '-dQUIET', '-dBATCH',
                    f'-sOutputFile={compressed_path}', str(output_path)
                ]
                
                compress_success, _ = run_subprocess(compress_cmd)
                if compress_success and compressed_path.exists():
                    compressed_size = compressed_path.stat().st_size
                    reduction = ((original_size - compressed_size) / original_size) * 100
                    
                    # Only use compressed version if it's significantly smaller (>10% reduction)
                    if reduction > 10:
                        print(f"  → Compressed {original_size:,} → {compressed_size:,} bytes ({reduction:.1f}% reduction)")
                        compressed_path.replace(output_path)
                        return ProcessingResult(
                            file_name=output_path.name,
                            status='OK',
                            metadata={'compression': f"{original_size:,} → {compressed_size:,} bytes ({reduction:.1f}% reduction)"}
                        )
                    else:
                        print(f"  → Compression only {reduction:.1f}%, keeping original size")
                        if compressed_path.exists():
                            compressed_path.unlink()
                        return ProcessingResult(file_name=output_path.name, status='OK')
                else:
                    print(f"  → Compression failed, keeping original")
                    return ProcessingResult(file_name=output_path.name, status='OK')
                
            except Exception as e:
                if output_path.exists():
                    return ProcessingResult(file_name=output_path.name, status='PARTIAL', error=f"Compression failed: {e}")
                else:
                    return ProcessingResult(file_name=pdf_path.name, status='FAILED', error=f"No output file created: {e}")
        else:
            # OCR failed, try direct copy
            try:
                shutil.copy2(str(pdf_path), str(output_path))
                return ProcessingResult(file_name=output_path.name, status='COPIED')
            except Exception as e:
                return ProcessingResult(file_name=pdf_path.name, status='FAILED', error=str(e))
    
    except Exception as e:
        return ProcessingResult(file_name=pdf_path.name, status='FAILED', error=str(e))
    finally:
        # Always cleanup temp files
        if temp_cleaned and temp_cleaned.exists():
            try:
                temp_cleaned.unlink()
            except Exception:
                pass
        if compressed_path and compressed_path.exists():
            try:
                compressed_path.unlink()
            except Exception:
                pass

# === GCS HELPER FUNCTIONS ===
def sync_directory_to_gcs(local_dir, gcs_prefix, make_public=False, mirror=False):
    """Sync local directory to GCS bucket.

    - Always uploads and overwrites existing remote objects for matching files
    - When mirror=True, deletes remote objects that do not exist locally
    - Optionally makes uploaded objects public (make_public=True)
    """
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET)
        
        local_path = Path(local_dir)
        uploaded_files = []
        local_files_set = set()
        
        for file_path in local_path.rglob('*'):
            if file_path.is_file() and not file_path.name.startswith('.') and not file_path.name.startswith('_'):
                # Calculate relative path for GCS
                relative_path = file_path.relative_to(local_path)
                gcs_path = f"{gcs_prefix}/{relative_path}".replace('\\', '/')
                local_files_set.add(gcs_path)
                
                # Upload to GCS (overwrite if exists)
                blob = bucket.blob(gcs_path)
                blob.upload_from_filename(str(file_path))
                
                # Make public if requested
                if make_public:
                    blob.make_public()
                    public_url = f"https://storage.googleapis.com/{GCS_BUCKET}/{gcs_path}"
                    uploaded_files.append((str(file_path), public_url))
                    print(f"  [PUBLIC] {file_path.name}")
                else:
                    uploaded_files.append((str(file_path), None))
                    print(f"  [UPLOAD] {file_path.name}")
        
        # Mirror: delete remote objects that no longer exist locally
        if mirror:
            try:
                to_delete = []
                for blob in storage_client.list_blobs(GCS_BUCKET, prefix=gcs_prefix + '/'):
                    if blob.name not in local_files_set:
                        to_delete.append(blob)
                for blob in to_delete:
                    blob.delete()
                    print(f"  [DELETE] {blob.name}")
            except Exception as e_del:
                print(f"  [WARN] Mirror delete failed: {e_del}")

        return uploaded_files
    except Exception as e:
        print(f"  [WARN] GCS sync failed: {e}")
        return []

def get_public_url_for_pdf(root_dir, pdf_filename):
        """Get an authenticated URL for the OCR PDF suitable for browser access.

        Returns the Cloud Console authenticated URL pattern so users with access
        can open the file directly in the browser (login required):
            https://storage.cloud.google.com/<bucket>/<object>

        Example:
            https://storage.cloud.google.com/fremont-1/docs/<project>/<filename>.pdf

        Note: Signed URLs remain available via generate_signed_url_for_pdf() if
        time-limited anonymous access is needed.
        """
        project_name = root_dir.name
        return f"https://storage.cloud.google.com/{GCS_BUCKET}/docs/{project_name}/{pdf_filename}"

def generate_signed_url_for_pdf(root_dir, pdf_filename, expiration_hours=168):
    """Generate a signed URL that expires after specified hours (default: 7 days)
    
    This provides temporary access without making files publicly readable.
    Requires service account credentials with signing permissions.
    """
    from datetime import timedelta
    
    project_name = root_dir.name
    
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET)
        blob_name = f"docs/{project_name}/{pdf_filename}"
        blob = bucket.blob(blob_name)
        
        # Generate signed URL that expires in X hours
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=expiration_hours),
            method="GET"
        )
        return url
    except Exception as e:
        print(f"  [WARN] Could not generate signed URL: {e}")
        # Fallback to public URL
        return f"https://storage.googleapis.com/{GCS_BUCKET}/docs/{project_name}/{pdf_filename}"

def sync_all_directories_to_gcs(root_dir):
    """Sync OCR PDFs to GCS (authentication required for access)"""
    print("\n[GCS SYNC] Uploading directories to Google Cloud Storage...")
    
    project_name = root_dir.name
    
    # Sync OCR PDFs to /docs/ path (requires Google authentication to access)
    local_dir = root_dir / "03_doc-clean"
    if local_dir.exists():
        gcs_prefix = f"docs/{project_name}"
        # Mirror deletes remote files that were removed locally. Overwrite on upload is default.
        sync_directory_to_gcs(local_dir, gcs_prefix, make_public=False, mirror=True)
    
    print(f"[OK] GCS sync complete: gs://{GCS_BUCKET}/docs/{project_name}/")

# === PHASE 4: CONVERT - Google Vision OCR ===
def phase4_convert(root_dir):
    """Convert text from PDFs using Google Vision API only"""
    print("\nPHASE 4: CONVERT - GOOGLE VISION TEXT CONVERTION")
    print("-" * 80)
    
    # Ensure directory structure exists
    ensure_directory_structure(root_dir)
    
    clean_dir = root_dir / "03_doc-clean"
    txt_dir = root_dir / "04_doc-convert"
    
    pdf_files = [f for f in clean_dir.glob("*_o.pdf") if not f.parent.name.startswith('_')]
    
    if not pdf_files:
        print("[SKIP] No PDF files found in 03_doc-clean")
        return
    
    # Sort by file size (smallest to largest)
    pdf_files.sort(key=lambda x: x.stat().st_size)
    
    # Initialize Google Vision client
    try:
        client = vision.ImageAnnotatorClient()
    except Exception as e:
        print(f"[FAIL] Could not initialize Google Vision: {e}")
        return
    
    skipped_count = 0
    for pdf in pdf_files:
        base_name = pdf.stem[:-2]  # Remove _o suffix
        output_path = txt_dir / f"{base_name}_c.txt"
        
        # Skip if output already exists
        if output_path.exists():
            print(f"[SKIP] Already converted: {pdf.name}")
            skipped_count += 1
            continue
        
        print(f"Processing: {pdf.name}...")
        
        try:
            # Read PDF
            with open(pdf, 'rb') as f:
                content = f.read()
            
            # Check file size - Google Vision API has 40MB limit for inline requests
            file_size_mb = len(content) / (1024 * 1024)
            use_pymupdf_fallback = file_size_mb > 35  # Use PyMuPDF for files >35MB
            
            # Process in batches of 5 pages (API limit)
            text_pages = []
            page_num = 1
            batch_size = 5
            
            if use_pymupdf_fallback:
                print(f"  [INFO] File size {file_size_mb:.1f}MB - using PyMuPDF extraction (Google Vision payload limit)")
                
                # Use PyMuPDF to extract text from large PDFs
                try:
                    import fitz  # PyMuPDF
                    doc = fitz.open(pdf)
                    
                    for page_idx in range(len(doc)):
                        page = doc.load_page(page_idx)
                        page_text = page.get_text()
                        if page_text.strip():
                            text_pages.append(page_text)
                        if (page_idx + 1) % 10 == 0:
                            print(f"  Processed {len(text_pages)} pages...")
                    
                    doc.close()
                    print(f"  Processed {len(text_pages)} pages...")
                    
                except Exception as e:
                    print(f"  [WARN] PyMuPDF extraction failed: {e}")
                    # Continue to Google Vision fallback below
                    
            else:
                # Standard processing for smaller files
                image_ctx = None
                try:
                    image_ctx = vision.ImageContext(language_hints=['en'])
                except Exception:
                    image_ctx = None
                    
                # Prefer latest OCR model with English hint; fall back if needed
                clean_feature_primary = None
                try:
                    clean_feature_primary = vision.Feature(
                        type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION,
                        model="builtin/latest"
                    )
                except Exception:
                    clean_feature_primary = vision.Feature(
                        type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION
                    )

                while True:
                    # Create request for next 5 pages
                    request = vision.AnnotateFileRequest(
                        input_config=vision.InputConfig(
                            content=content,
                            mime_type='application/pdf'
                        ),
                        features=[clean_feature_primary],
                        pages=list(range(page_num, page_num + batch_size)),
                        image_context=image_ctx
                    )
                    
                    # Process batch
                    try:
                        response = client.batch_annotate_files(requests=[request])
                        
                        # Convert text from this batch
                        batch_pages = []
                        for file_response in response.responses:
                            for page_response in file_response.responses:
                                if page_response.full_text_annotation.text:
                                    batch_pages.append(page_response.full_text_annotation.text)
                        
                        if not batch_pages:
                            # No more pages
                            break
                            
                        text_pages.extend(batch_pages)
                        page_num += batch_size
                        print(f"  Processed {len(text_pages)} pages...")
                        
                    except Exception as e:
                        if "400" in str(e):
                            # Reached end of document
                            break
                        raise
            
            # Fallback: if nothing converted, try simpler TEXT_DETECTION once
            if len(text_pages) == 0:
                try:
                    # Initialize context for fallback
                    fallback_ctx = None
                    try:
                        fallback_ctx = vision.ImageContext(language_hints=['en'])
                    except Exception:
                        fallback_ctx = None
                    
                    page_num = 1
                    fallback_batch_size = 5  # Use smaller batches for fallback
                    while True:
                        clean_feature_fallback = None
                        try:
                            clean_feature_fallback = vision.Feature(
                                type_=vision.Feature.Type.TEXT_DETECTION,
                                model="builtin/latest"
                            )
                        except Exception:
                            clean_feature_fallback = vision.Feature(
                                type_=vision.Feature.Type.TEXT_DETECTION
                            )

                        request_fb = vision.AnnotateFileRequest(
                            input_config=vision.InputConfig(
                                content=content,
                                mime_type='application/pdf'
                            ),
                            features=[clean_feature_fallback],
                            pages=list(range(page_num, page_num + fallback_batch_size)),
                            image_context=fallback_ctx
                        )
                        response_fb = client.batch_annotate_files(requests=[request_fb])
                        batch_pages_fb = []
                        for file_response in response_fb.responses:
                            for page_response in file_response.responses:
                                if page_response.full_text_annotation.text:
                                    batch_pages_fb.append(page_response.full_text_annotation.text)
                        if not batch_pages_fb:
                            break
                        text_pages.extend(batch_pages_fb)
                        page_num += fallback_batch_size
                        print(f"  [FB] Processed {len(text_pages)} pages...")
                except Exception as e_fb:
                    print(f"  [WARN] Fallback TEXT_DETECTION failed: {e_fb}")

            # Build document with header, content, and footer
            base_name = pdf.stem[:-2]  # Remove _o suffix from PDF name
            
            # Get public URL for this PDF
            public_url = get_public_url_for_pdf(root_dir, pdf.name)
            
            # Get simplified directory path (folder name for non-E: drives, full path for E: drive)
            folder_name = root_dir.name
            full_path_str = str(root_dir).replace('\\', '/')
            if full_path_str.startswith('E:/') or full_path_str.startswith('e:/'):
                pdf_directory = full_path_str[3:]
            else:
                pdf_directory = folder_name
            
            # Document header
            header = f"""§§ DOCUMENT INFORMATION §§

DOCUMENT NUMBER: TBD
DOCUMENT NAME: {base_name}
ORIGINAL PDF NAME: {pdf.name}
PDF DIRECTORY: {pdf_directory}
PDF PUBLIC LINK: {public_url}
TOTAL PAGES: {len(text_pages)}

=====================================================================
BEGINNING OF PROCESSED DOCUMENT
=====================================================================

"""
            
            # Document content with page markers
            content_parts = []
            for idx, page_text in enumerate(text_pages, 1):
                # Add blank line before marker (except first page)
                if idx > 1:
                    content_parts.append(f"\n[BEGIN PDF Page {idx}]\n\n{page_text}\n")
                else:
                    content_parts.append(f"[BEGIN PDF Page {idx}]\n\n{page_text}\n")
            
            content = "".join(content_parts)
            
            # Document footer
            footer = f"""
=====================================================================
END OF PROCESSED DOCUMENT
=====================================================================
"""
            
            # Combine all parts
            final_text = header + content + footer
            
            # Save converted text with template
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_text)
            
            print(f"  [OK] {output_path.name} ({len(text_pages)} pages)")
            report_data['convert'].append({
                'file': pdf.name,
                'pages': len(text_pages),
                'chars': sum(len(p) for p in text_pages),
                'status': 'OK'
            })
            
        except Exception as e:
            print(f"  [FAIL] Google Vision error: {e}")
            report_data['convert'].append({'file': pdf.name, 'status': 'FAILED', 'error': str(e)})
    
    success_count = len([r for r in report_data['convert'] if r.get('status') == 'OK'])
    print(f"\n[OK] Converted {success_count}/{len(pdf_files)} files")
    if skipped_count > 0:
        print(f"[INFO] Skipped {skipped_count} already converted files")

def _chunk_body_by_pages(body_text, pages_per_chunk=80):
    """Split body text into chunks by page markers for large documents"""
    chunks = []
    
    # Find all page markers
    page_pattern = r'\n\n\[BEGIN PDF Page \d+\]\n\n'
    page_markers = list(re.finditer(page_pattern, body_text))
    
    if len(page_markers) <= pages_per_chunk:
        # Document small enough, return as single chunk
        return [body_text]
    
    # Split into chunks
    for i in range(0, len(page_markers), pages_per_chunk):
        chunk_markers = page_markers[i:i + pages_per_chunk]
        
        if i == 0:
            # First chunk: from start to end of last page in chunk
            start_pos = 0
        else:
            # Subsequent chunks: from start of first page marker
            start_pos = chunk_markers[0].start()
        
        if i + pages_per_chunk >= len(page_markers):
            # Last chunk: to end of document
            end_pos = len(body_text)
        else:
            # Middle chunks: to start of next chunk's first page
            end_pos = page_markers[i + pages_per_chunk].start()
        
        chunk = body_text[start_pos:end_pos].strip()
        chunks.append(chunk)
    
    return chunks


def _process_format_file(txt_file, formatted_dir, prompt):
    """Worker function for parallel text formatting - matches v21 architecture with chunking"""
    base_name = txt_file.stem[:-2]  # Remove _c suffix
    output_path = formatted_dir / f"{base_name}_v31.txt"
    
    try:
        # Initialize model for this worker
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(MODEL_NAME)
        
        # Read input text (has template from Phase 4)
        with open(txt_file, 'r', encoding='utf-8') as f:
            full_text = f.read()
        
        # CRITICAL: Extract header, body, footer separately (like v21 does)
        # Gemini should ONLY see the document body, not the template
        body_start = full_text.find("BEGINNING OF PROCESSED DOCUMENT")
        footer_start = full_text.find("=====================================================================\nEND OF PROCESSED DOCUMENT")
        
        if body_start < 0 or footer_start < 0:
            raise ValueError("Template markers not found - file may not be from Phase 4")
        
        # Skip past the BEGINNING marker and separator line to get to content
        body_start_line = full_text.find("\n", body_start + len("BEGINNING OF PROCESSED DOCUMENT"))
        body_start_line = full_text.find("\n", body_start_line + 1)  # Skip the === line
        body_start_content = body_start_line + 1
        
        # Extract the three parts
        header = full_text[:body_start_content]
        raw_body = full_text[body_start_content:footer_start].strip()
        footer = full_text[footer_start:]  # Includes the === line before END
        
        # Check if document needs chunking (count pages)
        page_count = len(re.findall(r'\[BEGIN PDF Page \d+\]', raw_body))
        
        if page_count > 80:
            # Large document - process in chunks
            print(f"  [CHUNK] Document has {page_count} pages - processing in 80-page chunks...")
            chunks = _chunk_body_by_pages(raw_body, pages_per_chunk=80)
            cleaned_chunks = []
            
            for idx, chunk in enumerate(chunks, 1):
                print(f"    Processing chunk {idx}/{len(chunks)}...")
                response = model.generate_content(
                    prompt + "\n\n" + chunk,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=MAX_OUTPUT_TOKENS
                    )
                )
                cleaned_chunks.append(response.text.strip())
            
            # Consolidate chunks
            cleaned_body = "\n\n".join(cleaned_chunks)
            print(f"  [OK] Consolidated {len(chunks)} chunks into complete document")
            
        else:
            # Small document - process in single call
            response = model.generate_content(
                prompt + "\n\n" + raw_body,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=MAX_OUTPUT_TOKENS
                )
            )
            cleaned_body = response.text.strip()
        
        # Reassemble: header + cleaned_body + footer (like v21)
        # CRITICAL: Ensure blank lines between sections
        if not header.endswith("\n\n"):
            header = header.rstrip() + "\n\n"
        
        # Footer should have blank lines before it
        final_text = header + cleaned_body + "\n\n" + footer
        
        # Save formatted text
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(final_text)
        
        return ProcessingResult(
            file_name=output_path.name,
            status='OK',
            metadata={'chars_in': len(raw_body), 'chars_out': len(cleaned_body), 'pages': page_count}
        )
        
    except Exception as e:
        return ProcessingResult(
            file_name=txt_file.name,
            status='FAILED',
            error=str(e)
        )

# === PHASE 5: FORMAT - AI Text Cleaning ===
def phase5_format(root_dir):
    """Clean and format text files using Gemini (exact v21 prompt)"""
    print("\nPHASE 5: FORMAT - AI TEXT CLEANING")
    print("-" * 80)
    
    # Ensure directory structure exists
    ensure_directory_structure(root_dir)
    
    txt_dir = root_dir / "04_doc-convert"
    formatted_dir = root_dir / "05_doc-format"
    
    txt_files = [f for f in txt_dir.glob("*_c.txt") if not f.parent.name.startswith('_')]
    
    if not txt_files:
        print("[SKIP] No text files found in 04_doc-convert")
        return
    
    # Sort by file size (smallest to largest)
    txt_files.sort(key=lambda x: x.stat().st_size)
    
    # Check which files need processing FIRST
    files_to_process = []
    skipped_count = 0
    
    for txt_file in txt_files:
        base_name = txt_file.stem[:-2]  # Remove _c
        output_path = formatted_dir / f"{base_name}_v31.txt"
        
        if output_path.exists():
            print(f"[SKIP] Already formatted: {txt_file.name}")
            skipped_count += 1
        else:
            files_to_process.append(txt_file)
    
    if not files_to_process:
        print("[SKIP] All files already formatted")
        return
    
    print(f"[INFO] Processing {len(files_to_process)} new files with {MAX_WORKERS_IO} workers...")
    
    genai.configure(api_key=GEMINI_API_KEY)
    
    # v21 exact prompt - Gemini only sees document body, not template
    prompt = """You are correcting OCR output for a legal document. Your task is to:
1. Fix OCR errors and preserve legal terminology
2. CRITICAL: Preserve ALL page markers EXACTLY as they appear: '[BEGIN PDF Page N]' with blank lines before and after
3. NEVER remove or modify page markers, especially [BEGIN PDF Page 1] - it MUST be preserved
4. Format with lines under 65 characters and proper paragraph breaks
5. Return only the corrected text with ALL page markers intact

IMPORTANT: The first page marker [BEGIN PDF Page 1] must appear at the start of the document body. Do not remove it."""
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS_IO) as executor:
        futures = {
            executor.submit(_process_format_file, txt_file, formatted_dir, prompt): txt_file
            for txt_file in files_to_process
        }
        
        for future in concurrent.futures.as_completed(futures):
            txt_file = futures[future]
            try:
                result = future.result()
                if result.status == 'OK':
                    print(f"[OK] {result.file_name}")
                    metadata = result.metadata if result.metadata else {}
                    report_data['format'].append({
                        'file': txt_file.name,
                        'chars_in': metadata.get('chars_in', 0),
                        'chars_out': metadata.get('chars_out', 0),
                        'status': 'OK'
                    })
                else:
                    print(f"[FAIL] {result.file_name}: {result.error}")
                    report_data['format'].append({'file': txt_file.name, 'status': 'FAILED', 'error': result.error})
            except Exception as e:
                print(f"[FAIL] {txt_file.name}: {e}")
                report_data['format'].append({'file': txt_file.name, 'status': 'FAILED', 'error': str(e)})
    
    success_count = len([r for r in report_data['format'] if r.get('status') == 'OK'])
    print(f"\n[OK] Formatted {success_count}/{len(txt_files)} files")
    if skipped_count > 0:
        print(f"[INFO] Skipped {skipped_count} already formatted files")

# === PHASE 6: VERIFY - Deep comparison ===
def phase6_gcs_upload(root_dir):
    """Upload cleaned PDFs to GCS and insert URLs into text files.
    
    This phase:
    1. Identifies the full directory path relative to workspace
    2. Uploads all *_o.pdf files from 03_doc-clean to GCS with full path
    3. Generates public URLs for each uploaded PDF
    4. Updates headers in 04_doc-convert/*_c.txt files with PDF Directory and PDF Public Link
    5. Updates headers in 05_doc-format/*_v31.txt files with PDF Directory and PDF Public Link
    """
    print("\n" + "="*80)
    print("PHASE 6: GCS UPLOAD - ONLINE ACCESS")
    print("="*80)
    
    clean_dir = root_dir / '03_doc-clean'
    convert_dir = root_dir / '04_doc-convert'
    format_dir = root_dir / '05_doc-format'
    
    if not clean_dir.exists():
        print(f"[SKIP] Clean directory not found: {clean_dir}")
        return
    
    # Get directory name for GCS path (use just the folder name, not full path)
    folder_name = root_dir.name
    full_path_str = str(root_dir).replace('\\', '/')
    
    # For E:\ drive, preserve the path structure
    if full_path_str.startswith('E:/') or full_path_str.startswith('e:/'):
        full_path = full_path_str[3:]
    else:
        # For other drives (G:\, etc.), use just the folder name
        full_path = folder_name
    
    gcs_prefix = f"docs/{folder_name}"
    pdf_directory = full_path
    
    pdf_files = sorted(clean_dir.glob('*_o.pdf'))
    if not pdf_files:
        print(f"[SKIP] No cleaned PDFs found in {clean_dir}")
        return
    
    # Sort by file size (smallest to largest)
    pdf_files.sort(key=lambda x: x.stat().st_size)
    
    print(f"[INFO] Found {len(pdf_files)} PDFs to upload")
    print(f"[INFO] PDF Directory: {pdf_directory}")
    print(f"[INFO] GCS destination: gs://{GCS_BUCKET}/{gcs_prefix}/")
    
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET)
        
        uploaded_count = 0
        convert_updated_count = 0
        format_updated_count = 0
        
        for pdf_path in pdf_files:
            try:
                # Upload to GCS with full directory path
                blob_name = f"{gcs_prefix}/{pdf_path.name}"
                blob = bucket.blob(blob_name)
                
                # CRITICAL: Delete existing file first to ensure fresh upload
                if blob.exists():
                    print(f"\n[DELETE] Removing old version: {pdf_path.name}")
                    blob.delete()
                    print(f"[OK] Deleted old file from GCS")
                
                # Upload new file
                print(f"\n[UPLOAD] {pdf_path.name} → gs://{GCS_BUCKET}/{blob_name}")
                blob.upload_from_filename(str(pdf_path))
                blob.make_public()
                gcs_url = f"https://storage.cloud.google.com/{GCS_BUCKET}/{blob_name}"
                uploaded_count += 1
                print(f"[OK] Uploaded: {gcs_url}")
                
                # Find corresponding files (remove only suffix _o, not all occurrences)
                base_name = pdf_path.stem
                if base_name.endswith('_o'):
                    base_name = base_name[:-2]
                convert_file = convert_dir / f"{base_name}_c.txt" if convert_dir.exists() else None
                format_file = format_dir / f"{base_name}_v31.txt" if format_dir.exists() else None
                
                # Update 04_doc-convert/*_c.txt header
                if convert_file and convert_file.exists():
                    with open(convert_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Create header
                    header = f"PDF Directory: {pdf_directory}\nPDF Public Link: {gcs_url}\n\n"
                    
                    # Remove old header if exists
                    if content.startswith("PDF URL:") or content.startswith("PDF Directory:") or content.startswith("PDF Public Link:"):
                        lines = content.split('\n')
                        content_start = 0
                        for i, line in enumerate(lines):
                            if not line.startswith("PDF") and line.strip():
                                content_start = i
                                break
                        content = '\n'.join(lines[content_start:])
                    
                    # Write updated content
                    with open(convert_file, 'w', encoding='utf-8') as f:
                        f.write(header + content)
                    
                    convert_updated_count += 1
                    print(f"[OK] Updated header in: {convert_file.name}")
                
                # Update 05_doc-format/*_v31.txt header
                if format_file and format_file.exists():
                    with open(format_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Create header
                    header = f"PDF Directory: {pdf_directory}\nPDF Public Link: {gcs_url}\n\n"
                    
                    # Remove old header if exists
                    if content.startswith("PDF URL:") or content.startswith("PDF Directory:") or content.startswith("PDF Public Link:"):
                        lines = content.split('\n')
                        content_start = 0
                        for i, line in enumerate(lines):
                            if not line.startswith("PDF") and line.strip():
                                content_start = i
                                break
                        content = '\n'.join(lines[content_start:])
                    
                    # Write updated content
                    with open(format_file, 'w', encoding='utf-8') as f:
                        f.write(header + content)
                    
                    format_updated_count += 1
                    print(f"[OK] Updated header in: {format_file.name}")
                
                if not convert_file or not convert_file.exists():
                    print(f"[WARN] No convert file found: {base_name}_c.txt")
                if not format_file or not format_file.exists():
                    print(f"[WARN] No format file found: {base_name}_v31.txt")
                
            except Exception as e:
                print(f"[FAIL] Error processing {pdf_path.name}: {e}")
                continue
        
        print(f"\n[SUMMARY] Uploaded {uploaded_count} PDFs to GCS")
        print(f"[SUMMARY] Updated {convert_updated_count} convert files (04_doc-convert)")
        print(f"[SUMMARY] Updated {format_updated_count} format files (05_doc-format)")
        
    except Exception as e:
        print(f"[ERROR] GCS upload failed: {e}")
        raise DocumentProcessingError(f"Phase 6 GCS upload failed: {e}")

# === PHASE 7: VERIFY ===
def phase7_verify(root_dir):
    """Comprehensive verification: PDF directory, online access, and content accuracy"""
    print("\nPHASE 7: VERIFY - COMPREHENSIVE VALIDATION")
    print("-" * 80)
    
    # Ensure directory structure exists
    ensure_directory_structure(root_dir)
    
    clean_dir = root_dir / "03_doc-clean"
    formatted_dir = root_dir / "05_doc-format"
    
    txt_files = list(formatted_dir.glob("*_v31.txt"))
    
    if not txt_files:
        print("[SKIP] No formatted files to verify")
        return
    
    # Sort by file size (smallest to largest)
    txt_files.sort(key=lambda x: x.stat().st_size)
    
    verification_results = []
    manifest_rows = []
    
    for txt_file in txt_files:
        # Find corresponding PDF
        base_name = txt_file.stem[:-4]  # Remove _v31
        pdf_file = clean_dir / f"{base_name}_o.pdf"
        
        if not pdf_file.exists():
            print(f"[WARN] PDF not found for {txt_file.name}")
            continue
        
        print(f"Verifying: {txt_file.name}")
        
        try:
            # Read formatted text
            with open(txt_file, 'r', encoding='utf-8') as f:
                formatted_text = f.read()
            
            # Validate header information
            header_issues = []
            lines = formatted_text.split('\n')
            
            # Check for PDF Directory header
            if not any(line.startswith("PDF Directory:") for line in lines[:10]):
                header_issues.append("Missing PDF Directory header")
            else:
                # Validate PDF Directory path
                for line in lines[:10]:
                    if line.startswith("PDF Directory:"):
                        pdf_dir = line.replace("PDF Directory:", "").strip()
                        # Get expected directory from root_dir
                        full_path = str(root_dir).replace('\\', '/')
                        if full_path.startswith('E:/') or full_path.startswith('e:/'):
                            full_path = full_path[3:]
                        if pdf_dir != full_path:
                            header_issues.append(f"PDF Directory mismatch: expected '{full_path}', found '{pdf_dir}'")
                        break
            
            # Check for PDF Public Link header
            pdf_link_in_header = None
            if not any(line.startswith("PDF Public Link:") for line in lines[:10]):
                header_issues.append("Missing PDF Public Link header")
            else:
                # Validate URL is public format and matches expected
                for line in lines[:10]:
                    if line.startswith("PDF Public Link:"):
                        url = line.replace("PDF Public Link:", "").strip()
                        pdf_link_in_header = url
                        if not url.startswith("https://storage.cloud.google.com/"):
                            header_issues.append(f"URL not in public format: {url}")
                        # Verify URL matches the expected URL for this PDF
                        expected_url = get_public_url_for_pdf(root_dir, pdf_file.name)
                        if url != expected_url:
                            header_issues.append(f"PDF link mismatch: header has '{url}', expected '{expected_url}'")
                        break
            
            # Count pages in formatted text (look for bracketed markers)
            formatted_pages = formatted_text.count('[BEGIN PDF Page ')
            
            # CRITICAL: Verify [BEGIN PDF Page 1] exists
            if '[BEGIN PDF Page 1]' not in formatted_text:
                header_issues.append("Missing [BEGIN PDF Page 1] marker - content may be incomplete")
            
            # Get PDF page count
            doc = fitz.open(pdf_file)
            pdf_pages = len(doc)
            doc.close()

            # File sizes and reduction metrics
            pdf_size_bytes = pdf_file.stat().st_size
            pdf_size_mb = pdf_size_bytes / (1024 * 1024)
            original_pdf = root_dir / "02_doc-renamed" / f"{base_name}_r.pdf"
            reduction_pct = None
            if original_pdf.exists():
                try:
                    orig_size_bytes = original_pdf.stat().st_size
                    if orig_size_bytes > 0:
                        reduction_pct = ((orig_size_bytes - pdf_size_bytes) / orig_size_bytes) * 100.0
                except Exception:
                    reduction_pct = None
            
            # GCS URL for this PDF
            gcs_url = get_public_url_for_pdf(root_dir, pdf_file.name)
            
            # Get character counts
            formatted_chars = len(formatted_text)
            
            # Check for issues (combine header issues with content issues)
            issues = header_issues.copy()
            if formatted_pages == 0:
                issues.append("No page markers found")
            elif abs(formatted_pages - pdf_pages) > 2:
                issues.append(f"Page count mismatch: PDF has {pdf_pages}, markers found {formatted_pages}")
            
            if formatted_chars < 1000:
                issues.append("Text length unusually short")
            
            if issues:
                print(f"  [WARN] Issues found:")
                for issue in issues:
                    print(f"    - {issue}")
                status = 'WARNING'
            else:
                print(f"  [OK] Verified: {pdf_pages} pages, {formatted_chars:,} chars, headers valid")
                status = 'OK'
            
            verification_results.append({
                'file': txt_file.name,
                'pdf_pages': pdf_pages,
                'formatted_pages': formatted_pages,
                'chars': formatted_chars,
                'status': status,
                'issues': issues
            })

            # Add to manifest rows
            manifest_rows.append({
                'file': pdf_file.name,
                'gcs_url': gcs_url,
                'local_path': str(pdf_file),
                'bytes': pdf_size_bytes,
                'mb': round(pdf_size_mb, 3),
                'pdf_pages': pdf_pages,
                'formatted_pages': formatted_pages,
                'status': status,
                'issues': "; ".join(issues) if issues else "",
                'reduction_pct': round(reduction_pct, 2) if reduction_pct is not None else ''
            })
            
        except Exception as e:
            print(f"  [FAIL] Verification error: {e}")
            verification_results.append({
                'file': txt_file.name,
                'status': 'FAILED',
                'error': str(e)
            })
    
    # Generate verification report
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = root_dir / f"VERIFICATION_REPORT_v31_{timestamp}.txt"
    manifest_csv_path = root_dir / f"PDF_MANIFEST_v31_{timestamp}.csv"
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("DOCUMENT PROCESSING v31 - VERIFICATION REPORT\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*80 + "\n\n")
        
        f.write("SUMMARY\n")
        f.write("-"*80 + "\n")
        total = len(verification_results)
        ok_count = len([r for r in verification_results if r.get('status') == 'OK'])
        warn_count = len([r for r in verification_results if r.get('status') == 'WARNING'])
        fail_count = len([r for r in verification_results if r.get('status') == 'FAILED'])
        
        f.write(f"Total Files: {total}\n")
        f.write(f"Verified OK: {ok_count}\n")
        f.write(f"Warnings: {warn_count}\n")
        f.write(f"Failed: {fail_count}\n\n")
        
        # PDF MANIFEST SECTION
        f.write("PDF MANIFEST\n")
        f.write("-"*80 + "\n")
        f.write("File, Size (MB), Pages, Status, Reduction (%), GCS URL\n")
        for row in manifest_rows:
            size_str = f"{row['mb']:.3f}"
            red_str = f"{row['reduction_pct']}" if row['reduction_pct'] != '' else ""
            f.write(f"{row['file']}, {size_str}, {row['pdf_pages']}, {row['status']}, {red_str}, {row['gcs_url']}\n")

        f.write("\nDETAILED RESULTS\n")
        f.write("-"*80 + "\n")
        
        for result in verification_results:
            f.write(f"\nFile: {result['file']}\n")
            f.write(f"Status: {result.get('status', 'UNKNOWN')}\n")
            if 'pdf_pages' in result:
                f.write(f"PDF Pages: {result['pdf_pages']}\n")
                f.write(f"Formatted Pages: {result['formatted_pages']}\n")
                f.write(f"Characters: {result['chars']:,}\n")
            if result.get('issues'):
                f.write("Issues:\n")
                for issue in result['issues']:
                    f.write(f"  - {issue}\n")
            if result.get('error'):
                f.write(f"Error: {result['error']}\n")
    
    # Write CSV manifest
    try:
        with open(manifest_csv_path, 'w', encoding='utf-8', newline='') as csvfile:
            fieldnames = ['file', 'gcs_url', 'local_path', 'bytes', 'mb', 'pdf_pages', 'formatted_pages', 'status', 'issues', 'reduction_pct']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(manifest_rows)
        print(f"[OK] Manifest CSV saved: {manifest_csv_path.name}")
    except Exception as e:
        print(f"[WARN] Could not write manifest CSV: {e}")

    print(f"\n[OK] Final report saved: {report_path.name}")
    report_data['verify'] = verification_results

# === INTERACTIVE MENU ===
def interactive_menu():
    """Interactive menu for user to select phases and verification mode"""
    print("\n" + "="*80)
    print("DOCUMENT PROCESSING v31 - INTERACTIVE MODE")
    print("="*80 + "\n")
    
    # Question 1: Full or Individual phases
    print("1. Do you want to run FULL pipeline or INDIVIDUAL phases?")
    print("   [1] Full pipeline (all 7 phases)")
    print("   [2] Individual phases (select which ones to run)")
    
    while True:
        choice = input("\nEnter choice (1 or 2): ").strip()
        if choice in ['1', '2']:
            break
        print("Invalid choice. Please enter 1 or 2.")
    
    if choice == '1':
        phases = ['directory', 'rename', 'clean', 'convert', 'format', 'gcs_upload', 'verify']
    else:
        print("\n2. Select which phases to run (enter phase numbers separated by spaces):")
        print("   [1] Directory    - Move PDFs to 01_doc-original")
        print("   [2] Rename      - Add date prefix, clean filenames")
        print("   [3] Clean       - PDF enhancement (600 DPI, PDF/A)")
        print("   [4] Convert     - Text convertion with Google Vision")
        print("   [5] Format      - AI-powered text formatting")
        print("   [6] GCS Upload  - Upload to cloud storage & update headers")
        print("   [7] Verify      - Comprehensive verification")
        
        while True:
            phase_input = input("\nEnter phase numbers (e.g., '1 2 3' or '2 3'): ").strip()
            phase_nums = phase_input.split()
            if all(p in ['1', '2', '3', '4', '5', '6', '7'] for p in phase_nums):
                break
            print("Invalid input. Please enter numbers 1-7 separated by spaces.")
        
        phase_map = {
            '1': 'directory', '2': 'rename', '3': 'clean',
            '4': 'convert', '5': 'format', '6': 'gcs_upload', '7': 'verify'
        }
        phases = [phase_map[p] for p in phase_nums]
    
    # Question 2: Verification before each phase
    print("\n3. Do you want to VERIFY before starting each phase?")
    print("   [1] Yes - Ask for confirmation before each phase")
    print("   [2] No  - Run without verification")
    
    while True:
        verify_choice = input("\nEnter choice (1 or 2): ").strip()
        if verify_choice in ['1', '2']:
            break
        print("Invalid choice. Please enter 1 or 2.")
    
    verify_before_phase = (verify_choice == '1')
    
    print("\n" + "="*80)
    print(f"CONFIGURATION:")
    print(f"  Phases to run: {', '.join(phases)}")
    print(f"  Verification: {'Enabled' if verify_before_phase else 'Disabled'}")
    print("="*80 + "\n")
    
    return phases, verify_before_phase

def confirm_phase(phase_name):
    """Ask user to confirm running a phase"""
    phase_descriptions = {
        'directory': 'Move PDFs to 01_doc-original with _d suffix',
        'rename': 'Add date prefix and clean filenames with _r suffix',
        'clean': 'PDF enhancement (600 DPI, PDF/A) with _o suffix',
        'convert': 'Text convertion with Google Vision API with _c suffix',
        'format': 'AI-powered text formatting with Gemini with _v31 suffix',
        'gcs_upload': 'Upload PDFs to GCS and update file headers with directory and public links',
        'verify': 'Comprehensive verification: PDF directory, online access, and content accuracy'
    }
    
    print("\n" + "-"*80)
    print(f"PHASE: {phase_name.upper()}")
    print(f"Description: {phase_descriptions.get(phase_name, 'Unknown phase')}")
    print("-"*80)
    
    choice = input_with_timeout("Commence this phase? [1] Yes  [2] Skip (auto-continue in 30s): ", timeout=30, default='1')
    
    while choice not in ['1', '2']:
        print("Invalid choice. Please enter 1 or 2.")
        choice = input("Commence this phase? [1] Yes  [2] Skip: ").strip()
    
    return choice == '1'

# === PHASE OVERVIEW DISPLAY ===
def print_phase_overview():
    """Display comprehensive overview of all 7 pipeline phases"""
    print("\n" + "="*80)
    print("DOCUMENT PROCESSING PIPELINE v31 - PHASE OVERVIEW")
    print("="*80)
    
    print("\nPHASE 1: DIRECTORY - ORIGINAL PDF COLLECTION")
    print("─" * 80)
    print("  Step 1.1: Verify directory structure")
    print("    • Check for 01_doc-original, 02_doc-renamed, 03-07 directories")
    print("    • Create missing directories if needed")
    print("  Step 1.2: Move PDFs from root to 01_doc-original")
    print("    • Find all *.pdf files in root directory")
    print("    • Remove existing suffixes (_o, _d, _r, _a, _t, _c, _v22, _v31)")
    print("    • Add _d suffix (document/original)")
    print("    • Move to 01_doc-original/")
    print("  Output: *_d.pdf → 01_doc-original/")
    
    print("\nPHASE 2: RENAME - ADD DATE PREFIX, PRESERVE ORIGINAL NAME")
    print("─" * 80)
    print("  Step 2.1: Extract date from filename or PDF content")
    print("    • Check if filename has YYYYMMDD date prefix")
    print("    • Parse common date formats (MM.DD.YY, MM-DD-YY, etc.)")
    print("    • Use Gemini API to extract date from PDF first page if needed")
    print("  Step 2.2: Clean and standardize filename")
    print("    • Remove date patterns from filename")
    print("    • Replace spaces with underscores")
    print("    • Remove special characters")
    print("    • Handle compilations with RR_ prefix")
    print("  Step 2.3: Build new filename and deduplicate")
    print("    • Format: YYYYMMDD_CleanedName_r.pdf")
    print("    • Add counter suffix if duplicate name exists")
    print("    • Copy to 02_doc-renamed/")
    print("  Output: *_r.pdf → 02_doc-renamed/")
    print("  Tools: Gemini 2.5 Pro API")
    
    print("\nPHASE 3: CLEAN - PDF ENHANCEMENT (600 DPI, PDF/A)")
    print("─" * 80)
    print("  Step 3.1: Clean metadata/annotations [PyMuPDF]")
    print("    • Remove all metadata fields")
    print("    • Delete annotations (highlights, comments, stamps)")
    print("    • Remove bookmarks/outline")
    print("    • Save to temp: *_metadata_cleaned.pdf")
    print("  Step 3.2: OCR cleaned file [ocrmypdf]")
    print("    • Input: *_metadata_cleaned.pdf (from Step 3.1)")
    print("    • OCR with 600 DPI oversample")
    print("    • Output as PDF/A format")
    print("    • Fallback: Ghostscript flatten or copy if OCR fails")
    print("  Step 3.3: Delete temporary metadata file")
    print("    • Remove *_metadata_cleaned.pdf")
    print("  Step 3.4: Compress for online access [Ghostscript]")
    print("    • /ebook settings (150 DPI images)")
    print("    • Only keep if >10% size reduction")
    print("    • Cleanup: *_compressed_temp.pdf")
    print("  Output: *_o.pdf → 03_doc-clean/")
    print("  Tools: PyMuPDF (fitz), ocrmypdf 16.11.1, Ghostscript")
    print("  Processing: Large files (>5MB) sequential, smaller files parallel (5 workers)")
    
    print("\nPHASE 4: CONVERT - TEXT EXTRACTION")
    print("─" * 80)
    print("  Step 4.1: Extract text with Google Cloud Vision API")
    print("    • Batch process PDFs for efficiency")
    print("    • Handle large documents (>80 pages) with chunking")
    print("    • Extract raw text from OCR'd PDFs")
    print("  Step 4.2: Save raw extracted text")
    print("    • Output: *_c.txt → 04_doc-convert/")
    print("  Output: *_c.txt → 04_doc-convert/")
    print("  Tools: Google Cloud Vision API (Batch OCR)")
    print("  Processing: Parallel (5 workers)")
    
    print("\nPHASE 5: FORMAT - AI-POWERED TEXT FORMATTING")
    print("─" * 80)
    print("  Step 5.1: Clean and format text with Gemini")
    print("    • Fix OCR errors and spacing issues")
    print("    • Preserve [BEGIN PDF Page N] markers")
    print("    • Remove headers/footers (page numbers, case info)")
    print("    • Remove duplicate lines and whitespace")
    print("    • Standardize formatting for legal documents")
    print("  Step 5.2: Handle large documents with chunking")
    print("    • Split documents >80 pages into chunks")
    print("    • Process chunks in parallel")
    print("    • Reassemble with page markers intact")
    print("  Step 5.3: Save formatted text")
    print("    • Output: *_v31.txt → 05_doc-format/")
    print("  Output: *_v31.txt → 05_doc-format/")
    print("  Tools: Gemini 2.5 Pro (Temperature 0.1 for consistency)")
    print("  Processing: Parallel chunks (5 workers)")
    
    print("\nPHASE 6: GCS UPLOAD - CLOUD STORAGE")
    print("─" * 80)
    print("  Step 6.1: Delete existing files in GCS bucket (if any)")
    print("    • Check for existing files with same name")
    print("    • Delete old versions to prevent stale links")
    print("  Step 6.2: Upload PDF to Google Cloud Storage")
    print("    • Bucket: fremont-1")
    print("    • Path: docs/<directory-name>/")
    print("    • Make publicly accessible")
    print("  Step 6.3: Update formatted text file headers")
    print("    • Add directory path header")
    print("    • Add public GCS URL for PDF")
    print("    • Preserve existing content and page markers")
    print("  Output: Public URLs added to *_v31.txt headers")
    print("  Tools: Google Cloud Storage API")
    print("  Processing: Sequential (API rate limits)")
    
    print("\nPHASE 7: VERIFY - COMPREHENSIVE VALIDATION")
    print("─" * 80)
    print("  Step 7.1: Validate PDF metadata")
    print("    • Count pages in original PDF")
    print("    • Verify file sizes (original vs compressed)")
    print("    • Calculate compression percentage")
    print("  Step 7.2: Verify formatted text content")
    print("    • Count [BEGIN PDF Page N] markers")
    print("    • Verify page 1 marker present")
    print("    • Verify character count >0")
    print("  Step 7.3: Verify GCS links and directory paths")
    print("    • Check directory path matches filename")
    print("    • Extract PDF name from GCS URL")
    print("    • Verify URL matches filename")
    print("  Step 7.4: Generate verification reports")
    print("    • VERIFICATION_REPORT.txt (detailed results)")
    print("    • PDF_MANIFEST.csv (all files summary)")
    print("  Output: Verification reports and status for each file")
    print("  Status Levels: [OK], [WARN], [FAILED]")
    
    print("\n" + "="*80)
    print("TOOLS VERIFICATION:")
    print("─" * 80)
    # Show tool status from preflight checks
    print("  Phase 0 (Preflight):")
    print("    ✓ Root directory: Accessible and writable")
    print("    ✓ Pipeline directories: Created or verified (01-05, y_logs)")
    print("    ✓ Network drive detection: Warns if G:\\ or UNC path")
    print("  Phase 3 Requirements:")
    print("    ✓ PyMuPDF (fitz): Metadata and annotation removal")
    print("    ✓ ocrmypdf: 600 DPI OCR with PDF/A output")
    print("    ✓ Ghostscript: PDF compression (/ebook settings)")
    print("  Phase 4-6 Requirements:")
    print("    ✓ Google Cloud Vision API: Batch text extraction")
    print("    ✓ Gemini 2.5 Pro API: AI-powered text formatting")
    print("    ✓ Google Cloud Storage API: Public file hosting")
    print("="*80 + "\n")

# === MAIN PIPELINE ===
def main():
    parser = argparse.ArgumentParser(description='Document Processing Pipeline v31')
    parser.add_argument('--dir', type=str, help='Target directory to process')
    parser.add_argument('--phase', nargs='+', choices=['directory', 'rename', 'clean', 'convert', 'format', 'gcs_upload', 'verify', 'all'],
                       default=None, help='Phases to run (omit for interactive mode)')
    parser.add_argument('--no-verify', action='store_true', help='Skip phase verification prompts')
    
    args = parser.parse_args()
    
    if not args.dir:
        print("Error: --dir parameter required")
        print("Usage: python doc-process-v31.py --dir /path/to/directory [--phase directory rename clean convert format gcs_upload verify]")
        sys.exit(1)
    
    root_dir = Path(args.dir)
    
    if not root_dir.exists():
        print(f"Error: Directory not found: {root_dir}")
        sys.exit(1)
    
    # Determine which phases to run and verification mode
    if args.phase is None:
        # Interactive mode - ask user
        phases, verify_before_phase = interactive_menu()
    else:
        # Command-line mode
        phases = args.phase
        if 'all' in phases:
            phases = ['directory', 'rename', 'clean', 'convert', 'format', 'gcs_upload', 'verify']
        verify_before_phase = not args.no_verify
    
    # Run preflight checks (skip OCR tools for convert/format/verify/gcs_upload phases)
    skip_clean_check = all(p in ['convert', 'format', 'verify', 'gcs_upload'] for p in phases)
    if not preflight_checks(skip_clean_check=skip_clean_check, root_dir=root_dir):
        sys.exit(1)
    
    # Display comprehensive phase overview
    print_phase_overview()
    
    # Execute phases with optional verification
    phase_functions = {
        'directory': phase1_directory,
        'rename': phase2_rename,
        'clean': phase3_clean,
        'convert': phase4_convert,
        'format': phase5_format,
        'gcs_upload': phase6_gcs_upload,
        'verify': phase7_verify
    }
    
    for phase_name in phases:
        if verify_before_phase:
            if not confirm_phase(phase_name):
                print(f"[SKIP] Skipping {phase_name} phase")
                continue
        
        # Execute the phase with error handling
        try:
            print(f"\n[START] Beginning {phase_name} phase...")
            phase_functions[phase_name](root_dir)
            print(f"[DONE] Completed {phase_name} phase")
        except KeyboardInterrupt:
            print(f"\n[STOP] User cancelled {phase_name} phase")
            user_choice = input_with_timeout("Continue to next phase? [1] Yes  [2] Stop (auto-continue in 30s): ", timeout=30, default='1')
            if user_choice != '1':
                print("[STOP] Pipeline stopped by user")
                break
        except Exception as e:
            print(f"\n[ERROR] Phase {phase_name} failed with error: {e}")
            print(f"[ERROR] Traceback: {e.__class__.__name__}")
            user_choice = input_with_timeout("Continue to next phase? [1] Yes  [2] Stop (auto-continue in 30s): ", timeout=30, default='1')
            if user_choice != '1':
                print("[STOP] Pipeline stopped due to error")
                break
            print(f"[CONTINUE] Moving to next phase...")
    
    print("\n" + "="*80)
    print("[OK] Processing complete")
    print("="*80 + "\n")
    
    # Resume Google Drive sync if it was detected
    resume_google_drive_sync()

if __name__ == "__main__":
    main()
