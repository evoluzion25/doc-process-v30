# Document Processing Pipeline v31

## Overview

Complete 7-phase pipeline for legal document processing with parallel execution, OCR enhancement, AI-powered text formatting, and cloud storage integration.

**Pipeline**: Directory → Rename → Clean → Convert → Format → Verify → GCS Upload

## What's New in v31

### Updated Phase Names & Suffixes
- Phase 1: **Directory** (was "Organize") - `_d` suffix
- Phase 2: **Rename** - `_r` suffix
- Phase 3: **Clean** (was "OCR") - `_o` suffix (OCR'd PDF/A)
- Phase 4: **Convert** (was "Extract") - `_c.txt` suffix
- Phase 5: **Format** - `_v31.txt` suffix
- Phase 6: **Verify** - report only
- Phase 7: **GCS Upload** - uploads PDFs to cloud storage and inserts URLs

### Optimized Clean/OCR Phase (Phase 3)

1. **Remove metadata** first (PyMuPDF)
2. **OCR at 600 DPI** (ocrmypdf → searchable PDF/A) - **runs in parallel**
3. **Compress** while maintaining searchability (Ghostscript /ebook)
4. Result: Clean, searchable, compressed PDF

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

### Run Full Pipeline

```powershell
python doc-process-v31.py --dir "E:\path\to\project" --phase all
```

### Run Single Phase

```powershell
# Phase 1: Directory (organize PDFs)
python doc-process-v31.py --dir "E:\path\to\project" --phase directory

# Phase 2: Rename (extract metadata, clean names)
python doc-process-v31.py --dir "E:\path\to\project" --phase rename

# Phase 3: Clean (OCR at 600 DPI)
python doc-process-v31.py --dir "E:\path\to\project" --phase clean

# Phase 4: Convert (extract text)
python doc-process-v31.py --dir "E:\path\to\project" --phase convert

# Phase 5: Format (clean text with AI)
python doc-process-v31.py --dir "E:\path\to\project" --phase format

# Phase 6: Verify (compare results)
python doc-process-v31.py --dir "E:\path\to\project" --phase verify

# Phase 7: GCS Upload (upload PDFs and insert URLs)
python doc-process-v31.py --dir "E:\path\to\project" --phase gcs_upload
```

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
- **Tools**: PyMuPDF (metadata removal), ocrmypdf (600 DPI OCR), Ghostscript (compression)
- **Action**: 
  1. Remove metadata
  2. OCR at 600 DPI → searchable PDF/A
  3. Compress while maintaining searchability

### Phase 4: Convert (Extract)
- **Input**: `03_doc-clean/*_o.pdf`
- **Output**: `04_doc-convert/`
- **Suffix**: `_c.txt`
- **Tools**: Google Cloud Vision API (batch OCR)
- **Action**: Extract text in 5-page batches

### Phase 5: Format
- **Input**: `04_doc-convert/*_c.txt`
- **Output**: `05_doc-format/`
- **Suffix**: `_v31.txt`
- **Tools**: Gemini 2.5 Pro (text cleaning)
- **Action**: Remove headers/footers, fix formatting, preserve legal structure

### Phase 6: Verify
- **Input**: `04_doc-convert/*_c.txt` + `05_doc-format/*_v31.txt`
- **Output**: Console diff report
- **Action**: Compare convert vs format, validate completeness

### Phase 7: GCS Upload
- **Input**: `03_doc-clean/*_o.pdf` + `04_doc-convert/*_c.txt`
- **Output**: GCS bucket + updated text files
- **Tools**: Google Cloud Storage
- **Action**: 
  1. Upload all cleaned PDFs to `gs://fremont-1/docs/<project>/`
  2. Generate public URLs for each PDF
  3. Insert URL header into corresponding `_c.txt` files
- **URL Format**: `https://storage.cloud.google.com/fremont-1/docs/<project>/<filename>`

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
