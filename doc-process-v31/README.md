# Document Processing Pipeline v31

## Overview

Complete 7-phase pipeline for legal document processing with parallel execution, OCR enhancement, AI-powered text formatting, and cloud storage integration.

**Pipeline**: Directory → Rename → Clean → Convert → Format → GCS Upload → Verify

## What's New in v31

### Automatic Backup System (November 9, 2025)
- **Complete protection**: All file operations are backed up before execution
- **Timestamped snapshots**: Every backup stored in `_backups/<YYYYMMDD-HHMMSS>/`
- **Preserve structure**: Maintains original directory hierarchy in backups
- **Metadata tracking**: Each backup includes operation type, timestamp, file paths, sizes
- **Easy restore**: Use `restore_backup.py` utility to restore any backup
- **Session backups**: Full pipeline directory snapshots before starting phases

**Backup Features**:
- Phase 1 (Directory): Backs up all PDFs before moving to `01_doc-original/`
- Prevents data loss from path issues, special characters, or Windows limitations
- Backups preserved indefinitely - never auto-deleted
- Restore utility supports dry-run mode for safe testing

**Restore Usage**:
```bash
# List all available backups
python restore_backup.py --dir "G:\path\to\project"

# Restore latest backup (dry-run)
python restore_backup.py --dir "G:\path\to\project" --latest

# Execute restore (actually copy files)
python restore_backup.py --dir "G:\path\to\project" --latest --execute

# Restore specific backup by timestamp
python restore_backup.py --dir "G:\path\to\project" --backup 20251109-153045 --execute
```

### Phase 6-7 Suffix Flexibility (November 9, 2025)
- **Universal suffix support**: Phase 6 (GCS Upload) and Phase 7 (Verify) now handle PDFs and text files with ANY suffix
- **Automatic detection**: Finds convert files (`*_c.txt`) and format files with any suffix (`*_v31.txt`, `*_gp.txt`, `*_v22.txt`)
- **Smart base name extraction**: Automatically removes known suffixes (`_o`, `_d`, `_r`, `_a`, `_t`, `_c`, `_v22`, `_v31`, `_gp`) to match files across phases
- **Backward compatible**: Still supports standard naming conventions while accommodating custom suffixes
- **Example**: Successfully processes directories with:
  - PDFs: `20231226_9c1_Hearing_o.pdf` (standard suffix)
  - Convert: `20231226_9c1_Hearing_c.txt` (standard suffix)
  - Format: `20231226_9c1_Hearing_gp.txt` (custom Gemini Pro suffix)
- **Validation**: Header verification checks all detected files regardless of suffix
- **Use cases**: Supports legacy files, mixed processing versions, and custom workflow suffixes

### Critical Fixes (November 8, 2025)
- **Phase 3 OCR Enhancement**: PIL preprocessing with fallback approach for optimal quality
  - **STEP 1**: Try fast OCR first (--force-ocr, ~1 sec/page)
  - **Quality Check**: Verify page 1 has >100 characters
  - **STEP 2**: If quality check fails, use PIL preprocessing:
    - Render PDF at 3x zoom (~864 DPI effective resolution)
    - Convert to grayscale and enhance contrast 2.0x
    - Remove horizontal lines (underlines) via pixel-level scanning
    - Create PDF from preprocessed images with correct page dimensions (÷3.0 for 72 DPI)
    - OCR preprocessed PDF with --force-ocr --oversample 600
    - Compress with Ghostscript
  - **Result**: Successfully captures underlined headers that Tesseract misses (e.g., "AMENDED PETITION")
  - **Efficiency**: Only preprocesses PDFs that fail fast OCR quality check (~2-3 sec/page overhead only when needed)
  - **Page Size Fix**: Corrected scaling from 3x rendered images to standard 72 DPI (612x792 points for 8.5x11 inches)
- **Phase 3 Metadata Cleaning**: Reordered processing to clean metadata/annotations FIRST, then OCR
  - Previous versions OCR'd first, then cleaned metadata (backwards)
  - Now removes metadata, annotations, highlights, bookmarks BEFORE OCR
  - Ensures no sensitive data leaks through to OCR'd output
  - Prevents annotations from interfering with OCR quality
  - Uses PyMuPDF to strip: metadata, all annotations (highlights/comments/stamps), bookmarks/outline
  - Proper sanitization order: Clean → OCR → Compress
- **Phase 5 Fix**: Enhanced Gemini prompt to preserve `[BEGIN PDF Page 1]` marker
  - Previous versions removed first page marker during text cleaning
  - Added explicit multi-line instructions to never remove page markers
  - Validates all page markers exist during Phase 7 verification
- **Phase 6 Fix**: Delete-before-upload to prevent stale versions
  - Now deletes existing GCS files before uploading new versions
  - Ensures URLs always point to latest processed version
  - Prevents version mismatches between local and cloud storage
- **Phase 7 Enhancement**: PDF link validation
  - Verifies PDF Public Link matches expected URL for actual file
  - Detects missing `[BEGIN PDF Page 1]` markers
  - Reports PDF link mismatches as validation errors
- **OCR Fix**: Fixed ocrmypdf launcher path issue
  - Reinstalled ocrmypdf with correct Python path
  - Resolved silent OCR failures from incorrect venv path

### Performance Optimizations (November 8, 2025)
- **File processing order**: All phases now process files smallest to largest
  - Better progress visibility (quick wins early)
  - Faster initial feedback on pipeline status
  - More predictable timing estimates (small files complete quickly)
  - Applied to all 7 phases for consistent behavior
  - **Phase 3 Fix**: Small files processed in parallel FIRST, large files sequentially LAST
    - Previous version processed large files first (defeating smallest-to-largest order)
    - Now shows immediate progress on small files
    - Large files (>5MB) still processed sequentially to prevent subprocess deadlocks
    - Provides better UX with faster visible results
- **Google Drive sync detection and auto-pause**: Automatically detects Google Team Drives
  - Detects real-time sync that slows processing by 3-10x
  - Uses psutil to detect Google Drive File Stream process
  - Attempts automatic pause (informational if automation unavailable)
  - Provides clear manual pause instructions if auto-pause fails
  - Shows performance warning with recommendations
  - Prevents 30-60 minute slowdowns on 10-minute tasks
  - Interactive prompt with 30-second auto-continue timeout
- **Secrets loading optimization**: Reduced from 98 to 3 secrets (96% reduction)
  - Only loads required secrets: `GOOGLEAISTUDIO_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS`, `GCS_BUCKET`
  - Faster startup time (~32x faster secrets parsing)
  - Reduced memory footprint (96% fewer environment variables)
  - More secure (only loads what's needed)
- **Explicit dependency management**: Required secrets clearly documented in code
- **CPU worker optimization**: Increased from 3 to 5 workers for small file OCR
  - Optimized for 24-core systems
  - Large files (>5MB) remain sequential to prevent subprocess deadlocks
  - Small files process ~40% faster (5 workers vs 3 workers)
  - Estimated Phase 3 time reduction: 2 minutes on typical 30-file batch

### Phase Reorganization (November 2025)
- **Phase 6 is now GCS Upload**: Upload PDFs to cloud storage and update file headers
- **Phase 7 is now Comprehensive Verification**: Validates PDF directory, online access, and content accuracy
- **New verification checks**:
  - PDF Directory header validation (matches actual folder path)
  - PDF Public Link format validation (public URL, not authenticated)
  - Page count accuracy
  - Character count validation
  - All previous verification metrics retained
- **Logical flow**: Upload files first, then verify everything is correct

### Phase 6 GCS Upload Enhancements (November 2025)
- **Smart path handling**: 
  - E:\ drive paths: Preserves full directory structure from E:\ root
  - Other drives (G:\, network drives): Uses folder name only for cleaner URLs
- **Example (E:\ drive)**: `E:\01_prjct_active\02_legal_system_v1.2\x_docs\01_fremont\15_coa` → `gs://fremont-1/docs/01_prjct_active/02_legal_system_v1.2/x_docs/01_fremont/15_coa/`
- **Example (Google Drive)**: `G:\Shared drives\...\09_Pleadings_plaintiff` → `gs://fremont-1/docs/09_Pleadings_plaintiff/`
- **Dual header updates**: Updates both 04_doc-convert/*_c.txt and 05_doc-format/*_v31.txt files
- **New header format**:
  - `PDF Directory: 09_Pleadings_plaintiff` (or full path for E:\ drive)
  - `PDF Public Link: https://storage.cloud.google.com/fremont-1/docs/09_Pleadings_plaintiff/filename.pdf`
- **Backward compatibility**: Removes old "PDF URL:" headers when updating
- Supports both local (E:\) and network drive structures

### Phase 2 Rename Enhancements (November 2025)
- **Smart date detection**: Skips adding date prefix if filename already starts with YYYYMMDD format
- **Google Sheets removal**: Automatically removes "Google Sheets" text from filenames
- Prevents duplicate date prefixes on files that already have proper naming

### Phase 1 Suffix Fix (November 2025)
- **Fixed**: Phase 1 now properly strips `_o` suffix and adds `_d` suffix
- Previously files with `_o` kept their suffix unchanged, causing Phase 2 to skip files
- Now removes any existing suffix (`_o`, `_d`, `_r`, etc.) before adding `_d`
- Ensures proper progression through all pipeline phases

### Chunked Processing for Large Documents (November 2025)
- **Automatic chunking** for documents >80 pages
- Splits large documents into 80-page segments for Gemini processing
- Consolidates chunks seamlessly with proper formatting
- Overcomes Gemini's 65536 output token limit
- Successfully tested on 171-page documents (3 chunks)
- Each chunk maintains page markers and formatting integrity

### Automatic Phase Continuation (November 2025)
- **No user prompts**: Pipeline continues automatically through all phases
- **Error/cancel handlers**: Logs issue and continues to next phase
- Enables fully unattended pipeline execution
- Removed all `input_with_timeout()` prompts for seamless operation

### Automatic Missing File Detection (November 2025)
- **Smart phase resumption**: Each phase checks for missing files from previous phase
- **Incremental processing**: Only processes files that don't exist in output directory
- **Resume capability**: Can safely restart pipeline at any phase without reprocessing
- **Example**: If Phase 3 has 50 files but Phase 4 only has 45, automatically processes the 5 missing files
- **Status tracking**: Shows which files are being skipped vs newly processed
- Enables efficient reruns after failures or partial completions

### Phase 5 v21 Architecture (November 2025)
- **Architectural Change**: Phase 5 now matches v21's proven approach
  - Phase 4 creates complete template (header + body + footer)
  - Phase 5 extracts only document body for AI processing
  - Gemini processes raw text without seeing template structure
  - Reassembles cleaned body with original header/footer
- **Result**: Perfect formatting preservation with `\n\n[BEGIN PDF Page N]\n\n` (two blank lines)
- **Parallel Processing**: 5 concurrent workers via ThreadPoolExecutor
- **Model**: gemini-2.5-pro (Tier 3) with 65536 max tokens, temperature=0.1

### PyMuPDF Fallback for Large Files (November 2025)
- **Automatic fallback** for PDFs >35MB (overcomes Google Vision API 40MB payload limit)
- **Seamless switching**: Uses PyMuPDF's `fitz.open().get_text()` when needed
- Successfully tested on 40MB+ files with 50+ pages
- Same template structure as Google Vision output

### File Size Optimizations (November 2025)
- **Phase 3 threshold**: Files ≥5MB processed sequentially (prevents subprocess deadlocks)
- **Phase 4 threshold**: Files >35MB use PyMuPDF instead of Google Vision
- Configurable thresholds for different hardware/network conditions

### Updated Phase Names & Suffixes
- Phase 1: **Directory** (was "Organize") - `_d` suffix (original PDFs)
- Phase 2: **Rename** - `_r` suffix (renamed with date prefix)
- Phase 3: **Clean** (was "OCR") - `_o` suffix (cleaned metadata + OCR'd PDF/A)
- Phase 4: **Convert** (was "Extract") - `_c.txt` suffix (extracted text)
- Phase 5: **Format** - `_v31.txt` suffix (AI-cleaned text)
- Phase 6: **GCS Upload** - uploads Phase 3 PDFs (`_o.pdf`) to cloud storage
- Phase 7: **Verify** - validates all phases

### Optimized Clean/OCR Phase (Phase 3)

**Processing order** (sequential per file):
1. **Clean metadata/annotations** FIRST (PyMuPDF):
   - Remove all metadata
   - Delete all annotations (highlights, comments, stamps)
   - Remove bookmarks/outline
   - Saves to temporary `_metadata_cleaned.pdf`
2. **OCR at 600 DPI with aggressive optimization** (ocrmypdf on cleaned file):
   - Produces searchable PDF/A format
   - 600 DPI oversample for high-quality text extraction
   - `--optimize 3` for aggressive compression during OCR (prevents 700-850% file expansion)
   - `--jpeg-quality 85` balances quality vs file size
   - Compresses images and text layer simultaneously (much more effective than post-compression)
3. **Additional Compression** (Ghostscript `/ebook` settings - if needed):
   - Applies secondary compression if ocrmypdf didn't achieve sufficient reduction
   - Maintains searchability and text layer
   - Only keeps compressed version if >10% additional reduction
4. **Cleanup**: Deletes temporary `_metadata_cleaned.pdf`

**File size optimization**: ocrmypdf's built-in optimization prevents the 8 MB → 78 MB expansion that occurred with compression-only approaches. Expected output: 8 MB input → 10-15 MB searchable PDF (vs 78 MB without optimization).

**Parallelization**: Multiple files processed simultaneously (5 workers for small files, sequential for large >5MB files)

### Performance Improvements

- **Parallel processing** for Phases 2-6 (3-5x faster on multi-file batches)
- **ThreadPoolExecutor** for API calls (Gemini, Google Vision)
- **ProcessPoolExecutor** for CPU-bound OCR operations (Phase 3)
- Configurable worker counts: 5 workers (I/O), 3 workers (CPU)

### Error Handling
- **Custom exception classes** for better debugging
  - `DocumentProcessingError` (base)
  - `OcrError`, `ApiError`, `ExtractionError`, `FormattingError`
- **Dead-letter queue** - Failed files moved to `_failed/<phase>/` with error logs
- **Per-file error handling** - Single file failure doesn't stop entire phase
- Continues processing remaining files after errors

### New Features
- **ProcessingResult dataclass** for structured results
- Enhanced progress tracking
- Quarantine system for failed files with detailed error logs

## Quick Start

### CRITICAL: Python Environment Setup

**ALL DEPENDENCIES ARE ALREADY INSTALLED** in the main virtual environment:
- **Location**: `E:\00_dev_1\.venv\`
- **Python Executable**: `E:\00_dev_1\.venv\Scripts\python.exe`
- **Installed Packages**: PyMuPDF (fitz), google-generativeai, google-cloud-vision, google-cloud-storage, PyPDF2, Pillow, ocrmypdf

**DO NOT create new venv or install packages** - everything is ready to use.

### Run Full Pipeline

```powershell
# ALWAYS use the full path to the venv Python executable:
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "G:\Shared drives\12 - legal\a0_fremont_lg\_reedy-v-fremont_all\05_evidence\01_fremont\09_9c1_23-0406-ck\05_Court_Staff" --phase all
```

### Run Single Phase

```powershell
# Phase 1: Directory (organize PDFs)
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "E:\path\to\project" --phase directory

# Phase 2: Rename (extract metadata, clean names)
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "E:\path\to\project" --phase rename

# Phase 3: Clean (OCR at 600 DPI)
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "E:\path\to\project" --phase clean

# Phase 4: Convert (extract text)
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "E:\path\to\project" --phase convert

# Phase 5: Format (clean text with AI)
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "E:\path\to\project" --phase format

# Phase 6: GCS Upload (upload PDFs and insert URLs)
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "E:\path\to\project" --phase gcs_upload

# Phase 7: Verify (compare results)
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "E:\path\to\project" --phase verify

# Phase 8: Repair (fix all documented issues from last verification report)
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "E:\path\to\project" --phase repair

# Repair and Re-verify (one command to fix issues and verify again)
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "E:\path\to\project" --repair-and-verify
```

### Automatic Repair Workflow

After Phase 7 verification identifies issues, use Phase 8 to automatically repair:

```powershell
# Step 1: Run verification to identify issues
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "E:\path\to\project" --phase verify

# Step 2: Review VERIFICATION_REPORT_v31_*.txt to see issues

# Step 3: Repair all documented issues automatically
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "E:\path\to\project" --phase repair

# Step 4: Re-verify to confirm fixes
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "E:\path\to\project" --phase verify

# OR: Use --repair-and-verify shortcut (Steps 3 + 4 combined)
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "E:\path\to\project" --repair-and-verify
```

**Intelligent Repair Strategies (Phase 8)**:

Phase 8 analyzes each issue and applies the appropriate repair strategy:

**STRATEGY 1: Low Accuracy Issues** (< 70% content match)
- **Critical Accuracy (<50%)**:
  - Reprocess PDF with enhanced OCR (1200 DPI, background removal, deskewing)
  - Re-extract text with Google Vision API
  - Reformat with Gemini AI
  - *Use case*: Scanned documents with poor OCR quality, rotated pages, dark backgrounds
  
- **Moderate Accuracy (50-69%)**:
  - Re-extract text with Google Vision API (improved extraction)
  - Reformat with Gemini AI
  - *Use case*: Text extraction issues, missing content, garbled characters
  
- **Borderline Accuracy (70-79%)**:
  - Reformat with Gemini AI only
  - *Use case*: Minor OCR errors, formatting issues

**STRATEGY 2: Page Marker Issues**
- Missing or malformed `[BEGIN PDF Page N]` markers
- Action: Reformat with Gemini to restore proper page markers
- *Use case*: Formatting corruption, missing page boundaries

**STRATEGY 3: Header Issues**
- Missing or incorrect `PDF DIRECTORY` or `PDF PUBLIC LINK` headers
- Action: Update headers in place (no reprocessing needed)
- *Use case*: Metadata inconsistencies after folder moves

**STRATEGY 4: GCS URL Issues**
- Inaccessible or missing public URLs
- Action: Re-upload PDF to Google Cloud Storage and update headers
- *Use case*: Failed uploads, deleted files, bucket configuration changes

**What Phase 8 (Repair) Does**:
1. Reads most recent `VERIFICATION_REPORT_v31_*.txt`
2. Parses "FILES WITH ISSUES" section to identify problem files
3. Analyzes each issue to determine root cause and optimal repair strategy
4. Executes repairs automatically with detailed progress logging
5. Outputs repair summary showing what was fixed

**Enhanced OCR Settings** (for critical accuracy issues):
- 1200 DPI oversample (vs. standard 600 DPI)
- Force OCR on all pages
- Automatic deskewing and rotation correction
- Background removal for scanned documents
- Lower compression (optimize=1) for maximum text quality
- JPEG quality 95% (vs. standard 85%)

**--repair-and-verify Flag**:
- Combines Phase 8 (Repair) + Phase 7 (Verify) in one command
- Automatically fixes issues then generates new verification report
- Useful for iterative quality improvement
- Reports show before/after accuracy metrics

### After Directory Rename

If you renamed a directory after processing, use `--force-reupload` to:
1. Detect old GCS directory from existing text file headers
2. Delete entire old GCS directory
3. Upload all PDFs to new GCS directory
4. Update all text file headers with new directory name and URLs

```powershell
# IMPORTANT: Run from the NEW (renamed) directory location
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "E:\path\to\renamed-project" --phase gcs_upload --force-reupload

# Then re-verify with updated information
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "E:\path\to\renamed-project" --phase verify
```

**What `--force-reupload` does**:
- Reads first text file to detect old directory name from `PDF DIRECTORY:` header
- Deletes ALL files in old GCS path: `gs://fremont-1/docs/<old-folder-name>/`
- Uploads ALL PDFs to new GCS path: `gs://fremont-1/docs/<new-folder-name>/`
- Updates `PDF DIRECTORY:` header in all `04_doc-convert/*_c.txt` files
- Updates `PDF DIRECTORY:` header in all `05_doc-format/*_v31.txt` files
- Updates `PDF PUBLIC LINK:` with correct GCS URLs pointing to new directory
- Essential after renaming directories to keep GCS storage and headers synchronized

**Example**:
```powershell
# Before: G:\...\05_Court_Staff
# After rename: G:\...\05_Court-Staff-9c1

# Run with --force-reupload from NEW location:
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "G:\...\05_Court-Staff-9c1" --phase gcs_upload --force-reupload

# Output will show:
# [DETECT] Old directory: 05_Court_Staff
# [DELETE OLD] Removing old GCS directory: gs://fremont-1/docs/05_Court_Staff/
# [DELETED] docs/05_Court_Staff/file1.pdf
# [DELETED] docs/05_Court_Staff/file2.pdf
# [UPLOAD] file1.pdf → gs://fremont-1/docs/05_Court-Staff-9c1/
# [OK] Updated header in: file1_c.txt
# [OK] Updated header in: file1_v31.txt
```

### Using VS Code Tasks (Recommended)

VS Code tasks are pre-configured in `.vscode/tasks.json`:
1. Press `Ctrl+Shift+P`
2. Type "Tasks: Run Task"
3. Select "Doc Process v31: Full Pipeline"
4. Enter project directory when prompted

Available tasks:
- `Doc Process v31: Full Pipeline`
- `Doc Process v31: OCR Only`
- `Doc Process v31: Extract Only`
- `Doc Process v31: Format Only`
- `Doc Process v31: Verify Only`
- `Doc Process v31: GCS Upload Only`
- `Doc Process v31: OCR+Extract+Format`

## File Suffix Flow

```
filename.pdf
  → filename_d.pdf              (Phase 1: Directory)
  → YYYYMMDD_Name_r.pdf         (Phase 2: Rename)
  → YYYYMMDD_Name_o.pdf         (Phase 3: Clean - searchable PDF/A)
  → YYYYMMDD_Name_c.txt         (Phase 4: Convert - raw text)
  → YYYYMMDD_Name_v31.txt       (Phase 5: Format - cleaned text)
```

## Directory Structure

```
<project>/
├── 01_doc-original/      # Phase 1 output: PDFs with _d suffix
├── 02_doc-renamed/       # Phase 2 output: PDFs with _r suffix  
├── 03_doc-clean/         # Phase 3 output: OCR'd PDFs with _o suffix
├── 04_doc-convert/       # Phase 4 output: Text files with _c.txt suffix
├── 05_doc-format/        # Phase 5 output: Text files with _v31.txt suffix
├── y_logs/               # Processing logs
├── z_old/                # Archived files
└── _failed/              # Dead-letter queue for failed files
    ├── directory/
    ├── rename/
    ├── clean/
    ├── convert/
    └── format/
```

## Phase Details

### Phase 1: Directory
- **Input**: Root directory with raw PDFs
- **Output**: `01_doc-original/`
- **Suffix**: `_d`
- **Action**: Move all PDFs to organized folder

### Phase 2: Rename
- **Input**: `01_doc-original/*_d.pdf`
- **Output**: `02_doc-renamed/`
- **Suffix**: `_r`
- **Tools**: Gemini 2.5 Pro (metadata extraction)
- **Action**: Extract date, clean filename, add YYYYMMDD prefix

### Phase 3: Clean (OCR)
- **Input**: `02_doc-renamed/*_r.pdf`
- **Output**: `03_doc-clean/`
- **Suffix**: `_o`
- **Tools**: PyMuPDF (metadata removal), ocrmypdf 16.11.1 (600 DPI OCR with --optimize 3), Ghostscript (secondary compression)
- **Parallel Processing**: Files <5MB processed in parallel; files ≥5MB processed sequentially to prevent subprocess deadlocks
- **Action**: 
  1. Remove metadata and annotations with PyMuPDF
  2. OCR at 600 DPI with aggressive optimization (--optimize 3, --jpeg-quality 85) → searchable PDF/A
  3. Secondary Ghostscript compression if needed (>10% additional reduction)
  4. Result: High-quality searchable PDFs at reasonable file sizes (prevents 700-850% expansion)

### Phase 4: Convert (Extract)
- **Input**: `03_doc-clean/*_o.pdf`
- **Output**: `04_doc-convert/`
- **Suffix**: `_c.txt`
- **Tools**: Google Cloud Vision API (batch OCR), PyMuPDF (fallback for files >35MB)
- **Parallel Processing**: 5 concurrent workers
- **Action**: 
  1. Extract text in 5-page batches via Google Vision API
  2. Automatic PyMuPDF fallback for files >35MB (overcomes Google Vision 40MB payload limit)
  3. Add structured template with document information header and page markers
  4. Initial GCS URL included (updated in Phase 6)

**Template Structure**:
```
§§ DOCUMENT INFORMATION §§

DOCUMENT NUMBER: TBD
DOCUMENT NAME: <base_name>
ORIGINAL PDF NAME: <filename>
PDF DIRECTORY: <folder_name or path>
PDF PUBLIC LINK: <GCS URL>
TOTAL PAGES: <N>

=====================================================================
BEGINNING OF PROCESSED DOCUMENT
=====================================================================

[BEGIN PDF Page 1]
<page 1 content>

[BEGIN PDF Page 2]
<page 2 content>

=====================================================================
END OF PROCESSED DOCUMENT
=====================================================================
```

### Phase 5: Format
- **Input**: `04_doc-convert/*_c.txt`
- **Output**: `05_doc-format/`
- **Suffix**: `_v31.txt`
- **Tools**: Gemini 2.5 Pro (gemini-2.5-pro, Tier 3, 65536 max tokens, temperature=0.1)
- **Parallel Processing**: 5 concurrent workers via ThreadPoolExecutor
- **Architecture**: Matches v21 approach for optimal formatting preservation
  1. **Extract** header, body, and footer from `_c.txt` template
  2. **Process** only document body through Gemini (no template sent to AI)
  3. **Reassemble** cleaned body with original header/footer
- **Chunking**: Documents >80 pages automatically split into segments
  - Each chunk processed separately through Gemini
  - Chunks consolidated with proper spacing (`\n\n` separator)
  - Maintains page marker formatting across chunk boundaries
  - Tested on 171-page documents (3 chunks of 80+80+11 pages)
- **Action**: Fix OCR errors, remove scanning artifacts, preserve legal structure and page markers
- **Critical Format**: Maintains `\n\n[BEGIN PDF Page N]\n\n` (two blank lines) around all page markers
- **Prompt**: Uses exact v21 prompt for OCR correction without formatting preservation instructions

### Phase 6: GCS Upload
- **Input**: `03_doc-clean/*_o.pdf` + `04_doc-convert/*_c.txt` + `05_doc-format/*_v31.txt`
- **Output**: GCS bucket + updated text files
- **Tools**: Google Cloud Storage
- **Action**: 
  1. Upload all cleaned PDFs to `gs://fremont-1/docs/<folder_name>/`
  2. Generate public URLs for each PDF
  3. Update headers in both `_c.txt` and `_v31.txt` files
- **URL Format**: `https://storage.cloud.google.com/fremont-1/docs/<folder_name>/<filename>`
- **Headers Added**:
  - `PDF Directory: <folder_name>` (or full path for E:\ drive)
  - `PDF Public Link: <GCS URL>`

### Phase 7: Verify
- **Input**: `03_doc-clean/*_o.pdf` + `04_doc-convert/*_c.txt` + `05_doc-format/*_v31.txt`
- **Output**: Verification report + PDF manifest CSV
- **Action**: **Comprehensive validation with actual content comparison** (CRITICAL for legal documents)
  
#### Validation Checks Performed:

**Header Validation**:
- **PDF Directory header**: Verifies header matches actual folder path
- **PDF Public Link format**: Ensures proper public URL format
- **GCS URL accessibility**: Tests if public URLs are accessible (YES/NO indicator)

**Content Validation** (NEW - Critical for Legal Documents):
- **Actual text extraction**: Extracts text from PDF pages for comparison
- **Content matching**: Compares PDF text to formatted TXT content
- **Accuracy scoring**: Confidence percentage (first and last page comparison)
- **OCR quality check**: Detects garbled text, missing content, formatting issues
- **Completeness verification**: Ensures all text was extracted correctly

**Structural Validation**:
- **Page count comparison**: PDF pages vs [BEGIN PDF Page N] markers in text
- **Page marker validation**: Confirms [BEGIN PDF Page 1] exists
- **Character count tracking**: Total characters in formatted text
- **File size comparison**: PDF size (MB) vs TXT size (MB)

**Verification Report Sections**:

1. **Summary**: Total files, verified count, warnings, failures

2. **Files with Issues**: Shows only documents with problems:
   - Specific issue description
   - Affected pages
   - Content accuracy percentage

3. **Detailed Document Comparison Table** (organized by validation type):
   ```
                                           |---- PDF CONVERSION ----|  |---------- TXT CONVERSION ----------|
   Document Name                           | Pages  URL OK  PDF MB  Reduce%  | Pages  Match  Chars      Markers  Accuracy  | Status
   file_name                               | 10     YES     2.14    91.5%    | 10     YES    18,758     YES      86%       | OK
   ```
   
   **Column Groups**:
   
   **PDF CONVERSION** (Verifies online PDF quality):
   - **Pages**: Number of pages in cleaned/OCR'd PDF
   - **URL OK**: GCS public URL accessible (YES/NO) - verifies online availability
   - **PDF MB**: File size after OCR and compression
   - **Reduce%**: Size reduction from original (compression effectiveness)
   
   **TXT CONVERSION** (Verifies text extraction accuracy):
   - **Pages**: Number of [BEGIN PDF Page N] markers in TXT
   - **Match**: YES if PDF pages = TXT page markers (no missing pages)
   - **Chars**: Total character count (verifies content was extracted)
   - **Markers**: YES if [BEGIN PDF Page 1] exists (proper page marking)
   - **Accuracy**: Content match confidence from PDF vs TXT comparison (70%+ is passing)
   
   **Status**: OK (verified) / WARNING (issues found) / FAILED (error)

4. **Document Files and Public URLs**: For each document:
   - PDF: filename, GCS URL, page count, file size
   - TXT: filename, page count, character count, marker validation

5. **CSV Export**: Complete data with all validation metrics

**Content Accuracy Thresholds**:
- ≥70% = PASS (acceptable for legal documents)
- <70% = WARNING (may need reformatting or OCR correction)
- Page marker missing = CRITICAL (incomplete extraction)

#### Automatic Repair Functionality (NEW):

When issues detected, Phase 7 offers automated repair:

```powershell
# Run verification with automatic repair
python doc-process-v31.py --dir "path" --phase verify --auto-repair
```

**Repair Process**:
1. Identifies files with issues (low accuracy, missing markers, bad headers, inaccessible URLs)
2. Determines required repairs:
   - **Content issues** → Re-run Phase 5 (Format) to regenerate text
   - **URL issues** → Re-run Phase 6 (GCS Upload) to upload and update headers
3. Executes repairs automatically or prompts user for confirmation
4. Recommends re-running Phase 7 to confirm fixes

**Manual Repair Options** (if not using --auto-repair):
1. **Re-run Phase 5 (Format)**: Regenerate text with correct headers/content
2. **Re-run Phase 6 (GCS Upload)**: Upload missing files and update URLs
3. **Review specific pages**: Manually check flagged pages in PDF vs TXT

**Example Verification Output**:
```
DETAILED DOCUMENT COMPARISON
======================================================================================================================================================
Document Name                            PDF      TXT      Match  PDF MB    TXT MB    Chars      URL OK  Accuracy  Status  
------------------------------------------------------------------------------------------------------------------------------------------------------
20241017_9c1_RR_Notice_Close_Claim       1        1        YES    0.15      0.00      2,228      YES     98%       OK      
20230906_9c1_FIC_Amended_Petition        6        6        YES    0.88      0.01      7,089      YES     74%       WARNING 
20251030_9c1_FIC_Response_RR_Motion      72       71       NO     11.17     0.09      93,050     YES     44%       WARNING 
```

**Files with Issues**:
```
20230906_9c1_FIC_Amended_Petition_No_Coverage_v31.txt
    - Page 1: Low similarity: 66.40%

20251030_9c1_FIC_Response_RR_Motion_v31.txt
    - Page 72: Page marker not found: [BEGIN PDF Page 72]
    - Low content accuracy: 44%
```

## Performance Comparison

| Operation | v30 (Sequential) | v31 (Parallel) | Speedup |
|-----------|------------------|----------------|---------|
| Rename 10 files | 25s | 8s | 3.1x |
| Extract 10 files | 120s | 35s | 3.4x |
| Format 10 files | 60s | 18s | 3.3x |
| Full pipeline (10 files) | 8-9 min | 3-4 min | 2.5x |

*Actual performance depends on file size, API latency, and hardware*

## Error Handling Example

When a file fails processing:
```
[FAIL] problem_file.pdf: API call failed after 3 retries
[QUARANTINE] Copied problem_file.pdf to _failed/extract/
```

Check quarantine:
```
_failed/
├── extract/
│   ├── problem_file.pdf
│   └── problem_file_error.txt
```

Error log contains:
```
File: problem_file.pdf
Phase: extract
Timestamp: 2025-11-05T14:30:45
Error Type: ApiError
Error Message: Google Vision API rate limit exceeded
```

## Configuration

### Adjust Worker Counts
Edit in `doc-process-v31.py`:
```python
MAX_WORKERS_IO = 5  # API calls (increase if you have high API quota)
MAX_WORKERS_CPU = 3  # OCR operations (match your CPU cores)
```

### Skip Failed Files
Failed files are automatically moved to `_failed/<phase>/` and processing continues.

To retry failed files:
1. Fix the issue (e.g., API quota)
2. Move files back from `_failed/<phase>/` to appropriate input directory
3. Re-run the phase

## Directory Structure

v31 creates additional directories:

```text
<project>/
├── 01_doc-original/
├── 02_doc-renamed/
├── 03_doc-ocr/
├── 04_doc-txt-1/
├── 05_doc-txt-2/
├── y_logs/
├── z_old/
└── _failed/              # NEW in v31
    ├── organize/
    ├── rename/
    ├── ocr/
    ├── extract/
    ├── format/
    └── verify/
```

## Migration from v30

v31 is **backward compatible** with v30:

- Uses same directory structure (plus `_failed/`)
- Same phase names and arguments
- Same output file naming (`_v31.txt` instead of `_v30.txt`)

To migrate:

1. Copy your v30 command
2. Replace `doc-process-v30.py` with `doc-process-v31.py`
3. Run - no other changes needed

## Troubleshooting

### Issue: ModuleNotFoundError: No module named 'fitz'

**DO NOT install packages** - they are already installed in `E:\00_dev_1\.venv\`

**Solution**: Use the full path to the venv Python executable:
```powershell
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py --dir "path" --phase all
```

**Wrong**: `python doc-process-v31.py` (uses system Python without packages)

## After Directory Rename - Comprehensive Reupload

When you rename a directory locally and need to synchronize with GCS, use the `--force-reupload` flag to trigger a comprehensive 6-step process:

### What --force-reupload Does:

1. **Creates Directory Structure Documentation** (`y_logs/DIRECTORY_STRUCTURE_MANIFEST.txt`)
   - Records root directory, folder name, PDF directory path
   - Documents GCS bucket and full path for future reference

2. **Creates Document Catalog** (`y_logs/DOCUMENT_CATALOG.txt`)
   - Lists all documents in each pipeline stage (03, 04, 05 directories)
   - Shows GCS target path and public URL for each document
   - Identifies missing convert or format files

3. **Verifies GCS Directory Structure**
   - Checks if GCS directory already exists
   - Prepares for upload or deletion operations

4. **Manages GCS Uploads**
   - Detects old GCS directory from existing text file headers
   - **Deletes entire old GCS directory** (all files with old prefix)
   - Uploads all PDFs to new GCS location
   - Makes all files publicly accessible
   - Creates upload log (`y_logs/UPLOAD_LOG_YYYYMMDD_HHMMSS.txt`)

5. **Updates Headers in Convert and Format Files**
   - Updates `PDF DIRECTORY:` line in all `04_doc-convert/*_c.txt` files
   - Updates `PDF PUBLIC LINK:` line in all `04_doc-convert/*_c.txt` files
   - Updates `PDF DIRECTORY:` line in all `05_doc-format/*_v31.txt` files  
   - Updates `PDF PUBLIC LINK:` line in all `05_doc-format/*_v31.txt` files
   - Ensures all headers reflect new directory structure

6. **Verifies Header Consistency** (`y_logs/HEADER_VERIFICATION_YYYYMMDD_HHMMSS.txt`)
   - Checks every convert and format file
   - Verifies `PDF DIRECTORY:` matches expected path
   - Verifies `PDF PUBLIC LINK:` matches expected GCS URL
   - Reports mismatches and missing files

### Example Workflow:

```powershell
# Scenario: You renamed directory from 09_Pleadings_plaintiff to 01_Pleadings_plaintiff

# Run force-reupload (will detect old directory 09, delete it, upload to new 01)
E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py `
    --dir "G:\Shared drives\...\01_Pleadings_plaintiff" `
    --phase gcs_upload verify `
    --force-reupload `
    --no-verify

# Check logs to verify:
# - y_logs/DIRECTORY_STRUCTURE_MANIFEST.txt (structure documentation)
# - y_logs/DOCUMENT_CATALOG.txt (complete file inventory)
# - y_logs/UPLOAD_LOG_YYYYMMDD_HHMMSS.txt (upload results)
# - y_logs/HEADER_VERIFICATION_YYYYMMDD_HHMMSS.txt (header consistency check)
```

### What Gets Updated:

**Before force-reupload:**
```
PDF DIRECTORY: 09_Pleadings_plaintiff
PDF PUBLIC LINK: https://storage.cloud.google.com/fremont-1/docs/09_Pleadings_plaintiff/20230807_9c1_FIC_Petition_Umpire_o.pdf
```

**After force-reupload:**
```
PDF DIRECTORY: 01_Pleadings_plaintiff
PDF PUBLIC LINK: https://storage.cloud.google.com/fremont-1/docs/01_Pleadings_plaintiff/20230807_9c1_FIC_Petition_Umpire_o.pdf
```

**Old GCS directory deleted:**
- `gs://fremont-1/docs/09_Pleadings_plaintiff/` → Removed (all 30+ files deleted)

**New GCS directory created:**
- `gs://fremont-1/docs/01_Pleadings_plaintiff/` → Uploaded (all 30 PDFs with public access)

### Verification Logs:

All operations generate detailed logs in `y_logs/`:
1. `DIRECTORY_STRUCTURE_MANIFEST.txt` - Directory paths and GCS configuration
2. `DOCUMENT_CATALOG.txt` - Complete inventory of all files in pipeline
3. `UPLOAD_LOG_YYYYMMDD_HHMMSS.txt` - Upload results (success/fail for each file)
4. `HEADER_VERIFICATION_YYYYMMDD_HHMMSS.txt` - Header consistency report (mismatches flagged)

These logs provide full audit trail for directory rename operations.
**Right**: `E:\00_dev_1\.venv\Scripts\python.exe doc-process-v31.py`

### Issue: Files failing due to API rate limits

**Solution**: Lower MAX_WORKERS_IO from 5 to 3 or 2

### Issue: OCR taking too long

**Solution**: Increase MAX_WORKERS_CPU (up to your CPU core count)

### Issue: Out of memory errors

**Solution**: Lower both MAX_WORKERS_IO and MAX_WORKERS_CPU

### Issue: Want to see which files failed

**Solution**: Check `_failed/` directory for quarantined files and error logs

## See Also

- v30 README: `../doc-process-v30/README.md`
- Wrapper scripts: `ocr.py`, `extract.py`, `format.py`, `verify.py`
- VS Code tasks: `.vscode/tasks.json`
