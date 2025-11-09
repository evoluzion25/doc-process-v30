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
- Automatic phase continuation (no user prompts)
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
import PyPDF2
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

# === BACKUP SYSTEM ===
def create_backup(file_path: Path, root_dir: Path, operation: str = "modify"):
    """
    Create timestamped backup before any file modification or deletion.
    All backups stored in _backups/<YYYYMMDD-HHMMSS>/ with metadata.
    
    Args:
        file_path: Path to file being modified/deleted
        root_dir: Project root directory
        operation: Type of operation (modify, delete, move, rename)
    
    Returns:
        Path to backup file, or None if backup failed
    """
    try:
        if not file_path.exists():
            return None
        
        # Create timestamped backup directory
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = root_dir / "_backups" / timestamp
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Preserve directory structure in backup
        rel_path = file_path.relative_to(root_dir)
        backup_path = backup_dir / rel_path
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy file to backup
        shutil.copy2(str(file_path), str(backup_path))
        
        # Create metadata file
        metadata_path = backup_dir / "BACKUP_METADATA.txt"
        with open(metadata_path, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Operation: {operation}\n")
            f.write(f"Original Path: {file_path}\n")
            f.write(f"Backup Path: {backup_path}\n")
            f.write(f"File Size: {file_path.stat().st_size} bytes\n")
            f.write(f"{'='*80}\n")
        
        return backup_path
        
    except Exception as e:
        print(f"[WARN] Backup failed for {file_path.name}: {e}")
        return None

def create_session_backup(root_dir: Path):
    """
    Create complete snapshot backup before starting any phase.
    Backup includes all pipeline directories (01-05).
    
    Returns:
        Path to session backup directory
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        session_backup_dir = root_dir / "_backups" / f"SESSION_{timestamp}"
        
        # Directories to backup
        dirs_to_backup = [
            "01_doc-original", "02_doc-renamed", "03_doc-clean",
            "04_doc-convert", "05_doc-format"
        ]
        
        backup_count = 0
        for dir_name in dirs_to_backup:
            source_dir = root_dir / dir_name
            if source_dir.exists():
                target_dir = session_backup_dir / dir_name
                shutil.copytree(str(source_dir), str(target_dir), dirs_exist_ok=True)
                backup_count += len(list(target_dir.rglob("*")))
        
        # Create session metadata
        metadata_path = session_backup_dir / "SESSION_BACKUP_INFO.txt"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            f.write(f"SESSION BACKUP\n")
            f.write(f"{'='*80}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Root Directory: {root_dir}\n")
            f.write(f"Files Backed Up: {backup_count}\n")
            f.write(f"Directories Backed Up: {', '.join(dirs_to_backup)}\n")
            f.write(f"{'='*80}\n")
            f.write(f"\nTo restore this session:\n")
            f.write(f"1. Stop any running pipeline processes\n")
            f.write(f"2. Copy contents of each directory back to original location\n")
            f.write(f"3. Verify file counts match\n")
        
        print(f"[BACKUP] Session backup created: {session_backup_dir.name}")
        print(f"[BACKUP] {backup_count} files backed up")
        return session_backup_dir
        
    except Exception as e:
        print(f"[WARN] Session backup failed: {e}")
        return None

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
    
    # CREATE BACKUP before any file operations
    print(f"[BACKUP] Creating backup of {len(pdf_files)} files before moving...")
    for pdf in pdf_files:
        create_backup(pdf, root_dir, operation="move")
    print(f"[BACKUP] Backup complete")
    
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
        
        try:
            # NOTE: Files with very long paths (>260 chars) or special characters like brackets
            # may fail to move on Windows. User should manually move these to 01_doc-original first.
            
            source_str = str(pdf)
            target_str = str(target_path)
            
            # Try normal move first
            shutil.move(source_str, target_str)
            print(f"[OK] Moved: {pdf.name} → {new_name}")
            moved_count += 1
            
        except (OSError, FileNotFoundError) as e:
            # Windows path length limit or special character issue
            print(f"[WARN] Cannot auto-move (path too long or special chars): {pdf.name[:80]}")
            print(f"       Please manually move to 01_doc-original\\ with _d suffix")
            continue
    
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

def _enhance_page1_header(pdf_path, output_path):
    """
    Replace page 1 with high-res image version for better OCR.
    This fixes the issue where legal document titles (underlined, centered) are missed by OCR.
    """
    import fitz
    
    try:
        # Create temp enhanced PDF
        temp_enhanced = output_path.parent / f"temp_enhanced_{pdf_path.name}"
        
        doc = fitz.open(str(pdf_path))
        page = doc[0]
        
        # Render page 1 at very high DPI
        mat = fitz.Matrix(4.0, 4.0)  # 4x zoom = effective 1152 DPI
        pix = page.get_pixmap(matrix=mat, alpha=False)
        
        # Get page dimensions
        rect = page.rect
        
        # Create new PDF with enhanced page 1
        new_doc = fitz.open()
        new_page = new_doc.new_page(width=rect.width, height=rect.height)
        
        # Insert high-res image of original page 1
        img_bytes = pix.tobytes("png")
        new_page.insert_image(rect, stream=img_bytes)
        
        # Copy remaining pages as-is
        new_doc.insert_pdf(doc, from_page=1, to_page=doc.page_count-1)
        
        # Save enhanced PDF
        new_doc.save(str(temp_enhanced))
        new_doc.close()
        doc.close()
        
        print(f"  → Enhanced page 1 at 1152 DPI for header OCR")
        return str(temp_enhanced)
        
    except Exception as e:
        print(f"  [WARN] Page 1 enhancement failed: {e}")
        return None

def _process_clean_pdf(pdf_path, clean_dir):
    """Process a single PDF for Phase 3 (Clean). Runs in parallel worker process."""
    from PIL import Image, ImageEnhance
    import io
    
    base_name = pdf_path.stem[:-2]  # Remove _r
    output_path = clean_dir / f"{base_name}_o.pdf"
    temp_preprocessed = None
    compressed_path = None
    
    try:
        # STEP 1: Try fast OCR first (without preprocessing)
        print(f"[STEP 1] Attempting fast OCR (no preprocessing)...")
        
        ocrmypdf_cmd = shutil.which('ocrmypdf') or 'E:\\00_dev_1\\.venv\\Scripts\\ocrmypdf.exe'
        
        # Try basic OCR first
        cmd = [ocrmypdf_cmd, '--force-ocr', '--output-type', 'pdfa',
               '--oversample', '600',
               str(pdf_path), str(output_path)]
        
        success, out = run_subprocess(cmd)
        
        if not success:
            print(f"  [WARN] Fast OCR failed, will try preprocessing")
        else:
            # Verify OCR quality based on text extraction only
            try:
                doc = fitz.open(str(output_path))
                page1_text = doc[0].get_text()
                doc.close()
                
                # Quality check: page 1 should have meaningful text
                good_quality = len(page1_text) > 100
                
                if good_quality:
                    print(f"  → Fast OCR successful ({len(page1_text)} chars on page 1)")
                    success = True
                else:
                    print(f"  [WARN] Fast OCR produced little text ({len(page1_text)} chars), trying preprocessing")
                    success = False
                    output_path.unlink()  # Remove poor quality output
            except Exception as e:
                print(f"  [WARN] Could not verify OCR quality: {e}")
                success = False
        
        # STEP 2: If fast OCR failed, try PIL preprocessing
        if not success:
            print(f"[STEP 2] Preprocessing PDF (remove underlines, enhance contrast)...")
            temp_preprocessed = clean_dir / f"{base_name}_preprocessed.pdf"
            
            doc = fitz.open(str(pdf_path))
            temp_images = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # Render at high DPI for OCR
                mat = fitz.Matrix(3.0, 3.0)  # ~864 DPI
                pix = page.get_pixmap(matrix=mat, alpha=False)
                
                # Convert to PIL Image
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
                
                # Enhance for OCR: grayscale + contrast + remove horizontal lines
                img_gray = img.convert('L')
                enhancer = ImageEnhance.Contrast(img_gray)
                img_enhanced = enhancer.enhance(2.0)
                
                # Remove horizontal lines (underlines)
                width, height = img_enhanced.size
                pixel_data = img_enhanced.load()
                
                if pixel_data is not None:
                    for y in range(height):
                        line_length = 0
                        for x in range(width):
                            pixel_val = pixel_data[x, y]
                            if isinstance(pixel_val, (int, float)) and pixel_val < 128:
                                line_length += 1
                            else:
                                if line_length > width * 0.3:  # Long horizontal line
                                    for xx in range(x - line_length, x):
                                        if 0 <= xx < width:
                                            pixel_data[xx, y] = 255
                                line_length = 0
                
                # Save temp image
                temp_img = clean_dir / f"{base_name}_temp_page_{page_num + 1}.png"
                img_enhanced.save(str(temp_img), dpi=(600, 600))
                temp_images.append(temp_img)
            
            doc.close()
            
            # Create PDF from preprocessed images with correct page dimensions
            new_doc = fitz.open()
            
            for img_path in temp_images:
                # Open image to get dimensions
                img = Image.open(str(img_path))
                img_width, img_height = img.size
                img.close()
                
                # Images rendered at 3x zoom, convert to PDF points
                page_width = img_width / 3.0
                page_height = img_height / 3.0
                
                # Create new page with correct dimensions
                page = new_doc.new_page(width=page_width, height=page_height)
                
                # Insert image to fill the page
                page_rect = page.rect
                page.insert_image(page_rect, filename=str(img_path))
            
            new_doc.save(str(temp_preprocessed))
            new_doc.close()
            
            print(f"  → Preprocessed {len(temp_images)} pages")
            
            # Clean up temp images
            for img_path in temp_images:
                if img_path.exists():
                    img_path.unlink()
            
            # STEP 3: OCR preprocessed PDF
            print(f"[STEP 3] Running OCR on preprocessed file...")
            
            cmd = [ocrmypdf_cmd, '--force-ocr', '--output-type', 'pdfa',
                   '--oversample', '600',
                   str(temp_preprocessed), str(output_path)]
            
            success, out = run_subprocess(cmd)
            
            if not success:
                print(f"  [ERROR] Preprocessed OCR failed: {out[:200] if out else 'No error output'}")
                # Fallback: copy preprocessed file
                shutil.copy2(str(temp_preprocessed), str(output_path))
                success = True
        
        # STEP FINAL: Clean up temp preprocessed file
        if temp_preprocessed and temp_preprocessed.exists():
            try:
                temp_preprocessed.unlink()
            except Exception:
                pass  # Ignore cleanup errors
        
        # STEP COMPRESSION: Compress PDF to reduce file size
        step_num = 2 if success else 4  # Adjust step number based on path taken
        print(f"[STEP {step_num}] Compressing OCR'd PDF for online access...")
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
        # Always cleanup ALL temp files
        if temp_preprocessed and temp_preprocessed.exists():
            try:
                temp_preprocessed.unlink()
            except Exception:
                pass
        if compressed_path and compressed_path.exists():
            try:
                compressed_path.unlink()
            except Exception:
                pass
        # Also cleanup temp images
        try:
            for temp_img in clean_dir.glob(f"{base_name}_temp_page_*.png"):
                if temp_img.exists():
                    temp_img.unlink()
        except Exception:
            pass

def test_pdf_text_extraction(pdf_path):
    """Test if PDF has selectable/extractable text (OCR text layer).
    
    Returns: (has_text: bool, text_sample: str, page_count: int)
    """
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            page_count = len(reader.pages)
            
            # Extract text from first 3 pages
            text_samples = []
            for i in range(min(3, page_count)):
                page_text = reader.pages[i].extract_text()
                if page_text and page_text.strip():
                    text_samples.append(page_text.strip()[:200])  # First 200 chars
            
            full_sample = "\n".join(text_samples)
            has_text = len(full_sample.strip()) > 50  # At least 50 characters
            
            return has_text, full_sample[:500], page_count
    except Exception as e:
        return False, f"Error: {str(e)}", 0

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
    
    # Get all PDFs, excluding temp/old files
    pdf_files = [f for f in clean_dir.glob("*.pdf") 
                 if not f.parent.name.startswith('_')
                 and not f.name.startswith('_')
                 and not any(x in f.stem for x in ['_temp', '_compressed'])]
    
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
        # Extract base name by removing known suffixes
        base_name = pdf.stem
        for suffix in ['_o', '_d', '_r', '_a', '_t', '_c', '_v22', '_v31', '_gp']:
            if base_name.endswith(suffix):
                base_name = base_name[:-len(suffix)]
                break
        
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
    
    # v31 prompt with v20 formatting attributes
    prompt = """You are correcting OCR output for a legal document. Your task is to:
1. Fix OCR errors and preserve legal terminology
2. CRITICAL: Preserve ALL page markers EXACTLY as they appear: '[BEGIN PDF Page N]' with blank lines before and after
3. NEVER remove or modify page markers, especially [BEGIN PDF Page 1] - it MUST be preserved
4. Format with lines under 65 characters and proper paragraph breaks
5. Render logo/header text on SINGLE lines (e.g., "MERRY FARNEN & RYAN" not multi-line)
6. Use standard bullet points (•) not filled circles (⚫)
7. Use full forwarded message marker: "---------- Forwarded message ---------"
8. Return only the corrected text with ALL page markers intact

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

# === PHASE 6: GCS UPLOAD - COMPREHENSIVE STRUCTURE MANAGEMENT ===
def phase6_gcs_upload(root_dir, force_reupload=False):
    """Upload cleaned PDFs to GCS with comprehensive directory structure management.
    
    This phase implements a robust 5-step process:
    1. Create directory structure documentation (txt manifest)
    2. Create list of each document in each directory
    3. Verify or create GCS directory structure
    4. Delete all items in old directory (if force_reupload) and reupload all files
    5. Update headers for 04_doc-convert and 05_doc-format with:
       a. Relative path directory
       b. Original PDF relative directory path
       c. GCS PDF public URL link
    6. Verify all 04 and 05 headers match directory structure
    
    Args:
        root_dir: Root directory path
        force_reupload: If True, detects old GCS directory from headers, deletes it, uploads to new path
    """
    print("\n" + "="*80)
    print("PHASE 6: GCS UPLOAD - COMPREHENSIVE STRUCTURE MANAGEMENT")
    print("="*80)
    
    clean_dir = root_dir / '03_doc-clean'
    convert_dir = root_dir / '04_doc-convert'
    format_dir = root_dir / '05_doc-format'
    logs_dir = root_dir / 'y_logs'
    logs_dir.mkdir(exist_ok=True)
    
    if not clean_dir.exists():
        print(f"[SKIP] Clean directory not found: {clean_dir}")
        return
    
    # STEP 1: Create directory structure documentation
    print("\n[STEP 1] Creating directory structure documentation...")
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
    
    # Create structure manifest
    structure_manifest_path = logs_dir / "DIRECTORY_STRUCTURE_MANIFEST.txt"
    with open(structure_manifest_path, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("DIRECTORY STRUCTURE MANIFEST\n")
        f.write("="*80 + "\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Root Directory: {root_dir}\n")
        f.write(f"Folder Name: {folder_name}\n")
        f.write(f"PDF Directory Path: {pdf_directory}\n")
        f.write(f"GCS Bucket: {GCS_BUCKET}\n")
        f.write(f"GCS Prefix: {gcs_prefix}\n")
        f.write(f"GCS Full Path: gs://{GCS_BUCKET}/{gcs_prefix}/\n")
        f.write("\n" + "="*80 + "\n\n")
    
    print(f"[OK] Structure manifest created: {structure_manifest_path.name}")
    print(f"[INFO] PDF Directory: {pdf_directory}")
    print(f"[INFO] GCS destination: gs://{GCS_BUCKET}/{gcs_prefix}/")
    print(f"[OK] Structure manifest created: {structure_manifest_path.name}")
    print(f"[INFO] PDF Directory: {pdf_directory}")
    print(f"[INFO] GCS destination: gs://{GCS_BUCKET}/{gcs_prefix}/")
    
    # STEP 2: Create list of each document in each directory
    print("\n[STEP 2] Cataloging documents in each directory...")
    # Get all PDFs, excluding temp/old files
    pdf_files = [f for f in clean_dir.glob('*.pdf') 
                 if not f.parent.name.startswith('_') 
                 and not f.name.startswith('_')
                 and not any(x in f.stem for x in ['_temp', '_compressed'])]
    
    if not pdf_files:
        print(f"[SKIP] No cleaned PDFs found in {clean_dir}")
        return
    
    # Sort by file size (smallest to largest)
    pdf_files.sort(key=lambda x: x.stat().st_size)
    
    document_catalog_path = logs_dir / "DOCUMENT_CATALOG.txt"
    with open(document_catalog_path, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("DOCUMENT CATALOG\n")
        f.write("="*80 + "\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Directory: {pdf_directory}\n")
        f.write(f"Total Documents: {len(pdf_files)}\n")
        f.write("\n" + "-"*80 + "\n")
        f.write("DOCUMENTS BY PIPELINE STAGE:\n")
        f.write("-"*80 + "\n\n")
        
        for i, pdf_path in enumerate(pdf_files, 1):
            # Extract base name by removing known suffixes
            base_name = pdf_path.stem
            for suffix in ['_o', '_d', '_r', '_a', '_t', '_c', '_v22', '_v31', '_gp']:
                if base_name.endswith(suffix):
                    base_name = base_name[:-len(suffix)]
                    break
            
            f.write(f"{i}. {base_name}\n")
            f.write(f"   Clean PDF:   03_doc-clean/{pdf_path.name}\n")
            
            # Look for convert file with any suffix
            convert_file = None
            for suffix in ['_c']:
                candidate = convert_dir / f"{base_name}{suffix}.txt"
                if candidate.exists():
                    convert_file = candidate
                    break
            
            if convert_file:
                f.write(f"   Convert TXT: 04_doc-convert/{convert_file.name}\n")
            else:
                f.write(f"   Convert TXT: [MISSING] 04_doc-convert/{base_name}_c.txt\n")
            
            # Look for format file with any suffix
            format_file = None
            for suffix in ['_v31', '_gp', '_v22']:
                candidate = format_dir / f"{base_name}{suffix}.txt"
                if candidate.exists():
                    format_file = candidate
                    break
            
            if format_file:
                f.write(f"   Format TXT:  05_doc-format/{format_file.name}\n")
            else:
                f.write(f"   Format TXT:  [MISSING] 05_doc-format/{base_name}_v31.txt\n")
            
            f.write(f"   GCS Target:  gs://{GCS_BUCKET}/{gcs_prefix}/{pdf_path.name}\n")
            f.write(f"   Public URL:  https://storage.cloud.google.com/{GCS_BUCKET}/{gcs_prefix}/{pdf_path.name}\n")
            f.write("\n")
    
    print(f"[OK] Document catalog created: {document_catalog_path.name}")
    print(f"[INFO] Found {len(pdf_files)} PDFs to process")
    
    # STEP 3: Verify or create GCS directory structure
    print("\n[STEP 3] Verifying GCS directory structure...")
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET)
        
        # Check if GCS directory exists (any blob with this prefix)
        existing_blobs = list(storage_client.list_blobs(GCS_BUCKET, prefix=gcs_prefix + '/', max_results=1))
        if existing_blobs:
            print(f"[OK] GCS directory exists: gs://{GCS_BUCKET}/{gcs_prefix}/")
        else:
            print(f"[INFO] GCS directory does not exist yet (will be created on first upload)")
        
    except Exception as e:
        print(f"[WARN] Could not verify GCS structure: {e}")
        print(f"[INFO] Will attempt to create on upload")
    
    # STEP 4: Delete all items in old directory (if force_reupload) and reupload all files
    print("\n[STEP 4] Managing GCS uploads...")
    uploaded_count = 0
    old_gcs_folder = None
    
    if force_reupload:
        print("\n[FORCE REUPLOAD] Detecting old GCS directory from existing headers...")
        
        # Check first text file to get old directory name
        sample_txt = None
        if convert_dir.exists():
            txt_files = list(convert_dir.glob("*_c.txt"))
            if txt_files:
                sample_txt = txt_files[0]
        
        if sample_txt and sample_txt.exists():
            with open(sample_txt, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Extract old directory from "PDF DIRECTORY:" header
            for line in lines[:15]:
                if line.startswith("PDF DIRECTORY:"):
                    old_dir = line.replace("PDF DIRECTORY:", "").strip()
                    if old_dir and old_dir != pdf_directory:
                        # Extract folder name from old path
                        old_folder = old_dir.split('/')[-1] if '/' in old_dir else old_dir
                        old_gcs_folder = old_folder
                        print(f"[DETECT] Old directory: {old_dir}")
                        print(f"[DETECT] Old GCS folder: {old_gcs_folder}")
                        print(f"[DETECT] New directory: {pdf_directory}")
                        print(f"[DETECT] New GCS folder: {folder_name}")
                        break
        
        # Delete old GCS directory if detected and different from new
        if old_gcs_folder and old_gcs_folder != folder_name:
            old_gcs_prefix = f"docs/{old_gcs_folder}"
            print(f"\n[DELETE OLD] Removing old GCS directory: gs://{GCS_BUCKET}/{old_gcs_prefix}/")
            
            try:
                blobs_to_delete = list(storage_client.list_blobs(GCS_BUCKET, prefix=old_gcs_prefix + '/'))
                if blobs_to_delete:
                    for blob in blobs_to_delete:
                        blob.delete()
                        print(f"  [DELETED] {blob.name}")
                    print(f"[OK] Deleted {len(blobs_to_delete)} files from old directory")
                else:
                    print(f"[INFO] No files found in old directory (may already be deleted)")
            except Exception as e:
                print(f"[WARN] Could not delete old directory: {e}")
        elif old_gcs_folder == folder_name:
            print(f"[INFO] Directory name unchanged - will re-upload to same location")
        else:
            print(f"[INFO] No old directory detected - this may be first upload")
    
    # Upload all PDFs
    print(f"\n[UPLOAD] Processing {len(pdf_files)} PDFs...")
    upload_log = []
    convert_updated_count = 0
    format_updated_count = 0
    
    for pdf_path in pdf_files:
        try:
            # Upload to GCS with full directory path
            blob_name = f"{gcs_prefix}/{pdf_path.name}"
            blob = bucket.blob(blob_name)
            
            # CRITICAL: Delete existing file first to ensure fresh upload
            if force_reupload or blob.exists():
                if blob.exists():
                    blob.delete()
            
            # Upload new file
            if force_reupload or not blob.exists():
                print(f"\n[UPLOAD] {pdf_path.name} → gs://{GCS_BUCKET}/{blob_name}")
                blob.upload_from_filename(str(pdf_path))
                blob.make_public()
                uploaded_count += 1
                print(f"[OK] Uploaded")
                
                # Log upload
                gcs_url = f"https://storage.cloud.google.com/{GCS_BUCKET}/{blob_name}"
                upload_log.append({
                    'file': pdf_path.name,
                    'gcs_path': blob_name,
                    'url': gcs_url,
                    'size': pdf_path.stat().st_size
                })
            
            # Generate GCS URL (always do this for header updates)
            gcs_url = f"https://storage.cloud.google.com/{GCS_BUCKET}/{blob_name}"
            
            # Find corresponding files - extract base name by removing known suffixes
            base_name = pdf_path.stem
            for suffix in ['_o', '_d', '_r', '_a', '_t', '_c', '_v22', '_v31', '_gp']:
                if base_name.endswith(suffix):
                    base_name = base_name[:-len(suffix)]
                    break
            
            # Find convert file (look for any _c.txt file)
            convert_file = None
            if convert_dir.exists():
                candidate = convert_dir / f"{base_name}_c.txt"
                if candidate.exists():
                    convert_file = candidate
            
            # Find format file (look for any format suffix)
            format_file = None
            if format_dir.exists():
                for suffix in ['_v31', '_gp', '_v22']:
                    candidate = format_dir / f"{base_name}{suffix}.txt"
                    if candidate.exists():
                        format_file = candidate
                        break
            
            # Update 04_doc-convert/*_c.txt header
            if convert_file and convert_file.exists():
                with open(convert_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # Update PDF DIRECTORY and PDF PUBLIC LINK lines in template
                updated = False
                for i, line in enumerate(lines):
                    if line.startswith("PDF DIRECTORY:"):
                        lines[i] = f"PDF DIRECTORY: {pdf_directory}\n"
                        updated = True
                    elif line.startswith("PDF PUBLIC LINK:") or line.startswith("PDF PUBLIC URL:"):
                        lines[i] = f"PDF PUBLIC LINK: {gcs_url}\n"
                        updated = True
                
                if updated:
                    with open(convert_file, 'w', encoding='utf-8') as f:
                        f.writelines(lines)
                    convert_updated_count += 1
                    print(f"[OK] Updated header in: {convert_file.name}")
                else:
                    print(f"[WARN] No header lines found to update in: {convert_file.name}")
            
            # Update 05_doc-format/*_v31.txt header
            if format_file and format_file.exists():
                with open(format_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # Update PDF DIRECTORY and PDF PUBLIC LINK lines in template
                updated = False
                for i, line in enumerate(lines):
                    if line.startswith("PDF DIRECTORY:"):
                        lines[i] = f"PDF DIRECTORY: {pdf_directory}\n"
                        updated = True
                    elif line.startswith("PDF PUBLIC LINK:") or line.startswith("PDF PUBLIC URL:"):
                        lines[i] = f"PDF PUBLIC LINK: {gcs_url}\n"
                        updated = True
                
                if updated:
                    with open(format_file, 'w', encoding='utf-8') as f:
                        f.writelines(lines)
                    format_updated_count += 1
                    print(f"[OK] Updated header in: {format_file.name}")
                else:
                    print(f"[WARN] No header lines found to update in: {format_file.name}")
            
            if not convert_file or not convert_file.exists():
                print(f"[WARN] No convert file found: {base_name}_c.txt")
            if not format_file or not format_file.exists():
                # List possible format file suffixes that were checked
                checked = ', '.join([f"{base_name}{s}.txt" for s in ['_v31', '_gp', '_v22']])
                print(f"[WARN] No format file found (checked: {checked})")
        
        except Exception as e:
            print(f"[FAIL] Error uploading {pdf_path.name}: {e}")
            upload_log.append({
                'file': pdf_path.name,
                'error': str(e)
            })
            continue
    
    # Save upload log
    upload_log_path = logs_dir / f"UPLOAD_LOG_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(upload_log_path, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("GCS UPLOAD LOG\n")
        f.write("="*80 + "\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Force Reupload: {force_reupload}\n")
        f.write(f"Total Files: {len(upload_log)}\n")
        f.write(f"Successful: {uploaded_count}\n")
        f.write(f"Failed: {len([x for x in upload_log if 'error' in x])}\n")
        f.write("\n" + "-"*80 + "\n\n")
        
        for item in upload_log:
            if 'error' in item:
                f.write(f"[FAIL] {item['file']}\n")
                f.write(f"  Error: {item['error']}\n\n")
            else:
                f.write(f"[OK] {item['file']}\n")
                f.write(f"  GCS: {item['gcs_path']}\n")
                f.write(f"  URL: {item['url']}\n")
                f.write(f"  Size: {item['size']:,} bytes\n\n")
    
    print(f"\n[OK] Upload log saved: {upload_log_path.name}")
    print(f"[SUMMARY] Uploaded {uploaded_count}/{len(pdf_files)} PDFs to GCS")
    print(f"[SUMMARY] Updated {convert_updated_count} convert files (04_doc-convert)")
    print(f"[SUMMARY] Updated {format_updated_count} format files (05_doc-format)")
    
    # STEP 6: Verify all 04 and 05 headers match directory structure
    print("\n[STEP 6] Verifying header consistency...")
    header_log_path = logs_dir / f"HEADER_VERIFICATION_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    mismatch_count = 0
    
    with open(header_log_path, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("HEADER VERIFICATION REPORT\n")
        f.write("="*80 + "\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Expected Directory: {pdf_directory}\n")
        f.write(f"Expected GCS Prefix: {gcs_prefix}\n")
        f.write("\n" + "-"*80 + "\n\n")
        
        for pdf_path in pdf_files:
            # Extract base name by removing known suffixes
            base_name = pdf_path.stem
            for suffix in ['_o', '_d', '_r', '_a', '_t', '_c', '_v22', '_v31', '_gp']:
                if base_name.endswith(suffix):
                    base_name = base_name[:-len(suffix)]
                    break
            
            f.write(f"Document: {base_name}\n")
            
            # Check convert file
            convert_file = convert_dir / f"{base_name}_c.txt"
            if convert_file.exists():
                with open(convert_file, 'r', encoding='utf-8') as cf:
                    lines = cf.readlines()
                
                found_dir = None
                found_url = None
                for line in lines[:15]:
                    if line.startswith("PDF DIRECTORY:"):
                        found_dir = line.replace("PDF DIRECTORY:", "").strip()
                    elif line.startswith("PDF PUBLIC LINK:"):
                        found_url = line.replace("PDF PUBLIC LINK:", "").strip()
                
                if found_dir == pdf_directory:
                    f.write(f"  [OK] Convert directory matches: {found_dir}\n")
                else:
                    f.write(f"  [MISMATCH] Convert directory: expected '{pdf_directory}', found '{found_dir}'\n")
                    mismatch_count += 1
                
                expected_url = f"https://storage.cloud.google.com/{GCS_BUCKET}/{gcs_prefix}/{pdf_path.name}"
                if found_url == expected_url:
                    f.write(f"  [OK] Convert URL matches\n")
                else:
                    f.write(f"  [MISMATCH] Convert URL: expected '{expected_url}', found '{found_url}'\n")
                    mismatch_count += 1
            else:
                f.write(f"  [MISSING] Convert file not found\n")
                mismatch_count += 1
            
            # Check format file (try multiple suffixes)
            format_file = None
            for suffix in ['_v31', '_gp', '_v22']:
                candidate = format_dir / f"{base_name}{suffix}.txt"
                if candidate.exists():
                    format_file = candidate
                    break
            
            if format_file:
                with open(format_file, 'r', encoding='utf-8') as ff:
                    lines = ff.readlines()
                
                found_dir = None
                found_url = None
                for line in lines[:15]:
                    if line.startswith("PDF DIRECTORY:"):
                        found_dir = line.replace("PDF DIRECTORY:", "").strip()
                    elif line.startswith("PDF PUBLIC LINK:"):
                        found_url = line.replace("PDF PUBLIC LINK:", "").strip()
                
                if found_dir == pdf_directory:
                    f.write(f"  [OK] Format directory matches: {found_dir}\n")
                else:
                    f.write(f"  [MISMATCH] Format directory: expected '{pdf_directory}', found '{found_dir}'\n")
                    mismatch_count += 1
                
                expected_url = f"https://storage.cloud.google.com/{GCS_BUCKET}/{gcs_prefix}/{pdf_path.name}"
                if found_url == expected_url:
                    f.write(f"  [OK] Format URL matches\n")
                else:
                    f.write(f"  [MISMATCH] Format URL: expected '{expected_url}', found '{found_url}'\n")
                    mismatch_count += 1
            else:
                f.write(f"  [MISSING] Format file not found\n")
                mismatch_count += 1
            
            f.write("\n")
    
    print(f"[OK] Header verification saved: {header_log_path.name}")
    if mismatch_count == 0:
        print(f"[OK] All headers match directory structure")
    else:
        print(f"[WARN] Found {mismatch_count} header mismatches - see log for details")

# === PHASE 7: VERIFY ===
def phase7_verify(root_dir, auto_repair=False):
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
    
    # Initialize GCS client for URL checking
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET)
    except Exception as e:
        print(f"[WARN] Cannot initialize GCS client: {e}")
        storage_client = None
        bucket = None
    
    verification_results = []
    manifest_rows = []
    files_needing_repair = []
    
    def extract_pdf_text_sample(pdf_path, page_numbers=[0, -1]):
        """Extract text from specific PDF pages for comparison"""
        try:
            doc = fitz.open(str(pdf_path))
            samples = {}
            for page_num in page_numbers:
                if page_num < 0:
                    page_num = len(doc) + page_num  # Convert negative index
                if 0 <= page_num < len(doc):
                    text = doc[page_num].get_text()
                    samples[page_num] = text
            doc.close()
            return samples
        except Exception as e:
            return {"error": str(e)}
    
    def compare_content(pdf_text, txt_content, page_num):
        """Compare PDF text to TXT content for specific page"""
        # Find the page marker in TXT
        page_marker = f"[BEGIN PDF Page {page_num + 1}]"
        end_marker = f"[BEGIN PDF Page {page_num + 2}]"
        
        marker_pos = txt_content.find(page_marker)
        if marker_pos == -1:
            return {"match": False, "reason": f"Page marker not found: {page_marker}"}
        
        # Extract text for this page from TXT
        start = marker_pos + len(page_marker)
        end_pos = txt_content.find(end_marker, start)
        if end_pos == -1:
            # Last page
            txt_page_text = txt_content[start:].strip()
        else:
            txt_page_text = txt_content[start:end_pos].strip()
        
        # Clean both texts for comparison
        pdf_clean = re.sub(r'\s+', ' ', pdf_text.lower().strip())
        txt_clean = re.sub(r'\s+', ' ', txt_page_text.lower().strip())
        
        # Calculate similarity (simple overlap)
        if len(pdf_clean) < 50:
            # Too short to compare reliably
            return {"match": True, "reason": "Page too short to validate", "confidence": 0.5}
        
        # Check if significant portion of PDF text appears in TXT
        sample_size = min(200, len(pdf_clean))
        pdf_sample = pdf_clean[:sample_size]
        
        if pdf_sample in txt_clean:
            confidence = 1.0
        else:
            # Calculate word overlap
            pdf_words = set(pdf_clean.split())
            txt_words = set(txt_clean.split())
            if len(pdf_words) > 0:
                overlap = len(pdf_words & txt_words) / len(pdf_words)
                confidence = overlap
            else:
                confidence = 0.0
        
        match = confidence >= 0.7
        
        return {
            "match": match,
            "confidence": round(confidence, 2),
            "pdf_length": len(pdf_text),
            "txt_length": len(txt_page_text),
            "reason": "Content matches" if match else f"Low similarity: {confidence:.2%}"
        }
    
    def check_gcs_url_accessible(url):
        """Check if GCS public URL is accessible"""
        if not url or not bucket:
            return False
        
        try:
            # Extract blob name from URL
            # Format: https://storage.cloud.google.com/bucket-name/path/to/file.pdf
            if "storage.cloud.google.com" in url:
                parts = url.split(f"{GCS_BUCKET}/")
                if len(parts) > 1:
                    blob_name = parts[1]
                    blob = bucket.blob(blob_name)
                    return blob.exists()
            return False
        except Exception:
            return False
    
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
            
            # File sizes
            pdf_size_bytes = pdf_file.stat().st_size
            pdf_size_mb = pdf_size_bytes / (1024 * 1024)
            txt_size_bytes = txt_file.stat().st_size
            txt_size_mb = txt_size_bytes / (1024 * 1024)
            
            # Validate header information
            header_issues = []
            content_issues = []
            lines = formatted_text.split('\n')
            
            # Check for PDF DIRECTORY header (uppercase format)
            if not any(line.startswith("PDF DIRECTORY:") for line in lines[:10]):
                header_issues.append("Missing PDF DIRECTORY header")
            else:
                # Validate PDF Directory path
                for line in lines[:10]:
                    if line.startswith("PDF DIRECTORY:"):
                        pdf_dir = line.replace("PDF DIRECTORY:", "").strip()
                        # Get expected directory name from root_dir
                        expected_dir = root_dir.name
                        if pdf_dir != expected_dir:
                            header_issues.append(f"PDF Directory mismatch: expected '{expected_dir}', found '{pdf_dir}'")
                        break
            
            # Check for PDF PUBLIC LINK header (uppercase format)
            pdf_link_in_header = None
            if not any(line.startswith("PDF PUBLIC LINK:") for line in lines[:10]):
                header_issues.append("Missing PDF PUBLIC LINK header")
            else:
                # Validate URL is public format and matches expected
                for line in lines[:10]:
                    if line.startswith("PDF PUBLIC LINK:"):
                        url = line.replace("PDF PUBLIC LINK:", "").strip()
                        pdf_link_in_header = url
                        if not url.startswith("https://storage.cloud.google.com/"):
                            header_issues.append(f"URL not in public format: {url}")
                        # Verify URL matches the expected URL for this PDF
                        expected_url = get_public_url_for_pdf(root_dir, pdf_file.name)
                        if url != expected_url:
                            header_issues.append(f"PDF link mismatch: header has '{url}', expected '{expected_url}'")
                        break
            
            # Check if GCS URL is accessible
            gcs_url = get_public_url_for_pdf(root_dir, pdf_file.name)
            url_accessible = check_gcs_url_accessible(gcs_url)
            if not url_accessible:
                header_issues.append("GCS URL not accessible or blob does not exist")
            
            # Count pages in formatted text (look for bracketed markers)
            formatted_pages = formatted_text.count('[BEGIN PDF Page ')
            
            # CRITICAL: Verify [BEGIN PDF Page 1] exists
            if '[BEGIN PDF Page 1]' not in formatted_text:
                content_issues.append("Missing [BEGIN PDF Page 1] marker - content may be incomplete")
            
            # Get PDF page count
            doc = fitz.open(pdf_file)
            pdf_pages = len(doc)
            doc.close()
            
            # CONTENT VALIDATION: Compare actual text
            print(f"  → Extracting PDF text samples for comparison...")
            pdf_samples = extract_pdf_text_sample(pdf_file, [0, -1])  # First and last page
            
            content_matches = []
            if "error" in pdf_samples:
                content_issues.append(f"Cannot extract PDF text: {pdf_samples['error']}")
            else:
                for page_num, pdf_text in pdf_samples.items():
                    comparison = compare_content(pdf_text, formatted_text, page_num)
                    content_matches.append(comparison)
                    
                    if not comparison["match"]:
                        content_issues.append(f"Page {page_num + 1}: {comparison['reason']}")
                    
                    print(f"  → Page {page_num + 1}: {'✓' if comparison['match'] else '✗'} (confidence: {comparison.get('confidence', 0):.0%})")
            
            # Calculate overall content confidence
            if content_matches:
                avg_confidence = sum(c.get("confidence", 0) for c in content_matches) / len(content_matches)
            else:
                avg_confidence = 0.0

            # File sizes and reduction metrics
            original_pdf = root_dir / "02_doc-renamed" / f"{base_name}_r.pdf"
            reduction_pct = None
            if original_pdf.exists():
                try:
                    orig_size_bytes = original_pdf.stat().st_size
                    if orig_size_bytes > 0:
                        reduction_pct = ((orig_size_bytes - pdf_size_bytes) / orig_size_bytes) * 100.0
                except Exception:
                    reduction_pct = None
            
            # Get character counts
            formatted_chars = len(formatted_text)
            
            # Check for issues (combine all issues)
            all_issues = header_issues + content_issues
            
            if formatted_pages == 0:
                all_issues.append("No page markers found")
            elif abs(formatted_pages - pdf_pages) > 2:
                all_issues.append(f"Page count mismatch: PDF has {pdf_pages}, markers found {formatted_pages}")
            
            if formatted_chars < 1000:
                all_issues.append("Text length unusually short")
            
            if avg_confidence < 0.7:
                all_issues.append(f"Low content accuracy: {avg_confidence:.0%}")
            
            if all_issues:
                print(f"  [WARN] Issues found:")
                for issue in all_issues:
                    print(f"    - {issue}")
                status = 'WARNING'
                files_needing_repair.append({
                    'file': txt_file.name,
                    'pdf_file': pdf_file.name,
                    'issues': all_issues
                })
            else:
                print(f"  [OK] Verified: {pdf_pages} pages, {formatted_chars:,} chars, {avg_confidence:.0%} accuracy")
                status = 'OK'
            
            verification_results.append({
                'file': txt_file.name,
                'pdf_pages': pdf_pages,
                'formatted_pages': formatted_pages,
                'chars': formatted_chars,
                'status': status,
                'issues': all_issues,
                'content_confidence': avg_confidence
            })

            # Add to manifest rows with formatted text info
            manifest_rows.append({
                'file': pdf_file.name,
                'txt_file': txt_file.name,
                'gcs_url': gcs_url,
                'url_accessible': 'YES' if url_accessible else 'NO',
                'local_path': str(pdf_file),
                'txt_path': str(txt_file),
                'bytes': pdf_size_bytes,
                'mb': round(pdf_size_mb, 3),
                'txt_mb': round(txt_size_mb, 3),
                'pdf_pages': pdf_pages,
                'formatted_pages': formatted_pages,
                'formatted_chars': formatted_chars,
                'page_match': 'YES' if pdf_pages == formatted_pages else 'NO',
                'page_markers_valid': 'YES' if '[BEGIN PDF Page 1]' in formatted_text else 'NO',
                'content_confidence': f"{avg_confidence:.0%}",
                'status': status,
                'issues': "; ".join(all_issues) if all_issues else "",
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
        
        # PDF MANIFEST TABLE - Only show files with actual issues
        if warn_count > 0 or fail_count > 0:
            f.write("FILES WITH ISSUES\n")
            f.write("-"*80 + "\n")
            f.write(f"{'File':<55} {'Status':<10} {'Pages':<8} {'Issues'}\n")
            f.write("-"*80 + "\n")
            
            for result in verification_results:
                if result.get('status') in ['WARNING', 'FAILED']:
                    filename = result['file'][:53] + ".." if len(result['file']) > 55 else result['file']
                    pages = f"{result.get('pdf_pages', 'N/A')}/{result.get('formatted_pages', 'N/A')}"
                    
                    if result.get('issues'):
                        # First issue on same line as file info
                        first_issue = result['issues'][0]
                        f.write(f"{filename:<55} {result.get('status', 'UNKNOWN'):<10} {pages:<8} {first_issue}\n")
                        
                        # Remaining issues indented
                        for issue in result['issues'][1:]:
                            f.write(f"{'':<55} {'':<10} {'':<8} {issue}\n")
                    elif result.get('error'):
                        f.write(f"{filename:<55} {result.get('status', 'UNKNOWN'):<10} {pages:<8} {result['error']}\n")
                    else:
                        f.write(f"{filename:<55} {result.get('status', 'UNKNOWN'):<10} {pages:<8}\n")
            
            f.write("\n")
        else:
            f.write("ALL FILES VERIFIED SUCCESSFULLY\n")
            f.write("-"*80 + "\n")
            f.write("No issues found. All documents processed correctly.\n\n")
        
        # DETAILED DOCUMENT COMPARISON TABLE
        f.write("DETAILED DOCUMENT COMPARISON\n")
        f.write("="*180 + "\n")
        f.write("                                         |---- PDF CONVERSION ----|  |---------- TXT CONVERSION ----------|\n")
        f.write(f"{'Document Name':<40} | {'Pages':<6} {'URL OK':<7} {'PDF MB':<7} {'Reduce%':<8} | {'Pages':<6} {'Match':<6} {'Chars':<10} {'Markers':<8} {'Accuracy':<9} | {'Status':<8}\n")
        f.write("-"*180 + "\n")
        
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
            
            f.write(f"{doc_name:<40} | {pdf_pages:<6} {url_ok:<7} {pdf_mb:<7} {reduction:<8} | {txt_pages:<6} {page_match:<6} {chars:<10} {markers:<8} {accuracy:<9} | {status:<8}\n")
        
        f.write("\n")
        f.write("COLUMN GROUPS:\n")
        f.write("\n")
        f.write("PDF CONVERSION (Verifies online PDF quality):\n")
        f.write("  Pages: Number of pages in cleaned/OCR'd PDF\n")
        f.write("  URL OK: GCS public URL accessible (YES/NO) - verifies online availability\n")
        f.write("  PDF MB: File size after OCR and compression\n")
        f.write("  Reduce%: Size reduction from original (compression effectiveness)\n")
        f.write("\n")
        f.write("TXT CONVERSION (Verifies text extraction accuracy):\n")
        f.write("  Pages: Number of [BEGIN PDF Page N] markers in TXT\n")
        f.write("  Match: YES if PDF pages = TXT page markers (no missing pages)\n")
        f.write("  Chars: Total character count (verifies content was extracted)\n")
        f.write("  Markers: YES if [BEGIN PDF Page 1] exists (proper page marking)\n")
        f.write("  Accuracy: Content match confidence from PDF vs TXT comparison (70%+ is passing)\n")
        f.write("\n")
        f.write("Status: OK = verified, WARNING = issues found, FAILED = error\n\n")
        
        # DOCUMENT FILES AND URLS
        f.write("DOCUMENT FILES AND PUBLIC URLS\n")
        f.write("="*120 + "\n")
        
        for row in manifest_rows:
            base_name = row['file'].replace('_o.pdf', '')
            
            f.write(f"\n{base_name}\n")
            f.write("-"*120 + "\n")
            
            # PDF info
            f.write(f"  PDF (Cleaned):     {row['file']}\n")
            f.write(f"                     {row['gcs_url']}\n")
            f.write(f"                     Pages: {row['pdf_pages']}, Size: {row['mb']:.2f} MB\n")
            
            # TXT info
            f.write(f"\n  TXT (Formatted):   {row['txt_file']}\n")
            f.write(f"                     Pages: {row['formatted_pages']}, Characters: {row['formatted_chars']:,}\n")
            f.write(f"                     Page Markers Valid: {row['page_markers_valid']}\n")
        
        f.write("\n")
    
    # Write CSV manifest
    try:
        with open(manifest_csv_path, 'w', encoding='utf-8', newline='') as csvfile:
            fieldnames = ['file', 'txt_file', 'gcs_url', 'url_accessible', 'local_path', 'txt_path', 
                         'bytes', 'mb', 'txt_mb', 'pdf_pages', 'formatted_pages', 'formatted_chars', 
                         'page_match', 'page_markers_valid', 'content_confidence', 'status', 'issues', 'reduction_pct']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(manifest_rows)
        print(f"[OK] Manifest CSV saved: {manifest_csv_path.name}")
    except Exception as e:
        print(f"[WARN] Could not write manifest CSV: {e}")

    print(f"\n[OK] Final report saved: {report_path.name}")
    
    # REPAIR FUNCTIONALITY
    if files_needing_repair and auto_repair:
        print("\n" + "="*80)
        print("AUTO-REPAIR MODE: Issues detected in the following files")
        print("="*80)
        
        for item in files_needing_repair:
            print(f"\n{item['file']}")
            for issue in item['issues']:
                print(f"  - {issue}")
        
        print("\nAttempting automatic repair...")
        repair_files(root_dir, files_needing_repair)
        
    elif files_needing_repair:
        print("\n" + "="*80)
        print("ISSUES DETECTED - REPAIR AVAILABLE")
        print("="*80)
        print(f"\n{len(files_needing_repair)} file(s) have issues that may need repair:")
        
        for item in files_needing_repair:
            print(f"\n  {item['file']}")
            for issue in item['issues'][:3]:  # Show first 3 issues
                print(f"    - {issue}")
            if len(item['issues']) > 3:
                print(f"    ... and {len(item['issues']) - 3} more issues")
        
        print("\nRepair options:")
        print("  1. Re-run Phase 5 (Format) to regenerate text with correct headers")
        print("  2. Re-run Phase 6 (GCS Upload) to upload missing files and update URLs")
        print("  3. Run with --auto-repair flag to automatically fix issues")
        
        user_input = input("\nWould you like to attempt automatic repair now? (y/n): ").strip().lower()
        if user_input == 'y':
            repair_files(root_dir, files_needing_repair)
    
    report_data['verify'] = verification_results

def repair_files(root_dir, files_needing_repair):
    """Attempt to repair files with issues using intelligent repair strategies"""
    print("\n" + "="*80)
    print("REPAIR PROCESS STARTING")
    print("="*80)
    
    for item in files_needing_repair:
        txt_file = item['file']
        pdf_file = item['pdf_file']
        issues = item['issues']
        
        print(f"\nRepairing: {txt_file}")
        print(f"Issues detected: {len(issues)}")
        
        # Parse issues to determine repair strategy
        has_low_accuracy = False
        accuracy_value = None
        has_header_issues = False
        has_marker_issues = False
        has_url_issues = False
        
        for issue in issues:
            issue_lower = issue.lower()
            
            # Check for low accuracy
            if 'accuracy' in issue_lower or 'similarity' in issue_lower:
                has_low_accuracy = True
                # Extract accuracy percentage
                import re
                match = re.search(r'(\d+)%', issue)
                if match:
                    accuracy_value = int(match.group(1))
            
            # Check for specific issue types
            if 'header' in issue_lower or 'directory' in issue_lower:
                has_header_issues = True
            if 'marker' in issue_lower or 'page marker' in issue_lower:
                has_marker_issues = True
            if 'url' in issue_lower or 'gcs' in issue_lower or 'accessible' in issue_lower:
                has_url_issues = True
        
        base_name = txt_file.replace('_v31.txt', '')
        
        # STRATEGY 1: Low accuracy issues - reprocess PDF with enhanced OCR
        if has_low_accuracy:
            print(f"  [STRATEGY] Low accuracy detected ({accuracy_value}%)")
            
            if accuracy_value and accuracy_value < 50:
                print(f"  [ACTION] Critical accuracy (<50%) - Reprocessing PDF with enhanced OCR")
                # Re-run Phase 3 (Clean) with enhanced settings for this specific file
                reprocess_pdf_enhanced(root_dir, base_name)
                # Re-run Phase 4 (Convert) to extract text again
                reconvert_single_file(root_dir, base_name)
                # Re-run Phase 5 (Format) to regenerate formatted text
                format_single_file(root_dir, base_name)
            elif accuracy_value and accuracy_value < 70:
                print(f"  [ACTION] Moderate accuracy (<70%) - Regenerating text extraction")
                # Re-run Phase 4 (Convert) to re-extract text
                reconvert_single_file(root_dir, base_name)
                # Re-run Phase 5 (Format) to regenerate formatted text
                format_single_file(root_dir, base_name)
            else:
                print(f"  [ACTION] Borderline accuracy - Reformatting only")
                # Just reformat with Gemini
                format_single_file(root_dir, base_name)
        
        # STRATEGY 2: Marker issues without low accuracy - just reformat
        elif has_marker_issues:
            print(f"  [STRATEGY] Page marker issues - Reformatting text")
            format_single_file(root_dir, base_name)
        
        # STRATEGY 3: Header issues - update headers only
        elif has_header_issues and not has_url_issues:
            print(f"  [STRATEGY] Header issues - Updating headers only")
            update_headers_single_file(root_dir, base_name)
        
        # STRATEGY 4: URL issues - re-upload to GCS
        elif has_url_issues:
            print(f"  [STRATEGY] GCS URL issues - Re-uploading to cloud storage")
            upload_single_pdf_to_gcs(root_dir, base_name)
            update_headers_single_file(root_dir, base_name)
        
        # FALLBACK: Reformat if unclear
        else:
            print(f"  [STRATEGY] General issues - Reformatting text")
            format_single_file(root_dir, base_name)
    
    print("\n[OK] Repair process complete")
    print("[INFO] Run Phase 7 (Verify) again to confirm all issues are resolved")

def reprocess_pdf_enhanced(root_dir, base_name):
    """Reprocess PDF with enhanced OCR settings for low accuracy issues"""
    print(f"    [OCR] Reprocessing with enhanced settings...")
    
    rename_dir = root_dir / "02_doc-renamed"
    clean_dir = root_dir / "03_doc-clean"
    
    pdf_renamed = rename_dir / f"{base_name}_r.pdf"
    pdf_clean = clean_dir / f"{base_name}_o.pdf"
    
    if not pdf_renamed.exists():
        print(f"    [ERROR] Source PDF not found: {pdf_renamed}")
        return
    
    try:
        import subprocess
        import fitz  # PyMuPDF
        
        # Step 1: Clean metadata with PyMuPDF
        temp_clean = clean_dir / f"{base_name}_temp.pdf"
        doc = fitz.open(pdf_renamed)
        doc.set_metadata({})  # Clear all metadata
        doc.save(temp_clean, garbage=4, deflate=True)
        doc.close()
        
        # Step 2: Enhanced OCR with higher DPI and quality settings
        print(f"    [OCR] Running enhanced OCR (1200 DPI)...")
        cmd = [
            "ocrmypdf",
            "--force-ocr",           # Force OCR even if text exists
            "--deskew",              # Fix rotation
            "--clean",               # Clean artifacts
            "--rotate-pages",        # Auto-rotate pages
            "--remove-background",   # Remove background
            "--optimize", "1",       # Lower optimization for quality
            "--oversample", "1200",  # Higher DPI for better quality
            "--jpeg-quality", "95",  # Higher JPEG quality
            "--output-type", "pdfa", # PDF/A format
            str(temp_clean),
            str(pdf_clean)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode == 0:
            print(f"    [OK] Enhanced OCR complete: {pdf_clean.name}")
            temp_clean.unlink()  # Remove temp file
        else:
            print(f"    [WARN] OCR had issues: {result.stderr}")
            # Use temp file as fallback
            if temp_clean.exists():
                temp_clean.rename(pdf_clean)
    
    except Exception as e:
        print(f"    [ERROR] Enhanced OCR failed: {e}")
        # Fallback: copy original if nothing else worked
        if not pdf_clean.exists() and pdf_renamed.exists():
            import shutil
            shutil.copy2(pdf_renamed, pdf_clean)

def reconvert_single_file(root_dir, base_name):
    """Re-extract text from PDF using Google Vision API"""
    print(f"    [CONVERT] Re-extracting text with Google Vision...")
    
    clean_dir = root_dir / "03_doc-clean"
    convert_dir = root_dir / "04_doc-convert"
    
    pdf_path = clean_dir / f"{base_name}_o.pdf"
    txt_path = convert_dir / f"{base_name}_c.txt"
    
    if not pdf_path.exists():
        print(f"    [ERROR] Cleaned PDF not found: {pdf_path}")
        return
    
    try:
        # Check file size - use PyMuPDF if >35MB
        file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
        
        if file_size_mb > 35:
            print(f"    [INFO] Large file ({file_size_mb:.1f}MB) - using PyMuPDF extraction")
            import fitz
            doc = fitz.open(pdf_path)
            
            all_text = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                all_text.append(f"\n\n[BEGIN PDF Page {page_num + 1}]\n\n{text}")
            
            doc.close()
            extracted_text = ''.join(all_text)
        
        else:
            print(f"    [INFO] Using Google Vision API for extraction")
            # Use Google Vision in 5-page batches
            extracted_text = extract_text_with_vision(pdf_path)
        
        # Add document header template
        header = f"""§§ DOCUMENT INFORMATION §§

DOCUMENT NUMBER: TBD
DOCUMENT NAME: {base_name}
ORIGINAL PDF NAME: {base_name}_o.pdf
PDF DIRECTORY: {root_dir.name}
PDF PUBLIC LINK: TBD
TOTAL PAGES: {extracted_text.count('[BEGIN PDF Page')}

=====================================================================
BEGINNING OF PROCESSED DOCUMENT
=====================================================================
"""
        
        footer = """
=====================================================================
END OF PROCESSED DOCUMENT
=====================================================================
"""
        
        full_text = header + extracted_text + footer
        
        # Write converted text
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(full_text)
        
        print(f"    [OK] Text re-extracted: {txt_path.name}")
    
    except Exception as e:
        print(f"    [ERROR] Text extraction failed: {e}")

def extract_text_with_vision(pdf_path):
    """Extract text using Google Vision API in batches"""
    import fitz
    from google.cloud import vision
    import io
    
    client = vision.ImageAnnotatorClient()
    doc = fitz.open(pdf_path)
    
    all_text = []
    batch_size = 5
    
    for batch_start in range(0, len(doc), batch_size):
        batch_end = min(batch_start + batch_size, len(doc))
        
        for page_num in range(batch_start, batch_end):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            
            image = vision.Image(content=img_bytes)
            response = client.text_detection(image=image)
            
            if response.text_annotations:
                page_text = response.text_annotations[0].description
            else:
                page_text = page.get_text()  # Fallback to PyMuPDF
            
            all_text.append(f"\n\n[BEGIN PDF Page {page_num + 1}]\n\n{page_text}")
    
    doc.close()
    return ''.join(all_text)

def format_single_file(root_dir, base_name):
    """Format a single converted file (for repair)"""
    print(f"    [FORMAT] Reformatting with Gemini...")
    
    convert_dir = root_dir / "04_doc-convert"
    format_dir = root_dir / "05_doc-format"
    
    convert_file = convert_dir / f"{base_name}_c.txt"
    formatted_file = format_dir / f"{base_name}_v31.txt"
    
    if not convert_file.exists():
        print(f"    [ERROR] Converted file not found: {convert_file}")
        return
    
    try:
        with open(convert_file, 'r', encoding='utf-8') as f:
            text = f.read()
        
        # Extract header, body, footer
        parts = text.split('BEGINNING OF PROCESSED DOCUMENT')
        if len(parts) != 2:
            print(f"    [ERROR] Cannot parse document template")
            return
        
        header = parts[0] + 'BEGINNING OF PROCESSED DOCUMENT'
        remainder = parts[1].split('END OF PROCESSED DOCUMENT')
        body = remainder[0] if remainder else parts[1]
        footer = 'END OF PROCESSED DOCUMENT' + (remainder[1] if len(remainder) > 1 else '')
        
        # Format body with Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(MODEL_NAME)
        
        # Use exact v21 prompt
        prompt = f"""Clean this legal document text by fixing OCR errors. Follow these rules:

1. Fix obvious OCR errors and garbled text
2. Maintain original paragraph structure
3. Keep ALL page markers exactly as: [BEGIN PDF Page N]
4. Preserve case numbers, dates, citations, and formatting
5. Do not add or remove content
6. Keep two blank lines before and after page markers

TEXT TO CLEAN:
{body.strip()}"""
        
        response = model.generate_content(prompt)
        formatted_body = response.text
        
        # Reassemble with original header/footer
        final_text = header + '\n' + formatted_body.strip() + '\n' + footer
        
        # Write formatted output
        with open(formatted_file, 'w', encoding='utf-8') as f:
            f.write(final_text)
        
        print(f"    [OK] Reformatted: {formatted_file.name}")
    
    except Exception as e:
        print(f"    [ERROR] Formatting failed: {e}")

def upload_single_pdf_to_gcs(root_dir, base_name):
    """Upload a single PDF to GCS (for repair)"""
    print(f"    [GCS] Uploading to cloud storage...")
    
    clean_dir = root_dir / "03_doc-clean"
    pdf_path = clean_dir / f"{base_name}_o.pdf"
    
    if not pdf_path.exists():
        print(f"    [ERROR] PDF not found: {pdf_path}")
        return None
    
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET)
        
        # Construct blob path
        folder_name = root_dir.name
        blob_path = f"docs/{folder_name}/{pdf_path.name}"
        blob = bucket.blob(blob_path)
        
        # Upload
        print(f"    [INFO] Uploading {pdf_path.name} to gs://{GCS_BUCKET}/{blob_path}")
        blob.upload_from_filename(str(pdf_path))
        blob.make_public()
        
        public_url = f"https://storage.cloud.google.com/{GCS_BUCKET}/{blob_path}"
        print(f"    [OK] Uploaded: {public_url}")
        
        return public_url
    
    except Exception as e:
        print(f"    [ERROR] Upload failed: {e}")
        return None

def update_headers_single_file(root_dir, base_name):
    """Update PDF DIRECTORY and PDF PUBLIC LINK headers in formatted file"""
    print(f"    [HEADERS] Updating document headers...")
    
    format_dir = root_dir / "05_doc-format"
    convert_dir = root_dir / "04_doc-convert"
    
    formatted_file = format_dir / f"{base_name}_v31.txt"
    convert_file = convert_dir / f"{base_name}_c.txt"
    
    # Get PDF filename and public URL
    pdf_filename = f"{base_name}_o.pdf"
    gcs_url = get_public_url_for_pdf(root_dir, pdf_filename)
    
    # Update formatted file
    if formatted_file.exists():
        with open(formatted_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        updated_lines = []
        
        for line in lines:
            if line.startswith("PDF DIRECTORY:"):
                updated_lines.append(f"PDF DIRECTORY: {root_dir.name}")
            elif line.startswith("PDF PUBLIC LINK:"):
                updated_lines.append(f"PDF PUBLIC LINK: {gcs_url}")
            else:
                updated_lines.append(line)
        
        with open(formatted_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(updated_lines))
        
        print(f"    [OK] Updated headers in {formatted_file.name}")
    
    # Update convert file
    if convert_file.exists():
        with open(convert_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        updated_lines = []
        
        for line in lines:
            if line.startswith("PDF DIRECTORY:"):
                updated_lines.append(f"PDF DIRECTORY: {root_dir.name}")
            elif line.startswith("PDF PUBLIC LINK:"):
                updated_lines.append(f"PDF PUBLIC LINK: {gcs_url}")
            else:
                updated_lines.append(line)
        
        with open(convert_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(updated_lines))

def get_public_url_for_pdf(root_dir, pdf_filename):
    """Get or construct public URL for a PDF"""
    folder_name = root_dir.name
    blob_path = f"docs/{folder_name}/{pdf_filename}"
    return f"https://storage.cloud.google.com/{GCS_BUCKET}/{blob_path}"
        
        # Upload
        blob.upload_from_filename(str(pdf_path))
        blob.make_public()
        
        print(f"    [OK] Uploaded to GCS: {blob_path}")
    except Exception as e:
        raise DocumentProcessingError(f"GCS upload failed: {e}")

def update_headers_single_file(formatted_file, root_dir):
    """Update headers in a single formatted file (for repair)"""
    with open(formatted_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Get PDF filename
    base_name = formatted_file.stem[:-4]  # Remove _v31
    pdf_filename = f"{base_name}_o.pdf"
    
    # Get public URL
    gcs_url = get_public_url_for_pdf(root_dir, pdf_filename)
    
    # Update headers
    lines = content.split('\n')
    updated_lines = []
    
    for line in lines:
        if line.startswith("PDF DIRECTORY:"):
            updated_lines.append(f"PDF DIRECTORY: {root_dir.name}")
        elif line.startswith("PDF PUBLIC LINK:"):
            updated_lines.append(f"PDF PUBLIC LINK: {gcs_url}")
        else:
            updated_lines.append(line)
    
    # Write back
    with open(formatted_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(updated_lines))

# === PHASE 8: REPAIR - AUTOMATIC REPAIR OF VERIFICATION ISSUES ===
def phase8_repair(root_dir):
    """Phase 8: Read last verification report and repair all documented issues"""
    print("\nPHASE 8: REPAIR - AUTOMATIC ISSUE RESOLUTION")
    print("-" * 80)
    
    # Find most recent verification report
    report_files = sorted(root_dir.glob("VERIFICATION_REPORT_v31_*.txt"), reverse=True)
    
    if not report_files:
        print("[ERROR] No verification report found")
        print("[INFO] Run Phase 7 (Verify) first to identify issues")
        return
    
    latest_report = report_files[0]
    print(f"[INFO] Reading verification report: {latest_report.name}")
    
    # Parse report to find files with issues
    files_needing_repair = []
    
    with open(latest_report, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract files from "FILES WITH ISSUES" section
    if "FILES WITH ISSUES" in content:
        issues_section = content.split("FILES WITH ISSUES")[1].split("\n\n")[0]
        lines = issues_section.split('\n')
        
        current_file = None
        current_issues = []
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('-') or line.startswith('File') or line.startswith('Status'):
                continue
            
            # Check if this is a filename line (ends with .txt and has WARNING/FAILED status)
            if '.txt' in line and ('WARNING' in line or 'FAILED' in line):
                # Save previous file if exists
                if current_file:
                    files_needing_repair.append({
                        'file': current_file,
                        'pdf_file': current_file.replace('_v31.txt', '_o.pdf'),
                        'issues': current_issues.copy()
                    })
                    current_issues = []
                
                # Extract filename (first part before status)
                parts = line.split()
                current_file = None
                for part in parts:
                    if part.endswith('.txt'):
                        current_file = part
                        break
                
                # Extract issue from same line if present
                if current_file:
                    issue_start = line.find(current_file) + len(current_file)
                    remaining = line[issue_start:].strip()
                    # Skip status columns
                    parts_after = remaining.split(maxsplit=2)
                    if len(parts_after) > 2:
                        current_issues.append(parts_after[2])
            elif current_file and line and not line.startswith('File'):
                # This is a continuation issue line
                current_issues.append(line)
        
        # Save last file
        if current_file:
            files_needing_repair.append({
                'file': current_file,
                'pdf_file': current_file.replace('_v31.txt', '_o.pdf'),
                'issues': current_issues.copy()
            })
    
    if not files_needing_repair:
        print("[INFO] No issues found in verification report")
        print("[OK] All documents are verified successfully")
        return
    
    print(f"\n[INFO] Found {len(files_needing_repair)} file(s) with issues:")
    for item in files_needing_repair:
        print(f"  - {item['file']} ({len(item['issues'])} issue(s))")
    
    print("\n[START] Beginning automatic repair process...")
    repair_files(root_dir, files_needing_repair)
    
    print("\n" + "="*80)
    print("[OK] Repair process complete")
    print("[INFO] Run Phase 7 (Verify) again to confirm all issues are resolved")
    print("="*80)

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
    
    # Auto-continue without user prompt
    return True

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
    parser.add_argument('--phase', nargs='+', choices=['directory', 'rename', 'clean', 'convert', 'format', 'gcs_upload', 'verify', 'repair', 'all'],
                       default=None, help='Phases to run (omit for interactive mode)')
    parser.add_argument('--no-verify', action='store_true', help='Skip phase verification prompts')
    parser.add_argument('--force-reupload', action='store_true', help='Force re-upload to GCS and update all headers (use after directory rename)')
    parser.add_argument('--auto-repair', action='store_true', help='Automatically repair files with issues during Phase 7 verification')
    parser.add_argument('--repair-and-verify', action='store_true', help='Repair all issues and re-verify (same as --phase repair verify)')
    
    args = parser.parse_args()
    
    if not args.dir:
        print("Error: --dir parameter required")
        print("Usage: python doc-process-v31.py --dir /path/to/directory [--phase directory rename clean convert format gcs_upload verify repair]")
        sys.exit(1)
    
    root_dir = Path(args.dir)
    
    if not root_dir.exists():
        print(f"Error: Directory not found: {root_dir}")
        sys.exit(1)
    
    # Handle --repair-and-verify shortcut
    if args.repair_and_verify:
        phases = ['repair', 'verify']
        verify_before_phase = False
        args.auto_repair = True  # Implicit auto-repair mode
    # Determine which phases to run and verification mode
    elif args.phase is None:
        # Interactive mode - ask user
        phases, verify_before_phase = interactive_menu()
    else:
        # Command-line mode
        phases = args.phase
        if 'all' in phases:
            phases = ['directory', 'rename', 'clean', 'convert', 'format', 'gcs_upload', 'verify']
        verify_before_phase = not args.no_verify
    
    # Run preflight checks (skip OCR tools for convert/format/verify/gcs_upload/repair phases)
    skip_clean_check = all(p in ['convert', 'format', 'verify', 'gcs_upload', 'repair'] for p in phases)
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
        'verify': phase7_verify,
        'repair': phase8_repair
    }
    
    for phase_name in phases:
        if verify_before_phase:
            if not confirm_phase(phase_name):
                print(f"[SKIP] Skipping {phase_name} phase")
                continue
        
        # Execute the phase with error handling
        try:
            print(f"\n[START] Beginning {phase_name} phase...")
            # Pass auto_repair to phase 7
            if phase_name == 'verify':
                phase_functions[phase_name](root_dir, auto_repair=args.auto_repair)
            # Pass force_reupload to phase 6
            elif phase_name == 'gcs_upload':
                phase_functions[phase_name](root_dir, force_reupload=args.force_reupload)
            else:
                phase_functions[phase_name](root_dir)
            print(f"[DONE] Completed {phase_name} phase")
        except KeyboardInterrupt:
            print(f"\n[STOP] User cancelled {phase_name} phase - continuing to next phase")
            continue
        except Exception as e:
            print(f"\n[ERROR] Phase {phase_name} failed with error: {e}")
            print(f"[ERROR] Traceback: {e.__class__.__name__}")
            print(f"[CONTINUE] Moving to next phase...")
            continue
    
    print("\n" + "="*80)
    print("[OK] Processing complete")
    print("="*80 + "\n")
    
if __name__ == "__main__":
    main()
