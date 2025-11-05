# Document Processing v21 - Complete Instructions

**Version**: 21
**Date**: November 4, 2025
**Location**: `E:\00_dev_1\y_apps\x3_doc-processing\doc-process-v21\`
**Scripts**: Modular 4-phase pipeline (phase1-4 individual scripts)
**Credentials**: Loaded from `E:\00_dev_1\01_secrets\secrets_global`
**Tools**: PyMuPDF, Gemini 2.5 Pro, Google Cloud Vision API

---

## HIGH-LEVEL SUMMARY

### 4 Processing Phases (Modular Scripts)

**Phase 1: PDF-A Creation**  
Script: `phase1_pdfa_ocr.py`
Convert original PDFs to clean PDF-A → Output: `x0_pdf-a/{name}_a.pdf`
Strips metadata, bookmarks, comments for legal filing

**Phase 2: Text Conversion**  
Script: `phase2_convert_to_text.py`
Extract text with page markers → Output: `x1_converted/{name}_c.txt`
Preserves page structure with [BEGIN PDF Page N] markers

**Phase 3: AI Cleaning**  
Script: `phase3_clean_with_gemini.py`
Clean text with Gemini + apply template → Output: `x2_cleaned/{name}_v21.txt`
Fixes OCR errors, formats for court, adds header/footer

**Phase 4: Verification**  
Script: `phase4_verify_accuracy.py`
Compare cleaned text vs original PDF-A → Output: `x3_verified/VERIFICATION_REPORT_{timestamp}.txt`
Checks word accuracy, page markers, generates detailed report

**Goal**: Create court-ready PDF-A files and verified clean text for legal citations

---

## PHASE 1 DETAILS: PDF-A CREATION (CLEAN FOR LEGAL FILING)

### What This Phase Does
Creates clean, searchable PDF-A files ready for legal filing by stripping all metadata, comments, and bookmarks.

**Script**: `phase1_pdfa_ocr.py`

**Input**: PDF files in case folder root
- `*_o.pdf` or `*.pdf`
- Location: ROOT_DIR (configured in script)

**Output**: Clean PDF-A files
- Directory: `x0_pdf-a/` (created automatically if missing)
- Naming: `{basename}_a.pdf`
- Format: PDF-A (searchable, compressed)
- Metadata: Stripped clean
- Bookmarks: Removed
- Comments: Removed

**Tools**:
- PyMuPDF (fitz) - PDF manipulation and compression

**Process**:
1. Create `x0_pdf-a/` directory if it doesn't exist
2. Find all PDFs in root directory (not ending in _a)
3. For each PDF:
   - Open original PDF
   - Create new PDF copying only page content
   - Strip all metadata (author, title, dates, etc.)
   - Remove all bookmarks/TOC
   - Remove all comments/annotations
   - Compress with garbage=4, deflate=True, clean=True
   - Save as PDF-A with `_a` suffix

**Usage**:
```bash
E:\.venv\Scripts\python.exe phase1_pdfa_ocr.py
```

**Verification Output**:
- Pages copied: All pages preserved
- Bookmarks: 0
- Metadata: Cleared
- File size: Optimized with compression

**Example Output**:
```
20240628_9c1_ROA_o.pdf → 20240628_9c1_ROA_a.pdf (5 pages, 0 bookmarks, metadata cleared)
```

---

## PHASE 2 DETAILS: TEXT CONVERSION

### What This Phase Does
Extracts text from clean PDF-A files with page markers for exact citations.

**Script**: `phase2_convert_to_text.py`

**Input**: Clean PDF-A files from x0_pdf-a
- `*_a.pdf`
- Location: `x0_pdf-a/`

**Output**: Raw text files
- Directory: `x1_converted/` (created automatically)
- Naming: `{basename}_c.txt`
- Format: Plain text with page markers
- Page markers: `[BEGIN PDF Page N]`

**Tools**:
- PyMuPDF (fitz) - PDF text extraction

**Process**:
1. Find all *_a.pdf files in x0_pdf-a/
2. For each PDF:
   - Open with PyMuPDF
   - For each page:
     - Add page marker: `[BEGIN PDF Page N]`
     - Extract text: `page.get_text()`
     - Append to output
3. Save as *_c.txt in x1_converted/

**Usage**:
```bash
E:\.venv\Scripts\python.exe phase2_convert_to_text.py
```

**Example Output**:
```
[BEGIN PDF Page 1]

STATE OF MICHIGAN
CIRCUIT COURT FOR THE COUNTY OF KALAMAZOO

[BEGIN PDF Page 2]

Plaintiff Fremont Insurance Company hereby...
```

**Verification Output**:
```
20240628_9c1_ROA_a.pdf → 20240628_9c1_ROA_c.txt
  [OK] Extracted 9,694 characters from 5 pages
```

---

## PHASE 3 DETAILS: AI CLEANING WITH GEMINI

### What This Phase Does
AI-powered text cleaning with document template for court-ready formatting.

**Script**: `phase3_clean_with_gemini.py`

**Input**: Raw text from x1_converted
- `*_c.txt`
- Location: `x1_converted/`

**Output**: Cleaned text with template
- Directory: `x2_cleaned/` (created automatically)
- Naming: `{basename}_v21.txt`
- Format: Clean text with header/footer template
- Version: v21 (matches script version)

**Tools**:
- Gemini 2.5 Pro (google-generativeai)
- Temperature: 0.1 (minimal creativity, maximum accuracy)
- Max tokens: 65536

**Secrets Required**:
- GEMINI_API_KEY (loaded from `E:\00_dev_1\01_secrets\secrets_global`)

**Process**:
1. Load secrets from secrets_global
2. Archive all existing *_g*.txt and *_v*.txt files to _old/
3. For each *_c.txt file:
   - Read raw text
   - Send to Gemini 2.5 Pro with cleaning prompt
   - Apply document template (header/footer)
   - Add EXHIBIT separators (70-char dashed lines)
   - Save as *_v21.txt

**Gemini Prompt**:
```
You are correcting OCR output for a legal document. Your task is to fix OCR errors, 
preserve legal terminology, format page markers as [BEGIN PDF Page N], and ensure 
the document is court-ready with lines under 65 characters and proper paragraph breaks. 
Return only the corrected text.
```

**Document Template Applied**:
```
§§ DOCUMENT INFORMATION §§

DOCUMENT NUMBER: TBD
DOCUMENT NAME: {basename}
ORIGINAL PDF NAME: {basename}_a.pdf
PDF DIRECTORY: {full_path_to_pdf}
TOTAL PAGES: {page_count}

=====================================================================
BEGINNING OF PROCESSED DOCUMENT
=====================================================================

{GEMINI_CLEANED_TEXT}

=====================================================================
END OF PROCESSED DOCUMENT
=====================================================================
```

**EXHIBIT Handling**:
Any line containing "EXHIBIT X" (where X is single letter/number) gets wrapped:
```
----------------------------------------------------------------------
EXHIBIT A
----------------------------------------------------------------------
```

**Usage**:
```bash
E:\.venv\Scripts\python.exe phase3_clean_with_gemini.py
```

**Example Output**:
```
Processing: 20240628_9c1_ROA_c.txt -> 20240628_9c1_ROA_v21.txt
  [OK] Cleaned and templated
```

---

## PHASE 4 DETAILS: VERIFICATION & ACCURACY REPORT

### What This Phase Does
Compares cleaned text against original PDF-A files to verify accuracy, check page markers, and detect missing words.

**Script**: `phase4_verify_accuracy.py`

**Input**: 
- Cleaned text from x2_cleaned: `*_v21.txt`
- Original PDFs from x0_pdf-a: `*_a.pdf`

**Output**: Verification report
- Directory: `x3_verified/` (created automatically)
- Naming: `VERIFICATION_REPORT_{timestamp}.txt`
- Format: Detailed text report with metrics

**Tools**:
- PyMuPDF (fitz) - PDF text extraction for comparison
- difflib - Similarity calculation
- Custom normalization - Filters OCR artifacts

**Metrics Calculated**:
1. **Overall Similarity** (per file): Word-based Jaccard + sequence similarity (70/30 weighted)
2. **Page-by-Page Similarity**: Individual page comparisons
3. **Missing Words**: Words in PDF not in cleaned (filters artifacts)
4. **Added Words**: Words in cleaned not in PDF
5. **Page Count Match**: Verify page markers match PDF pages

**Normalization (Filters OCR Artifacts)**:
- URLs removed (common in headers)
- Date stamps removed (06282024, 071624)
- Page markers removed (pagepfs, pafe4pf5)
- "Printed" timestamps removed
- Single letters and pure numbers filtered (OCR noise)
- Mixed alphanumeric garbage filtered (q3j7, complainta)

**Similarity Thresholds**:
- **Perfect**: >85% (ready for legal use)
- **Good**: 75-85% (minor review recommended)
- **Warning**: 65-75% (review for legal accuracy)
- **Fail**: <65% (manual review required)

**Usage**:
```bash
E:\.venv\Scripts\python.exe phase4_verify_accuracy.py
```

**Report Structure**:
```
SUMMARY
--------------------------------------------------------------------------------
Total Files Verified: 4
Perfect Match (>85%): 0
Good Match (75-85%): 2
Warning (65-75%): 2
Failed (<65%): 0

FILE: 20240628_9c1_ROA_a.pdf
================================================================================
PDF File: 20240628_9c1_ROA_a.pdf
Cleaned File: 20240628_9c1_ROA_v21.txt
PDF Pages: 5
Cleaned Page Markers: 5
Page Count Match: YES
Overall Similarity: 69.9%
Issues Found: 7

PAGE-BY-PAGE ANALYSIS
--------------------------------------------------------------------------------
Page   Status     Similarity   PDF Words    Cleaned Words
--------------------------------------------------------------------------------
1      OK         75.3%        242          219
2      WARNING    68.7%        289          260
...

ISSUES DETECTED
--------------------------------------------------------------------------------
  - Page 2: Low similarity (68.7%)
  - Page 3: 6 missing words (non-artifacts)

Page 2 - Word Differences:
  Missing from cleaned (6 total): circuit, ninth, defendant, michigan
  Added in cleaned (1 total): reassignment

OVERALL ASSESSMENT
================================================================================
[WARNING] 2 file(s) have similarity between 65-75%
Action Recommended: Review warnings for legal accuracy
```

**Example Console Output**:
```
Verifying: 20240628_9c1_ROA_a.pdf vs 20240628_9c1_ROA_v21.txt
  Overall similarity: 69.9%
  Issues found: 7

[DONE] Report saved: VERIFICATION_REPORT_20251104_010845.txt

Verification Summary:
  Perfect (>85%): 0/4
  Good (75-85%): 2/4
```

---

## COMPLETE WORKFLOW - RUN ALL 4 PHASES

### Sequential Execution (Recommended)

```powershell
cd E:\00_dev_1\y_apps\x3_doc-processing\doc-process-v21

# Phase 1: Create clean PDF-A files
E:\.venv\Scripts\python.exe phase1_pdfa_ocr.py

# Phase 2: Extract text with page markers
E:\.venv\Scripts\python.exe phase2_convert_to_text.py

# Phase 3: Clean with Gemini AI
E:\.venv\Scripts\python.exe phase3_clean_with_gemini.py

# Phase 4: Verify accuracy
E:\.venv\Scripts\python.exe phase4_verify_accuracy.py
```

### Expected Results

After running all 4 phases on 4 ROA PDFs:

```
02_ROA/
├── 20240628_9c1_ROA_o.pdf        # Original
├── 20240716_9c1_ROA_o.pdf
├── 20240912_9c1_ROA_o.pdf
├── 20251007_9c1_ROA_o.pdf
├── x0_pdf-a/
│   ├── 20240628_9c1_ROA_a.pdf    # 5 pages, 0 bookmarks, clean
│   ├── 20240716_9c1_ROA_a.pdf    # 3 pages, 0 bookmarks, clean
│   ├── 20240912_9c1_ROA_a.pdf    # 5 pages, 0 bookmarks, clean
│   └── 20251007_9c1_ROA_a.pdf    # 8 pages, 0 bookmarks, clean
├── x1_converted/
│   ├── 20240628_9c1_ROA_c.txt    # 9,694 chars, 5 page markers
│   ├── 20240716_9c1_ROA_c.txt    # 9,448 chars, 3 page markers
│   ├── 20240912_9c1_ROA_c.txt    # 10,644 chars, 5 page markers
│   └── 20251007_9c1_ROA_c.txt    # 17,071 chars, 8 page markers
├── x2_cleaned/
│   ├── 20240628_9c1_ROA_v21.txt  # With template, 69.9% similarity
│   ├── 20240716_9c1_ROA_v21.txt  # With template, 68.9% similarity
│   ├── 20240912_9c1_ROA_v21.txt  # With template, 75.1% similarity
│   └── 20251007_9c1_ROA_v21.txt  # With template, 79.5% similarity
└── x3_verified/
    └── VERIFICATION_REPORT_20251104_010845.txt  # Detailed metrics
```

---

## FILE SUFFIX CONVENTIONS

- `_o`: Original PDF (input)
- `_a`: PDF-A (clean, searchable, court-ready)
- `_c`: Converted (raw extracted text)
- `_v21`: Version 21 (Gemini-cleaned text with template)

---

## CONFIGURATION

### Update Root Directory

Edit each phase script's `ROOT_DIR` variable:

```python
ROOT_DIR = Path("E:/01_prjct_active/02_legal_system_v1.2/x_docs/03_kazoo-county/06_9c1-23-0406-ck/02_ROA")
```

### Update Secrets Path

Scripts load from:
```python
secrets_file = Path('E:/00_dev_1/01_secrets/secrets_global')
```

Required secrets:
- `GEMINI_API_KEY` (for Phase 3)

---

## TROUBLESHOOTING

### Phase 1 Issues
- **Missing pages**: Check original PDF is not corrupted
- **Large file size**: Compression settings are aggressive (garbage=4, deflate=True)
- **Bookmarks remain**: Script removes all TOC entries via `set_toc([])`

### Phase 2 Issues
- **Missing page markers**: Verify PDF has readable text layer
- **Low character count**: May indicate PDF is image-only (needs OCR first)

### Phase 3 Issues
- **API errors**: Check GEMINI_API_KEY in secrets_global
- **Timeout**: Large files may take 30+ seconds per file
- **Missing template**: Verify script applies header/footer correctly

### Phase 4 Issues
- **Low similarity (65-75%)**: Normal due to Gemini reformatting
- **High "missing words"**: Filter artifacts first (URLs, dates, single letters)
- **Page count mismatch**: Check page markers in Phase 2 output

---

## NEXT STEPS AFTER PROCESSING

### For Neo4j Import
1. Use `*_v21.txt` files from x2_cleaned/
2. Page markers enable exact citations: "ROA Page 3, Line 15"
3. Template header provides metadata for graph nodes

### For Legal Filing
1. Use `*_a.pdf` files from x0_pdf-a/
2. Files are clean, compressed, searchable
3. All metadata/bookmarks removed per court requirements

### For Manual Review
1. Check verification report in x3_verified/
2. Review files with <75% similarity
3. Compare "missing words" sections for legal terms

---

## VERSION HISTORY

**v21** (November 4, 2025)
- Modular 4-phase scripts (phase1-4)
- Gemini 2.5 Pro for cleaning
- Enhanced verification with artifact filtering
- Updated documentation with complete examples

**v14-v20** (October 2025)
- Legacy monolithic script
- Combined all phases in single file
- ocrmypdf + Ghostscript approach
  Perfect (>85%): 0/4
  Good (75-85%): 2/4
```

---

## COMPLETE WORKFLOW - RUN ALL 4 PHASES

**Tools**:
- Gemini 2.5 Pro AI
- API Key: AIzaSyAYQOr1mRNKhcm6UCa1yEkMKp7r5a8ttZw (embedded)

**Process**:
1. **FIRST**: Archive ALL existing *_g*.txt files to _old/
2. For each _c.txt:
   - Read raw text
   - Send to Gemini with instructions:
     - Fix OCR errors
     - Preserve exact legal wording
     - Maintain exact paragraphs
     - Keep page markers
     - Lines under 65 characters
     - Preserve all citations
   - Get cleaned text from Gemini
   - Apply required template (header + text + footer)
3. Save as _g1.txt

**Required Template** (MUST be exact):
```
§§ DOCUMENT INFORMATION §§

DOCUMENT NUMBER: TBD
DOCUMENT NAME: 20230803_9c1_FIC_Accepts-Reedy-Insured
ORIGINAL PDF NAME: 20230803_9c1_FIC_Accepts-Reedy-Insured_a.pdf
PDF DIRECTORY: E:\...\x0_pdf-a\20230803_9c1_FIC_Accepts-Reedy-Insured_a.pdf
TOTAL PAGES: 12

=====================================================================
BEGINNING OF PROCESSED DOCUMENT
=====================================================================

[Gemini cleaned text with exact wording and paragraphs]

=====================================================================
END OF PROCESSED DOCUMENT
=====================================================================
```

**Output**: `x2_cleaned/{filename}_g1.txt`
- Clean court-ready text
- OCR errors fixed
- Template applied
- Exact wording preserved
- Exact paragraphs maintained
- Page markers intact
- Ready for Neo4j

---

## PHASE 4 DETAILS: Verify

### What This Phase Does
Verifies cleaned text matches original PDF and creates report.

**Input**:
- Cleaned: x2_cleaned/*_g1.txt
- Original: x0_pdf-a/*_a.pdf

**Tools**:
- PyMuPDF (extract PDF for comparison)

**Process**:
1. For each _g1.txt:
   - Open corresponding _a.pdf
   - Extract text from PDF
   - Count PDF pages
   - Count page markers in _g1.txt
   - Check: Marker count = PDF page count
   - Check: Text length reasonable (>80% of PDF)
   - Report deviations

2. Create final report:
   - All phases summary
   - Success/failure counts
   - Deviation list
   - Save to ROOT_DIR

**Checks Performed**:
- Page marker count matches PDF pages
- Text length within acceptable range
- Template present and correct
- No major content loss

**Output**: `PROCESSING_REPORT_v14_{timestamp}.txt` in ROOT_DIR

**Report Contains**:
- Pre-flight check results
- Files processed each phase
- Success/failure counts
- Any deviations found
- Final status (COMPLETE/WARNINGS/FAILED)

---

## DETAILED TOOL ACTIONS - What Happens Exactly

### Phase 1: OCR - Specific Actions

**Tool 1: ocrmypdf (Primary OCR)**

**What it does**:
- Rasterizes each PDF page at 600 DPI
- Performs optical character recognition on images
- Creates invisible searchable text layer over image
- Embeds text in PDF/A format

**Exact command**:
```bash
ocrmypdf --redo-ocr --output-type pdfa --oversample 600 input.pdf output_a.pdf
```

**Parameters explained**:
- `--redo-ocr`: Forces OCR even if PDF already has text (ensures quality)
- `--output-type pdfa`: Creates PDF/A-2b archival format (court-acceptable)
- `--oversample 600`: Renders pages at 600 DPI before OCR (high quality)
- Input: Original PDF from ROOT_DIR
- Output: Searchable PDF in x0_pdf-a/

**What happens inside ocrmypdf**:
1. Opens PDF and extracts each page
2. Converts each page to 600 DPI image
3. Runs Tesseract OCR engine on each image
4. Creates invisible text layer positioned over image
5. Combines all pages into PDF/A format
6. Validates PDF/A compliance
7. Saves to output path

---

**Tool 2: Ghostscript (Fallback)**

**When used**: If ocrmypdf fails (corrupted PDF, non-standard encoding)

**What it does**:
- Rasterizes entire PDF to clean bitmap images
- Removes any corruption or encoding issues
- Creates fresh PDF from images

**Exact command**:
```bash
gswin64c -sDEVICE=pdfimage32 -o temp.pdf input.pdf
```

**Parameters explained**:
- `gswin64c`: Windows Ghostscript executable
- `-sDEVICE=pdfimage32`: Output device = PDF with 32-bit images
- `-o temp.pdf`: Output file
- `input.pdf`: Problematic source PDF

**What happens**:
1. Opens input PDF
2. Rasterizes each page to 32-bit color image
3. Embeds images in new PDF structure
4. Creates clean temp.pdf
5. Then ocrmypdf processes temp.pdf (clean version)

---

**Tool 3: PyMuPDF (fitz) - PDF Cleanup**

**What it does**:
- Removes navigation bookmarks/table of contents
- Deletes annotations (highlights, comments, stamps)
- Cleans metadata
- Prepares court-ready PDF

**Exact code**:
```python
doc = fitz.open(output_path)  # Open OCR'd PDF

# Remove bookmarks
doc.set_toc([])  # Empties table of contents

# Remove annotations
for page in doc:
    # Skip pages with "exhibit" (preserve exhibit markings)
    if "exhibit" in page.get_text().lower():
        continue
    # Delete all annotations on this page
    for annot in page.annots():
        page.delete_annot(annot)

# Save to bytes buffer
buffer = doc.tobytes()
doc.close()

# Overwrite original file with cleaned version
with open(output_path, "wb") as f:
    f.write(buffer)
```

**What happens**:
1. Opens the OCR'd PDF
2. Clears all bookmarks (navigation entries)
3. Iterates through each page
4. Checks if page contains "exhibit" text
5. If not exhibit page: deletes all annotations (highlights, comments, stamps, etc.)
6. If exhibit page: skips (preserves exhibit markings)
7. Saves cleaned PDF in memory
8. Overwrites original with cleaned version

---

### Phase 2: Convert - Specific Actions

**Tool: PyMuPDF (fitz) - Text Extraction**

**What it does**:
- Opens searchable PDF created in Phase 1
- Extracts text layer page-by-page
- Adds page markers for citation tracking
- Saves as plain text file

**Exact code**:
```python
doc = fitz.open(pdf_file)  # Open _a.pdf from x0_pdf-a/
all_text = []

# Process each page
for page_num, page in enumerate(doc):
    # Get text from this page's searchable layer
    text = page.get_text()
    
    # Add page marker before text
    page_marker = f"\n\n[BEGIN PDF Page {page_num + 1}]\n\n"
    
    # Append to collection
    all_text.append(page_marker + text)

# Combine all pages
final_text = "".join(all_text)

# Write to file
output_file.write_text(final_text, encoding='utf-8')
```

**What happens step-by-step**:
1. Opens enhanced PDF from x0_pdf-a/
2. For page 1:
   - Calls `page.get_text()` to extract searchable text layer
   - Gets all text from page 1
   - Prepends `[BEGIN PDF Page 1]` marker
   - Adds to collection
3. For page 2:
   - Extracts text from page 2
   - Prepends `[BEGIN PDF Page 2]` marker
   - Adds to collection
4. Repeats for all pages
5. Joins all text together
6. Saves as UTF-8 text file with _c.txt suffix
7. Result: Text file with exact page markers matching PDF pages

**Output format**:
```
[BEGIN PDF Page 1]

STATE OF MICHIGAN
CIRCUIT COURT FOR THE COUNTY OF KALAMAZOO

Plaintiff: Fremont Insurance Company
...

[BEGIN PDF Page 2]

Defendant Reedy & Reedy, LLC, upon being served...
```

**Why this matters**:
- Page markers enable exact PDF citations
- [BEGIN PDF Page 5] in text = Page 5 in PDF
- Neo4j can store "found on Page 5" and it will be exact
- Court filings can reference specific pages accurately

---

### Phase 3: Clean - Specific Actions

**Part A: Archive Old Files**

**What happens**:
```python
# Get all existing cleaned files
old_files = list(x2_cleaned_dir.glob('*_g*.txt'))
# Returns: ['file1_g1.txt', 'file2_g1.txt', 'file1_g2.txt', ...]

# Move each to _old with timestamp
for old_file in old_files:
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')  # e.g., "20251031_143022"
    new_name = f"{old_file.stem}_{timestamp}.txt"
    archive_path = x2_cleaned_dir / '_old' / new_name
    
    # Move file
    shutil.move(str(old_file), str(archive_path))
    # Result: file1_g1.txt → _old/file1_g1_20251031_143022.txt
```

**Why this happens**:
- Prevents mixing old and new versions
- Preserves history (can compare versions)
- Ensures clean state before creating new files

---

**Part B: Gemini AI Processing**

**Tool: Gemini 2.5 Pro API**

**Configuration**:
```python
import google.generativeai as genai

# Configure API
genai.configure(api_key="AIzaSyAYQOr1mRNKhcm6UCa1yEkMKp7r5a8ttZw")

# Create model instance
model = genai.GenerativeModel("gemini-2.5-pro")

# Set generation parameters
config = genai.types.GenerationConfig(
    temperature=0.1,           # Low = consistent, predictable output
    max_output_tokens=65536    # Maximum length (full legal documents)
)
```

**Exact prompt sent to Gemini**:
```
You are correcting OCR output for a legal document. Your task is to:
1. Fix OCR errors while preserving exact legal wording
2. Maintain exact paragraph structure
3. Keep page markers as [BEGIN PDF Page N]
4. Ensure lines under 65 characters for readability
5. Preserve all legal citations exactly
6. Create court-ready formatting
Return only the corrected text with no commentary.

[BEGIN PDF Page 1]

STATE 0F MICHIGAN  [OCR error: 0 instead of O]
CIRCUIT C0URT F0R THE C0UNTY 0F KALAMA100  [Multiple OCR errors]

Plaintiff: Fremant Insurance...  [OCR error: Fremant vs Fremont]
```

**What Gemini does**:
1. Reads entire raw text with OCR errors
2. Identifies OCR errors (0 vs O, common mistakes)
3. Fixes errors: "0F" → "OF", "C0URT" → "COURT", "Fremant" → "Fremont"
4. Preserves exact legal wording (party names, case numbers)
5. Keeps paragraph breaks exactly as they appear
6. Maintains page markers: [BEGIN PDF Page N]
7. Formats lines to be under 65 characters
8. Returns only corrected text (no explanations)

**Gemini output example**:
```
[BEGIN PDF Page 1]

STATE OF MICHIGAN
CIRCUIT COURT FOR THE COUNTY OF KALAMAZOO

Plaintiff: Fremont Insurance Company...
```

---

**Part C: Template Application**

**What happens**:
```python
# Get PDF info
source_pdf = pdf_source_dir / f"{base_name}_a.pdf"
page_count = len(fitz.open(source_pdf))  # Count pages in PDF

# Create header
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

# Create footer
footer = """
=====================================================================
END OF PROCESSED DOCUMENT
====================================================================="""

# Assemble final document
final_text = header + gemini_cleaned_text + footer

# Save to file
dest_file.write_text(final_text, encoding='utf-8')
```

**What this creates**:
```
§§ DOCUMENT INFORMATION §§

DOCUMENT NUMBER: TBD
DOCUMENT NAME: 20230803_9c1_FIC_Accepts-Reedy-Insured
ORIGINAL PDF NAME: 20230803_9c1_FIC_Accepts-Reedy-Insured_a.pdf
PDF DIRECTORY: E:\DevWorkspace\...\x0_pdf-a\20230803_9c1_FIC_Accepts-Reedy-Insured_a.pdf
TOTAL PAGES: 12

=====================================================================
BEGINNING OF PROCESSED DOCUMENT
=====================================================================

[BEGIN PDF Page 1]

STATE OF MICHIGAN
CIRCUIT COURT FOR THE COUNTY OF KALAMAZOO

[Exact cleaned text from Gemini continues...]

=====================================================================
END OF PROCESSED DOCUMENT
=====================================================================
```

**Fields populated**:
- DOCUMENT NAME: From filename stem
- ORIGINAL PDF NAME: Adds _a.pdf suffix
- PDF DIRECTORY: Uses Path.resolve() for full absolute path
- TOTAL PAGES: Uses fitz to count PDF pages

---

### Phase 4: Verify - Specific Actions

**Tool: PyMuPDF (fitz) - PDF Comparison**

**What happens**:
```python
# Step 1: Load cleaned text
cleaned_file = Path("x2_cleaned/document_g1.txt")
cleaned_text = cleaned_file.read_text(encoding='utf-8')

# Step 2: Load original PDF
pdf_file = Path("x0_pdf-a/document_a.pdf")
pdf_doc = fitz.open(pdf_file)

# Step 3: Extract text from PDF
pdf_text = ""
for page in pdf_doc:
    page_text = page.get_text()  # Get searchable text layer
    pdf_text += page_text

# Step 4: Count PDF pages
pdf_page_count = len(pdf_doc)
pdf_doc.close()

# Step 5: Extract cleaned body (skip template header/footer)
body_start = cleaned_text.find("BEGINNING OF PROCESSED DOCUMENT")
body_end = cleaned_text.find("END OF PROCESSED DOCUMENT")
cleaned_body = cleaned_text[body_start:body_end]

# Step 6: Count page markers in cleaned text
page_marker_count = cleaned_body.count("[BEGIN PDF Page ")

# Step 7: Compare
if page_marker_count != pdf_page_count:
    deviation = f"Page mismatch: PDF={pdf_page_count}, markers={page_marker_count}"
    print(f"  [WARN] {deviation}")

# Step 8: Check text length
pdf_length = len(pdf_text)
cleaned_length = len(cleaned_body)
if cleaned_length < (pdf_length * 0.8):
    deviation = f"Text too short: {cleaned_length} vs {pdf_length}"
    print(f"  [WARN] {deviation}")
else:
    print(f"  [OK] Verified: {pdf_page_count} pages, {cleaned_length:,} chars")
```

**Verification checks performed**:

**Check 1: Page Count**
- Counts pages in PDF: `len(pdf_doc)` = 12
- Counts markers in text: `count("[BEGIN PDF Page ")` = 12
- Match? Yes = OK, No = WARN

**Check 2: Content Length**
- PDF text length: 50,000 characters
- Cleaned text length: 48,500 characters
- Ratio: 48,500 / 50,000 = 97% (within 80% threshold = OK)
- If ratio < 80%: WARN (possible content loss)

**Check 3: Template Present**
- Searches for "BEGINNING OF PROCESSED DOCUMENT"
- Searches for "END OF PROCESSED DOCUMENT"
- Both found? Yes = OK, No = WARN

**Report generated**:
```python
report_file = ROOT_DIR / f"PROCESSING_REPORT_v14_{timestamp}.txt"

# Write report with:
report_content = f"""
=== DOCUMENT PROCESSING REPORT v14 ===

Processing Date: {datetime.now()}
Case Directory: {ROOT_DIR}

PHASE 1: OCR
  Files Processed: 5
  Success: 5
  Failed: 0

PHASE 2: CONVERT
  Files Processed: 5
  Success: 5
  Failed: 0

PHASE 3: CLEAN
  Old Files Archived: 3
  Files Processed: 5
  Success: 5
  Failed: 0

PHASE 4: VERIFY
  Files Verified: 5
  Perfect Matches: 4
  Deviations Found: 1
  Issues:
    - document_g1.txt: Page mismatch: PDF=12, markers=11

=== SUMMARY ===
Total Files: 5
Successfully Processed: 5
Deviations Requiring Review: 1

Status: COMPLETE WITH WARNINGS
"""

report_file.write_text(report_content)
```

---

## COMPLETE TOOL CHAIN - What Executes

### Phase 1: OCR - Tools Chain

**Primary Flow**:
```
1. Python subprocess → 
2. ocrmypdf executable →
3. Tesseract OCR engine →
4. Image processing (600 DPI rasterization) →
5. Text recognition (character by character) →
6. Text positioning (coordinates on page) →
7. PDF/A assembly →
8. Output file: _a.pdf
```

**Fallback Flow** (if primary fails):
```
1. Python subprocess →
2. Ghostscript executable (gswin64c) →
3. PDF rasterization (convert to images) →
4. Clean PDF creation →
5. Then: Same as primary flow with temp PDF
```

**Cleanup Flow**:
```
1. Python fitz.open() → Opens PDF in memory
2. doc.set_toc([]) → Removes bookmark tree structure
3. page.annots() → Gets all annotations (list)
4. page.delete_annot() → Deletes each annotation object
5. doc.tobytes() → Serializes to bytes
6. file.write() → Overwrites original with cleaned version
```

---

### Phase 2: Convert - Tools Chain

**Execution Flow**:
```
1. Python fitz.open(pdf_path) →
   - Loads PDF into memory
   - Parses PDF structure
   - Identifies pages (12 pages)

2. For each page (enumerate loop):
   - page.get_text() → Extracts searchable text layer
   - Returns: String with all text from page
   - Includes: Spacing, line breaks as rendered

3. Text processing:
   - page_num + 1 → Converts 0-based to 1-based (page 0 → Page 1)
   - f-string formatting → Creates "[BEGIN PDF Page 1]"
   - String concatenation → Adds marker + text

4. Join all pages:
   - "".join(all_text) → Combines list into single string
   - Result: 50,000+ character string with 12 page markers

5. Write to file:
   - output_file.write_text() → UTF-8 encoding
   - Creates: filename_c.txt in x1_converted/
```

**Text layer extraction specifics**:
- `get_text()` reads embedded searchable text (from OCR)
- Preserves spaces, line breaks, paragraph structure
- Does NOT re-OCR (uses existing text layer)
- Maintains exact character positions as OCR'd
- Includes all OCR artifacts (errors still present at this stage)

---

### Phase 3: Clean - Tools Chain

**Archive Flow**:
```
1. Path.glob('*_g*.txt') →
   - Searches x2_cleaned/ directory
   - Finds: ['file1_g1.txt', 'file2_g1.txt', 'file1_g2.txt']
   - Returns: List of Path objects

2. For each old file:
   - datetime.now() → Gets current timestamp
   - strftime('%Y%m%d_%H%M%S') → Formats as "20251031_143022"
   - Creates new filename: "file1_g1_20251031_143022.txt"
   - shutil.move() → Moves file to _old/ subdirectory
```

**Gemini API Flow**:
```
1. genai.configure(api_key=GEMINI_API_KEY) →
   - Authenticates with Google AI
   - Establishes API session

2. genai.GenerativeModel("gemini-2.5-pro") →
   - Loads Gemini 2.5 Pro model
   - Model capabilities: 1M token context, code generation, reasoning

3. model.generate_content(prompt + raw_text, config) →
   - Sends: Prompt (instructions) + Raw text (50,000 chars)
   - Temperature=0.1: Consistent output (low randomness)
   - Max tokens=65536: Can output full legal documents
   - Processing time: 30-60 seconds per document

4. Gemini processes:
   - Reads entire document
   - Identifies patterns: "0" vs "O", "C0URT" vs "COURT"
   - Corrects errors based on context
   - Preserves legal terminology (knows "Fremont" not "Fremant")
   - Maintains paragraph breaks (recognizes document structure)
   - Keeps page markers exactly as is
   - Formats lines to 65 chars (improves readability)

5. Returns: response.text
   - Clean text string
   - All OCR errors corrected
   - Formatting improved
   - Legal accuracy preserved
```

**Template Assembly Flow**:
```
1. fitz.open(source_pdf) → Opens PDF to count pages
2. len(doc) → Returns page count (e.g., 12)
3. source_pdf.resolve() → Gets absolute path
4. f-string substitution → Fills template fields:
   - {base_name} → "20230803_9c1_FIC_Accepts-Reedy-Insured"
   - {page_count} → "12"
   - {source_pdf.resolve()} → "E:\DevWorkspace\...\file_a.pdf"

5. String concatenation:
   header + gemini_text + footer
   
6. dest_file.write_text(final_text) →
   - Writes complete document with template
   - UTF-8 encoding
   - Saves as _g1.txt
```

---

### Phase 4: Verify - Tools Chain

**Comparison Flow**:
```
1. For each _g1.txt in x2_cleaned/:
   
2. Load cleaned file:
   - Path.read_text() → Reads entire file
   - encoding='utf-8' → Handles special characters

3. Find corresponding PDF:
   - Construct path: x0_pdf-a/{base_name}_a.pdf
   - Check exists: pdf_file.exists()

4. Extract from PDF:
   - fitz.open(pdf_file) → Opens PDF
   - for page in doc: → Iterate pages
   - page.get_text() → Extract each page's text
   - Concatenate all pages into pdf_text string

5. Extract cleaned body:
   - Find start: text.find("BEGINNING OF PROCESSED DOCUMENT")
   - Find end: text.find("END OF PROCESSED DOCUMENT")
   - Slice: cleaned_body = text[start:end]
   - Result: Just document content, no template header/footer

6. Count markers:
   - cleaned_body.count("[BEGIN PDF Page ") → e.g., 12
   - len(pdf_doc) → e.g., 12
   - Compare: 12 == 12? Yes = OK

7. Check length:
   - len(cleaned_body) → e.g., 48,500
   - len(pdf_text) → e.g., 50,000
   - Ratio: 48,500 / 50,000 = 0.97 (97%)
   - >= 0.80? Yes = OK

8. Record results:
   - If all checks pass: status = 'OK'
   - If any check fails: status = 'DEVIATIONS', log issues
```

**Report Generation Flow**:
```
1. Collect all results from report_data dictionary
2. Format as text report
3. Include:
   - Timestamp
   - Each phase results
   - File-by-file status
   - Deviation details
   - Summary counts
4. Write to: ROOT_DIR/PROCESSING_REPORT_v14_{timestamp}.txt
```

---

## TOOL DEPENDENCIES

### What Must Be Installed

**Python Packages** (in venv):
```
pip install PyMuPDF>=1.24.0
pip install google-generativeai>=0.3.0
pip install google-cloud-vision>=3.0.0  # Optional
```

**System Tools**:
- **ocrmypdf**: `pip install ocrmypdf` or `brew install ocrmypdf`
- **Ghostscript**: Download from https://www.ghostscript.com/releases/
  - Windows: gswin64c.exe in PATH or C:\Program Files\gs\
  - Includes ps2pdf, pdf2ps utilities

**API Access**:
- Gemini API: Requires Google AI Studio account
- Vision API: Requires Google Cloud project (optional)

---

## EXECUTION SEQUENCE

### When You Run: `python doc-process-v14.py --phase all`

```
1. Script starts → Imports all modules
2. Reads configuration → Loads GEMINI_API_KEY, ROOT_DIR, etc.
3. Parses arguments → --phase all = run all phases
4. Creates report_data dictionary → For tracking results

5. Runs preflight_checks():
   - Tests Gemini API key != "YOUR_KEY_HERE"
   - Calls shutil.which('ocrmypdf') → Checks if installed
   - Calls shutil.which('gswin64c') → Checks if installed
   - Imports fitz → Tests PyMuPDF available
   - Tests ROOT_DIR.exists() → Verifies directory
   - Prints [OK] or [FAIL] for each
   - Returns True/False
   - If False: sys.exit(1) → Stops execution

6. Runs setup_directories():
   - ROOT_DIR / 'x0_pdf-a'.mkdir(exist_ok=True)
   - ROOT_DIR / 'x0_pdf-a' / '_old'.mkdir(exist_ok=True)
   - Repeat for x1_converted, x2_cleaned
   - Prints confirmation

7. Runs enhance_pdfs() [Phase 1: OCR]:
   - Scans ROOT_DIR for *.pdf files
   - For each: subprocess.run(['ocrmypdf', ...])
   - Waits for completion
   - Checks return code (0 = success)
   - If success: Opens with fitz, cleans, saves
   - Records result in report_data

8. Runs convert_to_text() [Phase 2: Convert]:
   - Scans x0_pdf-a/ for *_a.pdf
   - For each: fitz.open() → page.get_text() loop
   - Adds page markers
   - Writes to x1_converted/
   - Records result

9. Runs clean_with_gemini() [Phase 3: Clean]:
   - Archives old files first
   - Scans x1_converted/ for *_c.txt
   - For each: genai.GenerativeModel.generate_content()
   - Waits for Gemini response (30-60 sec per file)
   - Applies template
   - Writes to x2_cleaned/
   - Records result

10. Runs verify_accuracy() [Phase 4: Verify]:
    - Scans x2_cleaned/ for *_g1.txt
    - For each: Compares to PDF
    - Logs deviations
    - Records results

11. Runs generate_report():
    - Formats report_data as text
    - Writes to ROOT_DIR/PROCESSING_REPORT_v14_{timestamp}.txt
    - Prints completion message

12. Script exits
```

---

**Complete technical specification of all tools and actions for doc-process-v14.**

Last Updated: October 31, 2025
Version: 14
Detail Level: Complete - all tools and actions specified


### When to Create v15, v16, etc.
Create new version when changing ANY processing logic, templates, or tools.

### CRITICAL FOR AI AGENTS: Instructions First, Code Second

**MANDATORY ORDER**:

### Step 1: Stop All Services
```powershell
# Stop MCP servers
Get-Process | Where-Object { $_.ProcessName -like '*mcp-neo4j*' } | Stop-Process

# Stop document processing
Get-Process python | Where-Object { $_.CommandLine -like '*doc-process*' } | Stop-Process
```

### Step 2: Create New Version Directory
```powershell
New-Item -ItemType Directory -Path "y_config\x3_doc-processing\doc-process-v15"
```

### Step 3: Update INSTRUCTIONS First (.md file)

**Create**: `doc-process-v15/doc-process-v15.md`

1. Copy this file (doc-process-v14r.md) to doc-process-v15.md
2. Update version: v14r → v15 throughout
3. Update date
4. Document changes in WHAT CHANGED section
5. Update suffix rules: `_v14r.txt` → `_v15.txt`
6. Update output examples to show new suffix

### Step 4: SUMMARIZE Changes to User

**AI Agent MUST provide summary before creating script**:

```
"Updated doc-process-v15 instructions with following changes:

PHASE 1 (OCR): [No changes / Describe changes]
PHASE 2 (Convert): [No changes / Describe changes]
PHASE 3 (Clean): [Describe changes]
PHASE 4 (Verify): [Describe changes]

Ready to create script implementing these changes?"
```

**WAIT for user approval**

### Step 5: Create Script (.py file) - AFTER User Approves

**Create**: `doc-process-v15/doc-process-v15.py`

1. Copy doc-process-v14r.py to doc-process-v15.py
2. Update version in script: v14r → v15
3. Update output suffix: `_v14r.txt` → `_v15.txt`
4. Implement other changes described in instructions

**CRITICAL**: 
- Instructions created FIRST
- Script created SECOND (after approval)
- Directory name = .md name = .py name = output suffix

### Step 6: TEST on ONE File FIRST

**CRITICAL - DO NOT SKIP**:
```powershell
# Test on single file
python doc-process-v15.py --phase clean --file "path/to/one/file_a.txt"

# Check output quality:
# - Compare line count to v13 baseline (~same)
# - Check table formatting (columns aligned)
# - Check numbered lists (numbers with text)
# - Verify footer has 2 blank lines
```

**If quality good**: Proceed to Step 7
**If quality degraded**: Revert, modify prompt, test again

### Step 7: Archive Old Version (After Testing)
```powershell
Move-Item "doc-process-v14r" -Destination "z_old-versions\doc-process-v14r"
```

### Step 8: Update README and CHANGES_LOG
In `x3_doc-processing/README.md`:
- Change "Current Version: v14r" → "v15"
- Change all "doc-process-v14r" → "doc-process-v15"

In `CHANGES_LOG.md`:
- Update current version entry with test results

---

## AI AGENT VERSIONING WORKFLOW

**User**: "Update the cleaning phase to include case number"

**AI Agent Response**:
```
1. Stopping services...
2. Created doc-process-v15/ directory
3. Updated doc-process-v15.md with following changes:

PHASE 3 (Clean):
  - Added case number extraction from filename
  - Updated template to include CASE NUMBER field
  - Modified Gemini prompt to preserve case numbers

All other phases unchanged.

Ready to create doc-process-v15.py implementing this change?
```

**Wait for**: User says "yes" or "approved"

**Then**: Create doc-process-v15.py with the changes

**NEVER**: Create script before getting approval of instruction changes

---

## RUNNING THE SCRIPT

### Step 1: Verify Script Version
```powershell
cd E:\DevWorkspace\01_prjct_active\02_legal_system_v1.2
.\y_config\activate.ps1

# Find latest version
Get-ChildItem y_config\x3_doc-processing -Directory | Where-Object { $_.Name -match "^doc-process-v\d+" } | Sort-Object Name -Descending | Select-Object -First 1
```

**Should show**: doc-process-v14 (or higher if v15+ exists)

### Step 2: Run Script

**Interactive Mode** (Recommended):
```powershell
python y_config\x3_doc-processing\doc-process-v14\doc-process-v14.py
```

Script will ask:
1. Which phase? (ocr / convert / clean / verify / all)
2. Directory or file? (d / f)
3. If file: Enter file path

**Command-Line Mode**:
```powershell
# All phases, all files
python doc-process-v14.py --phase all

# Specific phases
python doc-process-v14.py --phase ocr convert
python doc-process-v14.py --phase clean
python doc-process-v14.py --phase verify

# Single file
python doc-process-v14.py --file "path/to/document.pdf"

# Combine
python doc-process-v14.py --phase clean --file "document.pdf"
```

### Step 3: Review Results
- Check console output for [OK] or [FAIL]
- Review final report in ROOT_DIR
- Check x2_cleaned/ for _g1.txt files
- Address any deviations reported

---

## FUNCTIONALITY

### Run All Phases on Directory
```powershell
python doc-process-v14.py --phase all
```
Processes ALL PDFs in ROOT_DIR through all 4 phases.

### Run Single Phase on Directory
```powershell
python doc-process-v14.py --phase ocr
python doc-process-v14.py --phase convert
python doc-process-v14.py --phase clean
python doc-process-v14.py --phase verify
```

### Run on Single File
```powershell
python doc-process-v14.py --file "20230803_9c1_FIC_Accepts-Reedy-Insured_o.pdf"
```

### Combine Phase + File
```powershell
python doc-process-v14.py --phase clean verify --file "document.pdf"
```

---

## FILE NAMING FLOW

### Complete Chain
```
ROOT/:     20230803_9c1_FIC_Accepts-Reedy-Insured_o.pdf  (original)
              ↓ Phase 1: OCR
x0_pdf-a/: 20230803_9c1_FIC_Accepts-Reedy-Insured_a.pdf  (searchable PDF/A)
              ↓ Phase 2: Convert
x1_converted/: 20230803_9c1_FIC_Accepts-Reedy-Insured_a.txt  (raw text)
              ↓ Phase 3: Clean
x2_cleaned/: 20230803_9c1_FIC_Accepts-Reedy-Insured_v20.txt  (clean + template)
              ↓ Phase 4: Verify
ROOT/:     PROCESSING_REPORT_v20_{timestamp}.txt  (verification report)
```

### Suffix Meanings
- `_o.pdf` - Original PDF
- `_a.pdf` - OCR'd searchable PDF/A
- `_a.txt` - Converted raw text (x1_converted)
- `_v20.txt` - Cleaned with v20 (x2_cleaned)
- `_v21.txt` - Cleaned with v21 (if reprocessed with newer version)

---

## CREDENTIALS & TOOLS

### Embedded in Script (No External Searches)
```python
GEMINI_API_KEY = "AIzaSyAYQOr1mRNKhcm6UCa1yEkMKp7r5a8ttZw"
ROOT_DIR = "E:/DevWorkspace/01_prjct_active/02_legal_system_v1.2/x_docs/03_kazoo-county/06_9c1-23-0406-ck/09_Pleadings_plaintiff"
MODEL_NAME = "gemini-2.5-pro"
MAX_OUTPUT_TOKENS = 65536
```

### Required Tools (Checked at Start)
- ocrmypdf - Install: `pip install ocrmypdf`
- Ghostscript - Download from ghostscript.com
- PyMuPDF - Install: `pip install PyMuPDF`
- Gemini API - Key embedded in script

**Script verifies all tools before starting and stops if anything missing.**

---

## AI AGENT INSTRUCTIONS

### When User Requests Document Processing

**Step 1: Announce Version**
```
"Using Document Processing v14"
"Location: y_config/x3_doc-processing/doc-process-v14/"
```

**Step 2: Request Phase Selection**
```
"Which phase to run?"
"  1. ocr     - Create searchable PDFs"
"  2. convert - Extract text"
"  3. clean   - AI clean with Gemini"
"  4. verify  - Verify accuracy"
"  5. all     - Run all phases"
```

**Step 3: Request Scope**
```
"Process (d)irectory or single (f)ile?"
If file: "Enter file path:"
```

**Step 4: Run Processing**
- Use exact tools specified
- No deviations from process
- Follow template exactly
- Report all results

---

**Script is ready to run with all credentials embedded and all requirements implemented.**

Last Updated: October 31, 2025
Version: 14
Phases: 4 (OCR, Convert, Clean, Verify)
Status: Production Ready
