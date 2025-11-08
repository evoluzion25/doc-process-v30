# Phase 3 OCR Improvements - Diagnostic Report

## Issue Identified

**File**: `20230906_9c1_FIC_Amended_Petition_No_Coverage_r.pdf`  
**Problem**: Page 5 has NO extractable/selectable text after OCR processing

### Diagnostic Results
```
INPUT PDF (before OCR):
  - Pages with text: 5/6
  - Page 5: 0 chars (image-only page)
  
OUTPUT PDF (after OCR):  
  - Pages with text: 5/6
  - Page 5: STILL 0 chars (OCR failed on this page)
```

## Root Causes

### 1. `--force-ocr` Limitations
**Current command**:
```bash
ocrmypdf --force-ocr --output-type pdfa --oversample 600 input.pdf output.pdf
```

**Issue**: `--force-ocr` completely re-renders all pages, which can:
- Fail silently on complex image pages
- Skip pages with corrupt or unusual image encodings
- Not report per-page OCR failures

### 2. No Per-Page Validation
Current code has no mechanism to:
- Detect which specific pages failed OCR
- Retry failed pages with different settings
- Report per-page OCR success/failure

### 3. Compression May Strip Partial OCR
STEP 4 runs Ghostscript compression which can:
- Remove incomplete OCR text layers
- Strip metadata from partially-processed pages
- Further degrade pages that had marginal OCR

### 4. No Fallback Strategy
When `--force-ocr` fails, the code:
- Falls back to Ghostscript flatten + retry (which also fails)
- Eventually copies the file without OCR
- Does not attempt alternative OCR strategies

## Recommended Solutions

### Priority 1: Use `--redo-ocr` Instead of `--force-ocr` [CRITICAL]

**Change**:
```python
# OLD (Line 953)
cmd = [ocrmypdf_cmd, '--force-ocr', '--output-type', 'pdfa', 
       '--oversample', '600', ocr_input, str(output_path)]

# NEW
cmd = [ocrmypdf_cmd, '--redo-ocr', '--output-type', 'pdfa', 
       '--oversample', '600', '--optimize', '1', 
       '--jbig2-lossy', ocr_input, str(output_path)]
```

**Why**: `--redo-ocr` is smarter than `--force-ocr`:
- Preserves existing good text on pages 1-4, 6
- **Only OCRs pages that lack text (like page 5)**
- Less likely to degrade quality of already-good pages
- Faster processing (skips pages with text)

### Priority 2: Add Per-Page Validation & Retry [HIGH]

**New function** to add after `_process_clean_pdf`:

```python
def validate_and_fix_ocr(pdf_path, output_path):
    """Validate each page has text, re-OCR failed pages individually"""
    import PyPDF2
    
    # Check which pages lack text
    failed_pages = []
    with open(output_path, 'rb') as f:
        pdf = PyPDF2.PdfReader(f)
        for i in range(len(pdf.pages)):
            text = pdf.pages[i].extract_text().strip()
            if len(text) < 50:  # Page has insufficient text
                failed_pages.append(i + 1)  # 1-indexed
    
    if not failed_pages:
        return True, "All pages have text"
    
    print(f"  [RETRY] Pages {failed_pages} need re-OCR")
    
    # Strategy: Extract failed pages, OCR individually, merge back
    import fitz
    
    # For each failed page, try more aggressive OCR
    for page_num in failed_pages:
        try:
            # Extract single page to temp PDF
            doc = fitz.open(pdf_path)
            temp_single = Path(output_path.parent) / f"temp_page_{page_num}.pdf"
            single_doc = fitz.open()
            single_doc.insert_pdf(doc, from_page=page_num-1, to_page=page_num-1)
            single_doc.save(str(temp_single))
            single_doc.close()
            doc.close()
            
            # Try OCR with more aggressive settings
            temp_ocr = Path(output_path.parent) / f"temp_page_{page_num}_ocr.pdf"
            ocrmypdf_cmd = shutil.which('ocrmypdf') or 'E:\\00_dev_1\\.venv\\Scripts\\ocrmypdf.exe'
            
            # Use maximum quality for problematic page
            cmd = [ocrmypdf_cmd, '--force-ocr', '--output-type', 'pdf', 
                   '--oversample', '450', '--optimize', '0',
                   '--pdfa-image-compression', 'lossless',
                   str(temp_single), str(temp_ocr)]
            
            success, _ = run_subprocess(cmd)
            
            if success and temp_ocr.exists():
                # Replace page in output PDF
                doc_out = fitz.open(output_path)
                doc_new_page = fitz.open(temp_ocr)
                doc_out.delete_page(page_num - 1)
                doc_out.insert_pdf(doc_new_page, from_page=0, to_page=0, start_at=page_num-1)
                doc_out.save(str(output_path), garbage=4, deflate=True)
                doc_out.close()
                doc_new_page.close()
                
                print(f"    ✓ Fixed page {page_num}")
            
            # Cleanup
            if temp_single.exists():
                temp_single.unlink()
            if temp_ocr.exists():
                temp_ocr.unlink()
                
        except Exception as e:
            print(f"    ✗ Could not fix page {page_num}: {e}")
    
    return True, f"Re-OCR'd {len(failed_pages)} pages"
```

**Integrate into `_process_clean_pdf`** (after STEP 2, before STEP 3):

```python
        # STEP 2: OCR the cleaned PDF
        print(f"[STEP 2] Running OCR (600 DPI) on cleaned file...")
        ocrmypdf_cmd = shutil.which('ocrmypdf') or 'E:\\00_dev_1\\.venv\\Scripts\\ocrmypdf.exe'
        
        # Use --redo-ocr to preserve existing good text
        cmd = [ocrmypdf_cmd, '--redo-ocr', '--output-type', 'pdfa', 
               '--oversample', '600', '--optimize', '1',
               '--jbig2-lossy', ocr_input, str(output_path)]
        success, out = run_subprocess(cmd)
        
        # NEW: Validate and fix individual pages if needed
        if success or output_path.exists():
            print(f"[STEP 2b] Validating OCR coverage...")
            validate_and_fix_ocr(pdf_path, output_path)
        
        if not success:
            # ... existing fallback code ...
```

### Priority 3: Skip Compression for Incomplete OCR [MEDIUM]

**Modify STEP 4** to check OCR completeness first:

```python
        # STEP 4: Compress PDF only if OCR is complete
        print(f"[STEP 4] Checking OCR completeness before compression...")
        
        # Validate all pages have text
        all_pages_ok = True
        with open(output_path, 'rb') as f:
            pdf = PyPDF2.PdfReader(f)
            for i in range(len(pdf.pages)):
                text = pdf.pages[i].extract_text().strip()
                if len(text) < 50:
                    all_pages_ok = False
                    print(f"  [WARN] Page {i+1} has insufficient text - skipping compression")
                    break
        
        if all_pages_ok:
            print(f"[STEP 4] All pages OK - proceeding with compression...")
            # ... existing compression code ...
        else:
            print(f"[STEP 4] Skipped compression due to incomplete OCR")
            return ProcessingResult(file_name=output_path.name, status='PARTIAL',
                                  error="Some pages lack selectable text")
```

### Priority 4: Enhanced Diagnostics [LOW]

Add `--verbose` flag to ocrmypdf for debugging:

```python
cmd = [ocrmypdf_cmd, '--redo-ocr', '--output-type', 'pdfa', 
       '--oversample', '600', '--optimize', '1',
       '--jbig2-lossy', '--verbose', '1',  # Add verbose output
       ocr_input, str(output_path)]
```

Save ocrmypdf logs to `_log/` directory for failed files.

## Testing Plan

### Test 1: Verify `--redo-ocr` Works
```bash
# Delete existing output
rm "G:\...\03_doc-clean\20230906_9c1_FIC_Amended_Petition_No_Coverage_o.pdf"

# Run Phase 3 with new code
python doc-process-v31.py --dir "G:\..." --phase clean --no-verify

# Validate page 5 now has text
python diagnose_ocr_issue.py
```

**Expected**: Page 5 should now show `✓ HAS TEXT`

### Test 2: Per-Page Retry
For files where `--redo-ocr` still fails on some pages:
1. Validation should detect failed pages
2. Per-page retry with `--force-ocr --optimize 0` should fix them
3. Final validation should show 100% text coverage

### Test 3: Compression Safety
1. Files with partial OCR should skip compression
2. Files with complete OCR should compress normally
3. Verify compressed files still have all text

## Implementation Priority

1. **Change `--force-ocr` to `--redo-ocr`** [IMMEDIATE - 5 min]
   - Single line change, huge impact
   - Preserves existing good text
   - Focuses OCR on problematic pages
   
2. **Add per-page validation & retry** [HIGH - 30 min]
   - Ensures no pages slip through
   - Provides detailed diagnostics
   - Fixes edge cases like page 5
   
3. **Skip compression for partial OCR** [MEDIUM - 10 min]
   - Prevents further degradation
   - Clear status reporting
   
4. **Enhanced logging** [LOW - 15 min]
   - Helps debug future issues
   - Provides audit trail

## Additional ocrmypdf Parameters to Consider

```bash
--skip-big 50           # Skip images >50MB (prevents memory issues)
--rotate-pages          # Auto-rotate pages based on text orientation
--deskew                # Straighten crooked scans
--clean                 # Clean up background noise
--remove-background     # Aggressive background removal
--threshold             # Better for low-contrast documents
--jpeg-quality 95       # Higher JPEG quality (default 75)
--png-quality 95        # Higher PNG quality
```

For **page 5 specifically**, try:
```bash
ocrmypdf --force-ocr --clean --deskew --remove-background \
  --oversample 450 --optimize 0 input.pdf output.pdf
```

## References
- ocrmypdf docs: https://ocrmypdf.readthedocs.io/
- Issue tracker: https://github.com/ocrmypdf/OCRmyPDF/issues
- Tesseract docs: https://tesseract-ocr.github.io/

## Next Steps

1. Apply Priority 1 change immediately
2. Test with problematic file
3. If page 5 still fails, apply Priority 2 (per-page retry)
4. Document results in this file
5. Commit improvements with descriptive message
