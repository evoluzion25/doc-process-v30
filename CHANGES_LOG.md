# Document Processing - Version Changes Log

**Purpose**: Track what changed in each version and why
**Rule**: Update this log with EVERY new version

---

## v13 (October 31, 2025) - RESTORED AS CURRENT

**Status**: Known good quality
**Prompt**: Simple OCR correction
**Output Quality**: Excellent (tables formatted, numbered lists clean)
**File Suffix**: `_g1.txt`
**Footer**: No spacing (immediate END marker)

**Issues**: 
- Missing blank line before END marker

**Using this as baseline** - best quality achieved

---

## v14-v19 (November 1, 2025) - EXPERIMENTAL - FAILED

**Attempted Changes**:
- v14: Added verification phase, fixed file suffixes
- v15: Changed `_c.txt` to `_a.txt` (existing files)
- v16: Added structure preservation to prompt
- v17: Explicit footer newlines
- v18: Reverted to simple prompt
- v19: Added "CRITICAL: 65 characters"

**Results**: ALL degraded quality
- Tables broken (cells on separate lines)
- Numbered lists malformed (numbers separated from text)
- More lines = worse formatting
- OCR errors not fixed ("APPOINTPOINTMENT", "one one-half")

**Root Cause**: Any prompt changes from v13 degraded output

---

## v14r (Current - November 1, 2025)

**Based on**: v14 with improvements
**Changes**:
- Added: 2 blank lines before END marker (footer spacing)
- Changed: File suffix `_g1.txt` → `_v14r.txt` (shows version)
- Kept: v13 Gemini prompt (proven quality)
**Has**: 4 phases (OCR, Convert, Clean, Verify) + reporting
**File Suffix**: `_a.txt` for input, `_v14r.txt` for output

---

## v21 (Planned - November 1, 2025)

**Will change**:
- Phase 4 (Verify): Enhanced word-by-word comparison
- Phase 4: Extract text from PDF-A and compare to cleaned text
- Phase 4: Verify page markers match PDF page numbers
- Phase 4: Report word-level differences

**Reason**: Current verification too basic - need actual comparison using PDF-A searchable text

**Expected result**: Detailed verification report showing exact differences

---

## Future Version Template

### v## (Date)

**Changed**:
- What specifically changed

**Reason**:
- Why change was made

**Result**:
- Quality impact (better/worse/same)
- Line count change
- Specific improvements or regressions

**Revert if**: Quality degrades

---

**RULE**: Test each version on sample file before batch processing. Compare to v13 quality.

Last Updated: November 1, 2025
Current Version: v13-restored
Best Known Version: v13 (Oct 31, 2025)

