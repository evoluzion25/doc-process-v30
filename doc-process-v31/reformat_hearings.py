#!/usr/bin/env python3
"""
Reformat hearing transcripts from v31 format to improved hearing format.

This script converts:
- [BEGIN PDF Page X] → [Page X BEGIN] / [Page X END]
- Adds double spacing between pages
- Preserves line numbers (critical for legal citations)
- Removes footer text (FTP, PAGE #)
- Updates header to "HEARING TRANSCRIPT INFORMATION"
- Adds file size and line number preservation note

Usage:
    python reformat_hearings.py --dir "path/to/04_Hearings"
    python reformat_hearings.py --file "path/to/specific_v31.txt"
    python reformat_hearings.py --dir "path/to/04_Hearings" --test (dry run)
"""

import argparse
import re
from pathlib import Path
from typing import List, Tuple


def get_file_size_kb(pdf_path: Path) -> str:
    """Get file size in KB."""
    if pdf_path.exists():
        size_bytes = pdf_path.stat().st_size
        size_kb = size_bytes / 1024
        return f"{size_kb:.1f} KB"
    return "Unknown"


def remove_footer_lines(text: str) -> str:
    """Remove footer lines like 'FTP 9-CC-5100, 12-26-23, 11:00 a.m., PAGE #X'"""
    # Pattern matches lines like: FTP 9-CC-5100, 12-26-23, 11:00 a.m., PAGE #1
    footer_pattern = r'^FTP.*?PAGE #\d+\s*$'
    lines = text.split('\n')
    cleaned_lines = [line for line in lines if not re.match(footer_pattern, line, re.MULTILINE)]
    return '\n'.join(cleaned_lines)


def convert_page_markers(text: str) -> str:
    """
    Convert [BEGIN PDF Page X] to [Page X BEGIN] format.
    """
    # Simple replacement - just change the format
    text = re.sub(r'\[BEGIN PDF Page (\d+)\]', r'[Page \1 BEGIN]', text)
    return text


def update_header(text: str, pdf_name: str, total_pages: int, file_size: str) -> str:
    """Update header from DOCUMENT INFORMATION to HEARING TRANSCRIPT INFORMATION."""
    
    # Extract document name from header
    doc_name_match = re.search(r'DOCUMENT NAME:\s*(.+)', text)
    doc_name = doc_name_match.group(1) if doc_name_match else "Unknown"
    
    # Extract PDF directory and public link
    pdf_dir_match = re.search(r'PDF DIRECTORY:\s*(.+)', text)
    pdf_dir = pdf_dir_match.group(1) if pdf_dir_match else "Unknown"
    
    pdf_link_match = re.search(r'PDF PUBLIC LINK:\s*(.+)', text)
    pdf_link = pdf_link_match.group(1) if pdf_link_match else "Unknown"
    
    new_header = f"""§§ HEARING TRANSCRIPT INFORMATION §§

DOCUMENT NUMBER: [TBD]
DOCUMENT NAME: {doc_name}
TOTAL PAGES: {total_pages}
FILE SIZE: {file_size}

IMPORTANT: This transcript preserves original line numbers for legal citations.
Line numbers are essential for referencing specific testimony and must be preserved.

=====================================================================
BEGINNING OF HEARING TRANSCRIPT
====================================================================="""
    
    # Find the end of the old header (after "BEGINNING OF PROCESSED DOCUMENT")
    header_end_pattern = r'={69}\s*BEGINNING OF PROCESSED DOCUMENT\s*={69}\s*'
    match = re.search(header_end_pattern, text)
    
    if match:
        # Replace everything before the header end with new header
        return new_header + '\n' + text[match.end():]
    
    # Fallback: just prepend new header if pattern not found
    return new_header + '\n\n' + text


def clean_transcript_formatting(text: str) -> str:
    """Clean up various formatting issues in hearing transcripts."""
    
    # Join line numbers with their content (critical for legal citations)
    # Pattern: line number on its own line, followed by content on next line
    lines = text.split('\n')
    cleaned_lines = []
    i = 0
    
    while i < len(lines):
        current_line = lines[i]
        
        # Check if this line is ONLY a line number (1-2 digits, whitespace trimmed)
        stripped = current_line.strip()
        if stripped and re.match(r'^\d{1,2}$', stripped):
            # This is a standalone line number
            # Find the next non-blank line
            next_content_idx = i + 1
            while next_content_idx < len(lines) and not lines[next_content_idx].strip():
                next_content_idx += 1
            
            # If we found content, merge them
            if next_content_idx < len(lines):
                next_content = lines[next_content_idx]
                # Merge: "1 STATE OF MICHIGAN"
                merged = f"{stripped} {next_content}"
                cleaned_lines.append(merged)
                i = next_content_idx + 1  # Skip to line after content
                continue
        
        # Not a line number, keep as-is
        cleaned_lines.append(current_line)
        i += 1
    
    # Remove extra blank lines (more than 2 consecutive)
    result = '\n'.join(cleaned_lines)
    result = re.sub(r'\n{4,}', '\n\n\n', result)
    
    return result


def reformat_hearing_transcript(input_file: Path, output_file: Path = None, dry_run: bool = False) -> bool:
    """
    Reformat a single hearing transcript file.
    
    Args:
        input_file: Path to input v31.txt file
        output_file: Path to output file (defaults to same location with _hearing suffix)
        dry_run: If True, only show what would be done
    
    Returns:
        True if successful, False otherwise
    """
    
    if not input_file.exists():
        print(f"[ERROR] File not found: {input_file}")
        return False
    
    # Read input file
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"[ERROR] Failed to read {input_file}: {e}")
        return False
    
    # Extract total pages from content
    page_count_match = re.search(r'TOTAL PAGES:\s*(\d+)', content)
    total_pages = int(page_count_match.group(1)) if page_count_match else 0
    
    # Get PDF file size
    pdf_name = input_file.stem.replace('_v31', '_o') + '.pdf'
    pdf_path = input_file.parent.parent / '03_doc-clean' / pdf_name
    file_size = get_file_size_kb(pdf_path)
    
    # Apply transformations
    print(f"[PROCESSING] {input_file.name}")
    
    # Step 1: Remove footer lines
    content = remove_footer_lines(content)
    print(f"  ✓ Removed footer lines")
    
    # Step 2: Join line numbers with content (BEFORE page marker conversion)
    content = clean_transcript_formatting(content)
    print(f"  ✓ Merged line numbers with content")
    
    # Step 3: Convert page markers
    content = convert_page_markers(content)
    print(f"  ✓ Converted page markers to [Page X BEGIN/END]")
    
    # Step 4: Update header
    content = update_header(content, pdf_name, total_pages, file_size)
    print(f"  ✓ Updated header to HEARING TRANSCRIPT INFORMATION")
    
    # Determine output file
    if output_file is None:
        # Replace _v31 with _hearing
        output_file = input_file.parent / input_file.name.replace('_v31.txt', '_hearing.txt')
    
    if dry_run:
        print(f"[DRY RUN] Would write to: {output_file}")
        return True
    
    # Write output file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[OK] Created: {output_file.name}\n")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to write {output_file}: {e}")
        return False


def reformat_directory(directory: Path, dry_run: bool = False) -> Tuple[int, int]:
    """
    Reformat all v31.txt files in a directory's 05_doc-format folder.
    
    Returns:
        Tuple of (success_count, total_count)
    """
    format_dir = directory / '05_doc-format'
    
    if not format_dir.exists():
        print(f"[ERROR] Format directory not found: {format_dir}")
        return (0, 0)
    
    # Find all v31 files
    v31_files = sorted(format_dir.glob('*_v31.txt'))
    
    if not v31_files:
        print(f"[WARN] No v31.txt files found in {format_dir}")
        return (0, 0)
    
    print(f"\n[INFO] Found {len(v31_files)} hearing transcript(s) to reformat")
    print(f"[INFO] Location: {format_dir}\n")
    
    success_count = 0
    for v31_file in v31_files:
        if reformat_hearing_transcript(v31_file, dry_run=dry_run):
            success_count += 1
    
    return (success_count, len(v31_files))


def main():
    parser = argparse.ArgumentParser(
        description='Reformat hearing transcripts from v31 to improved hearing format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Reformat all hearings in a directory
  python reformat_hearings.py --dir "G:\\path\\to\\04_Hearings"
  
  # Reformat a single file
  python reformat_hearings.py --file "G:\\path\\to\\20231226_9c1_Hearing_v31.txt"
  
  # Dry run (test without writing files)
  python reformat_hearings.py --dir "G:\\path\\to\\04_Hearings" --test
        """
    )
    
    parser.add_argument('--dir', type=str, help='Directory containing 05_doc-format folder with v31.txt files')
    parser.add_argument('--file', type=str, help='Single v31.txt file to reformat')
    parser.add_argument('--test', action='store_true', help='Dry run - show what would be done without writing files')
    
    args = parser.parse_args()
    
    if not args.dir and not args.file:
        parser.error("Must specify either --dir or --file")
    
    if args.test:
        print("[DRY RUN MODE] No files will be modified\n")
    
    if args.file:
        # Single file mode
        input_file = Path(args.file)
        success = reformat_hearing_transcript(input_file, dry_run=args.test)
        exit(0 if success else 1)
    
    if args.dir:
        # Directory mode
        directory = Path(args.dir)
        if not directory.exists():
            print(f"[ERROR] Directory not found: {directory}")
            exit(1)
        
        success_count, total_count = reformat_directory(directory, dry_run=args.test)
        
        print("\n" + "="*80)
        print(f"SUMMARY: Reformatted {success_count}/{total_count} hearing transcripts")
        print("="*80)
        
        exit(0 if success_count == total_count else 1)


if __name__ == '__main__':
    main()
