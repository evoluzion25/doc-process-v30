# Document Processing Pipeline v30

## Purpose

Automated 6-phase pipeline for processing legal documents with intelligent file organization, AI-powered renaming, OCR enhancement, and text extraction optimized for large legal case files.

**Key improvements over v22:**
- Intelligent file renaming using Gemini AI (extracts dates, parties, descriptions)
- Google Vision API-exclusive text extraction (faster, more accurate than PyMuPDF)
- 5-directory structure for better workflow separation
- Enhanced verification comparing final text to source PDFs
- Smart suffix handling preventing duplicates

## Architecture

### Directory Structure
```
<target-directory>/
├── 01_doc-original/         # Original PDFs with _o suffix
├── 02_doc-renamed/          # Intelligently renamed PDFs with _r suffix
├── 03_doc-ocr/              # OCR-enhanced PDFs with _o suffix
├── 04_doc-txt-1/            # Extracted raw text with _o.txt suffix
├── 05_doc-txt-2/            # AI-formatted text with _v30.txt suffix
├── y_logs/                  # Processing logs and activity records
├── z_old/                   # Archived files
└── VERIFICATION_REPORT_v30_<timestamp>.txt
```

**Note:** All 7 directories are created automatically in Phase 1 before any file processing begins.

### File Naming Convention
**Target format:** `YYYYMMDD_PARTY_Description_<suffix>.pdf`

**Examples:**
- `20231226_9c1_Hearing_r.pdf`
- `20240212_3c2_RR_Complaint-v1_r.pdf`
- `20240502_9c2_RR_Stipulated-Agreement-to-Delay-Answer_r.pdf`

**Recognized party acronyms:**
- `RR` = Reedy
- `FIC` = Fremont Insurance Company
- `9c1`, `9c2`, `3c1`, `3c2` = Case identifiers
- `Court`, `Clerk` = Court documents

## Phases

### Phase 0: Pre-flight Checks
**Purpose:** Verify all credentials and tools before processing

**Validates:**
- Gemini API Key present
- Google Cloud Vision credentials configured
- ocrmypdf installed and accessible
- Ghostscript (gswin64c) available
- PyMuPDF (fitz) library present

**Critical:** Pre-flight is phase-aware. When running only extract/format/verify, OCR tooling checks (ocrmypdf/Ghostscript) are skipped so you can proceed without those tools installed.

### Phase 1: Organize
**Purpose:** Move PDFs from root directory to organized structure

**Actions:**
1. Create ALL pipeline directories upfront:
   - `01_doc-original/` - Source PDFs
   - `02_doc-renamed/` - Renamed PDFs
   - `03_doc-ocr/` - OCR-enhanced PDFs
   - `04_doc-txt-1/` - Extracted text files
   - `05_doc-txt-2/` - AI-formatted text
   - `y_logs/` - Processing logs
   - `z_old/` - Archive directory
2. Move all root-level PDFs to `01_doc-original/`
3. Add or replace `_o` suffix (prevents duplicates like `_o_o.pdf`)
4. Intelligent suffix handling removes old version suffixes (_a, _r, _t, _c, _v22, _v30) before adding _o
5. Skip files already in correct location

**Input:** `*.pdf` in root directory  
**Output:** `01_doc-original/*_o.pdf`

**Critical:** Directory structure is completely established before any file operations begin.

### Phase 2: Smart Rename
**Purpose:** Apply intelligent naming using AI metadata extraction

**Actions:**
1. Check if filename already matches `YYYYMMDD_PARTY_Description_*.pdf` pattern
2. If valid pattern exists, keep existing name (change `_o` → `_r`)
3. If invalid/missing pattern, use Gemini to extract:
   - Document date (filing date, hearing date, etc.)
   - Party identification (plaintiff, defendant, court)
   - Case number/acronym if present
   - Short description (2-4 hyphenated words)
4. Apply recognized acronyms (RR, FIC, 9c1, 9c2, etc.)
5. Copy to `02_doc-renamed/` with `_r` suffix

**Input:** `01_doc-original/*_o.pdf`  
**Output:** `02_doc-renamed/YYYYMMDD_PARTY_Description_r.pdf`

**AI Model:** Gemini 2.5 Pro (metadata extraction)

### Phase 3: OCR Enhancement
**Purpose:** Create searchable, standardized PDF/A documents

**Actions:**
1. Copy renamed PDFs to `03_doc-ocr/`
2. Remove all metadata, bookmarks, annotations
3. Convert to PDF/A format (archival standard)
4. Apply OCR at 600 DPI resolution
5. Use ocrmypdf as primary tool
6. Fallback to Ghostscript pdfimage32 device if ocrmypdf fails
7. Compress PDF files to reduce size (maintains searchability)
8. Change suffix from `_r` to `_o`

**Compression**: Uses Ghostscript `/ebook` setting (150dpi images) which:
- Reduces file size by 50-80% typically
- Preserves OCR text layer (full searchability maintained)
- Only applied if >10% size reduction achieved

**Input:** `02_doc-renamed/*_r.pdf`  
**Output:** `03_doc-ocr/*_o.pdf`

**Tools:** ocrmypdf, Ghostscript, Tesseract OCR

### Phase 4: Text Extraction
**Purpose:** Extract all text using Google Vision API

**Actions:**
1. Process each PDF using Google Cloud Vision Document Text Detection
2. Handle API 5-page batch limit automatically
3. Extract text from all pages sequentially
4. Add document template with metadata header and footer
5. Format page markers as "[BEGIN PDF Page X]" with blank lines
6. Save raw extracted text to `04_doc-txt-1/`
7. Preserve page order and content structure

**CRITICAL:** This phase uses **ONLY** Google Vision API. No PyMuPDF fallback.

**Input:** `03_doc-ocr/*_o.pdf`  
**Output:** `04_doc-txt-1/*_o.txt`

**API:** Google Cloud Vision API (Document Text Detection)

### Phase 5: AI Formatting
**Purpose:** Clean and format extracted text using legal document template

**Actions:**
1. Archive any existing `*_v30.txt` files to `05_doc-txt-2/_old/`
2. Extract content section from Phase 4 output (between header/footer markers)
3. Send only content to Gemini with legal document formatting prompt
4. Reassemble with original Phase 4 header and footer preserved
5. Fix OCR errors and formatting issues within content
6. Save formatted text with `_v30.txt` suffix

**Input:** `04_doc-txt-1/*_o.txt`  
**Output:** `05_doc-txt-2/*_v30.txt`

**AI Model:** Gemini 2.5 Pro with 65,536 max output tokens

**CRITICAL PROMPT (DO NOT MODIFY):**
```
You are an expert legal document formatter. Clean and format this legal document text while preserving all meaningful content.

CRITICAL RULES:
1. Preserve ALL substantive content - do not omit any legal arguments, facts, or citations
2. Fix OCR errors and formatting issues
3. Use proper paragraphing and line breaks
4. Format citations correctly
5. Preserve ALL page numbers in the format: [PAGE X]
6. Keep headers/footers only if substantively relevant
7. Remove redundant spacing but preserve paragraph structure
8. Use consistent formatting throughout
9. Preserve ALL exhibits, attachments, and referenced documents
10. Maintain chronological order of content

OUTPUT FORMAT:
- Start each new page with [PAGE X] on its own line
- Use blank lines to separate distinct sections
- Use proper indentation for quotes and sub-sections
- Format lists with bullets or numbers as appropriate
- Preserve table structures where present

Return ONLY the cleaned text with [PAGE X] markers. No explanations or meta-commentary.
```

### Phase 6: Deep Verification
**Purpose:** Compare formatted text to source PDFs for accuracy

**Actions:**
1. Compare each `*_v30.txt` file to corresponding `*_o.pdf`
2. Count PDF pages vs formatted page markers
3. Check character counts for reasonable length
4. Flag files with:
   - Missing page markers
   - Page count mismatches >2 pages
   - Unusually short text (<1000 chars)
5. Generate detailed verification report

**Input:** `03_doc-ocr/*_o.pdf` + `05_doc-txt-2/*_v30.txt`  
**Output:** `VERIFICATION_REPORT_v30_<timestamp>.txt`

**Report includes:**
- Total files processed
- Files verified OK
- Files with warnings
- Files failed
- Detailed per-file analysis

## Dependencies

### Required Tools
- **Python 3.10+**
- **ocrmypdf 16.x**
- **Ghostscript 10.06.0+**
- **Tesseract OCR**

### Required Python Packages
```bash
pip install PyMuPDF google-cloud-vision google-cloud-storage google-generativeai python-dotenv
```

**Package details:**
- `PyMuPDF` (fitz): PDF manipulation.
- `google-cloud-vision`: Google Cloud Vision API client.
- `google-cloud-storage`: Google Cloud Storage client.
- `google-generativeai`: Google Gemini API client.
- `python-dotenv`: For loading secrets from a `.env` file.

## API & Environment Setup

This project uses a `.env` file to manage all API keys and configuration. This ensures that no sensitive information is ever committed to the repository.

### Step 1: Create the `.env` File

In the root of the project, create a file named `.env`.

### Step 2: Add Configuration to `.env`

Add the following variables to your `.env` file and replace the placeholder values with your actual credentials.

```bash
# Google Gemini API Key
# Get this from Google AI Studio: https://aistudio.google.com/app/apikey
GOOGLEAISTUDIO_API_KEY="your-gemini-api-key-here"

# Google Cloud Service Account Credentials
# Create a service account in your GCP project and download its JSON key.
# Provide the absolute path to that JSON file here.
GOOGLE_APPLICATION_CREDENTIALS="C:/path/to/your/gcp-credentials.json"

# Google Cloud Storage Bucket
# The name of the GCS bucket where OCR'd documents will be stored.
GCS_BUCKET="your-gcs-bucket-name-here"
```

### Step 3: Set Google Cloud Permissions

The service account specified in `GOOGLE_APPLICATION_CREDENTIALS` needs the following roles on your GCS bucket to be able to upload and manage files:

- **Storage Object Creator** (`roles/storage.objectCreator`)
- **Storage Object Viewer** (`roles/storage.objectViewer`)

You can grant these permissions using the following `gcloud` commands:

```bash
# Replace [BUCKET_NAME] and [SERVICE_ACCOUNT_EMAIL] with your values
gcloud storage buckets add-iam-policy-binding gs://[BUCKET_NAME] --member="serviceAccount:[SERVICE_ACCOUNT_EMAIL]" --role="roles/storage.objectCreator"
gcloud storage buckets add-iam-policy-binding gs://[BUCKET_NAME] --member="serviceAccount:[SERVICE_ACCOUNT_EMAIL]" --role="roles/storage.objectViewer"
```

Once you have completed these steps, the script will be able to authenticate and run correctly in any environment.

## Google Cloud Storage Sync

### What’s uploaded

- Only `03_doc-ocr/*.pdf` are uploaded.
- Objects are stored at: `gs://<GCS_BUCKET>/docs/<project-directory>/<filename>.pdf`.

### Access defaults (v30.6)

- Bucket: `fremont-1` (via `GCS_BUCKET`).
- Access: authentication required by default (objects are not public).
- Phase 4 headers include `PDF PUBLIC URL` set to:
  `<https://storage.googleapis.com/<GCS_BUCKET>/docs/<project>/<filename>.pdf>`.
  If objects are private, this URL requires a logged-in identity with access (e.g., <ryan@rg1.us>).

### Anti-indexing

- `robots.txt` at bucket root discourages crawling.
- Objects under `docs/*` include metadata to prevent indexing (noindex).

### Signed URLs (optional)

- A helper exists to generate time-limited signed links for sharing without changing ACLs.
- Use this when you need external access without making objects public.

### Re-embed links when changing buckets/ACLs

- If you change `GCS_BUCKET` or object permissions after extraction, re-run Phase 4 to regenerate headers so they point to the current bucket/ACL state.

## Usage

### Run All Phases

```powershell
$env:Path = "E:\.venv\Scripts;C:\Program Files\Tesseract-OCR;" + $env:Path
E:\.venv\Scripts\python.exe E:\00_dev_1\y_apps\x3_doc-processing\doc-process-v30\doc-process-v30.py --phase all --dir "E:\path\to\case\directory"
```

### Run Individual Phases

```powershell
# Organize only
python doc-process-v30.py --phase organize --dir "E:\path\to\directory"

# Rename only
python doc-process-v30.py --phase rename --dir "E:\path\to\directory"

# OCR only
python doc-process-v30.py --phase ocr --dir "E:\path\to\directory"

# Extract only
python doc-process-v30.py --phase extract --dir "E:\path\to\directory"

# Format only
python doc-process-v30.py --phase format --dir "E:\path\to\directory"

# Verify only
python doc-process-v30.py --phase verify --dir "E:\path\to\directory"
```

### Run Multiple Specific Phases

```powershell
python doc-process-v30.py --phase ocr extract format verify --dir "E:\path\to\directory"
```

### VS Code tasks (recommended)

- Doc Process v30: Full Pipeline — prompts for a project directory and runs all phases
- Doc Process v30: Extract Only — prompts for a project directory and runs Phase 4

Location: `.vscode/tasks.json` at the workspace root.

## Important Notes

### Google Vision API is MANDATORY

- Phase 4 (text extraction) uses **ONLY** Google Cloud Vision API
- No PyMuPDF fallback exists in v30 (unlike v22)
- Ensures consistent, high-quality text extraction
- Handles complex layouts, tables, and multi-column documents better than PyMuPDF

### Gemini Prompt is LOCKED

- The Phase 5 formatting prompt is **exact** and **tested**
- DO NOT modify the prompt text
- DO NOT change temperature, max tokens, or model name
- Changes will break verification and reduce output quality
- Prompt designed specifically for legal documents with page markers

### Processing Large Files

- Gemini 2.5 Pro Tier 3 required for large legal documents (100+ pages)
- 65,536 token output limit handles most cases
- Files exceeding token limit will be truncated (rare with legal docs)
- Google Vision batch processing handles documents of any size

### Suffix Handling

- Phase 1: Adds/replaces `_o` (prevents `_o_o` duplicates)
- Phase 2: Changes `_o` → `_r` (renamed)
- Phase 3: Changes `_r` → `_o` (OCR-enhanced)
- Phase 4: Keeps `_o` for `.txt` files
- Phase 5: Changes `_o.txt` → `_v30.txt` (formatted)

### Verification Warnings

- Page count mismatches are acceptable if <2 pages difference
- Gemini may reformat content affecting page breaks
- Short text lengths (<1000 chars) flagged for review
- Verification report identifies all deviations

## Troubleshooting

### Pre-flight Fails

1. Check `secrets_global` file exists and contains API keys
3. Verify Google Cloud credentials JSON file exists
4. Ensure ocrmypdf and Ghostscript in PATH
5. Install missing Python packages: `pip install PyMuPDF google-cloud-vision google-generativeai`

### Phase 4 Document Template

Phase 4 now generates complete document templates with:
- **Header:** Document metadata (name, PDF path, total pages, separators)
- Includes: `PDF PUBLIC URL` pointing to the Cloud Storage object path
- **Content:** Text with bracketed page markers `[BEGIN PDF Page X]`
- **Footer:** End-of-document separator

Phase 5 preserves these headers/footers and only formats the content section.

### OCR Failures

1. Try running Phase 3 individually to isolate issue
2. Check Ghostscript installed: `gswin64c --version`
3. Verify Tesseract in PATH: `tesseract --version`
4. Large/complex PDFs may timeout - Ghostscript fallback will engage

### Google Vision Errors

1. Verify credentials path in `secrets_global`
2. Check service account has Vision API enabled
3. "At most 5 pages" error should not occur (automatic batching)
4. Check API quota limits in Google Cloud Console

### Gemini Formatting Issues

1. Verify API key valid and Tier 3 access enabled
2. Check model name is exactly `gemini-2.5-pro`
3. Large documents may hit token limits (increase if needed)
4. Do NOT modify the formatting prompt

### Verification Issues

- Review flagged files manually
- Page count differences <3 pages usually acceptable
- Check PDF visually if character count very low
- Gemini reformatting may change page breaks

## Version History

**v30.6 (November 5, 2025)**
- Cloud Storage: moved OCR PDF hosting to `gs://fremont-1/docs/<project>/`, authentication required by default
- Phase-aware preflight: skip ocrmypdf/Ghostscript checks when running only extract/format/verify
- Phase 4 headers now include `PDF PUBLIC URL`; added optional signed URL helper
- Docs: added Cloud Storage sync and VS Code tasks; standardized API key env to `GOOGLEAISTUDIO_API_KEY`

**v30.5 (November 5, 2025)**
- Added Cloud Storage sync for `03_doc-ocr` and embedded URL in Phase 4 headers
- Fixed spacing around page markers and improved batching handling

**v30.1 (November 4, 2024)**
- **OPTIMIZATION:** Phase 1 now creates all 7 directories upfront before moving any files
- Added y_logs/ and z_old/ utility directories for workspace organization
- Improved Phase 2 error handling for Gemini API responses (None/dict validation)
- Removed redundant mkdir() calls from Phases 2-5 (all directories pre-created in Phase 1)
- GitHub repository: https://github.com/evoluzion25/doc-process-v30

**v30.0 (November 4, 2024)**
- Complete architectural redesign from v22
- Added intelligent Gemini-powered file renaming
- Switched to Google Vision API-exclusive text extraction
- Implemented 5-directory workflow structure
- Enhanced verification comparing PDFs to final text
- Smart suffix handling preventing duplicates
- Added [PAGE X] markers in Phase 4, preserved in Phase 5, verified in Phase 6

**v22 (Previous)**
- Monolithic architecture (512 lines)
- 3-directory structure
- PyMuPDF text extraction with Google Vision fallback
- Basic Gemini formatting
- Simple verification

## Performance

**Typical processing times (per document):**
- Phase 1 (Organize): <1 second
- Phase 2 (Rename): 2-5 seconds (Gemini metadata extraction)
- Phase 3 (OCR): 30-120 seconds (depending on page count)
- Phase 4 (Extract): 10-60 seconds (Google Vision batching)
- Phase 5 (Format): 5-20 seconds (Gemini formatting)
- Phase 6 (Verify): 1-3 seconds

**Large document example (114 pages):**
- OCR: ~6 minutes (Ghostscript fallback)
- Extract: ~2 minutes (Google Vision)
- Format: ~15 seconds (Gemini)
- Total: ~8-9 minutes

## Support

**Location:** `E:\00_dev_1\y_apps\x3_doc-processing\doc-process-v30\`

**Related files:**
- `doc-process-v30.py` - Main pipeline script (1100+ lines)
- `README.md` - This documentation
- Example reference: `E:\01_prjct_active\02_legal_system_v1.2\x_docs\03_kazoo-county\06_9c1-23-0406-ck\04_Hearings\20231226_9c1_Hearing_o.pdf`

**Previous versions:**
- v22: `E:\00_dev_1\y_apps\x3_doc-processing\z_old-versions\doc-process-v22\`
- v21: `E:\00_dev_1\y_apps\x3_doc-processing\doc-process-v21\`

---

## Changelog

### v30.4 (November 4, 2025)
**Document Template & Page Marker Updates**
- Updated directory names for clarity:
  - `01_pdf-original` → `01_doc-original`
  - `02_pdf-renamed` → `02_doc-renamed`
  - `03_pdf-ocr` → `03_doc-ocr`
  - `04_pdf-txt` → `04_doc-txt-1`
  - `05_pdf-formatted` → `05_doc-txt-2`
- Changed Phase 3 suffix from `_t` to `_o` for consistency
- Updated all phase references to use `_o` suffix for OCR files
- **Fixed Phase 5 to use v22 exact Gemini prompt and model configuration**
  - Restored original prompt: *"You are correcting OCR output for a legal document..."*
  - Same temperature (0.1) and generation config as v22
  - Ensures consistent formatting results
- **Fixed metadata cleanup errors in Phase 3**
  - Now saves to temp file and replaces to avoid PyMuPDF incremental save issues
  - Metadata removal now works reliably
- **Added automatic PDF compression in Phase 3**
  - Uses Ghostscript `/ebook` setting after OCR
  - Reduces file size 50-80% while preserving OCR text layer
  - Only applies compression if >10% size reduction achieved
  - Maintains full searchability
- Implemented complete document template in Phase 4:
  - Header section with document metadata (name, PDF path, total pages)
  - "§§ DOCUMENT INFORMATION §§" and separator lines
  - Content section with bracketed page markers: `[BEGIN PDF Page X]`
  - Footer section with "END OF PROCESSED DOCUMENT" separator
- Added blank line spacing around page markers (above and below)
- Updated Phase 5 to preserve Phase 4 headers/footers:
  - Extracts only content section between markers
  - Sends content to Gemini for formatting
  - Reassembles with original header and footer intact
- Changed page marker format from `[PAGE X]` to `[BEGIN PDF Page X]`

### v30.3 (November 4, 2025)
**Interactive Mode & Resume Capability**
- Added interactive menu system for user-friendly operation
  - Choose full pipeline or individual phases
  - Optional verification before each phase
  - Confirmation prompts with skip option
- Implemented resume capability - skips already processed files
  - Each phase checks if output file exists before processing
  - Reports skipped count at end of each phase
  - Allows moving completed files to `_completed/` and resuming
- Enhanced error handling with continue/stop prompts
  - Catches KeyboardInterrupt (Ctrl+C) gracefully
  - Asks user to continue or stop on errors
  - Each phase wrapped in try-except for isolation
- Improved OCR fallback logic
  - Direct copy as last resort if OCR fails
  - Better Ghostscript error handling
  - Continues processing remaining files on failures
- Added `_old/`, `_log/`, `_completed/` subdirectories support
  - Files in underscore-prefixed directories are ignored
  - Allows better organization during processing

### v30.2 (November 4, 2025)
**Filename Cleaning & Deduplication**
- Enhanced clean_filename() function
  - Removes initial date prefixes (e.g., "23 - ", "1.1.23 - ")
  - Removes timestamps (e.g., "02-26T11-24")
  - Removes email addresses in brackets
  - Replaces spaces and dashes with underscores
  - Handles multiple date formats (M.D.YY, YYYY-MM-DD)
- Intelligent compilation detection
  - Files with "Ex. P1" or "Exhibit" get RR_ prefix
  - Preserves exhibit numbering and structure
- Deduplication logic
  - Tracks used filenames to prevent collisions
  - Adds counter suffix (_2, _3) when needed

### v30.1 (November 4, 2025)
**Directory Optimization**
- Refactored Phase 1 to create all 7 directories upfront before moving files
- Added ensure_directory_structure() function called by all phases
- Made all phases independently executable
- Standardized API key naming to GOOGLEAISTUDIO_API_KEY across all versions

---

**Created:** November 4, 2025  
**Author:** AI Agent for Legal System v1.2  
**Workspace:** E:\DevWorkspace\00_dev_1\y_apps\x3_doc-processing\
