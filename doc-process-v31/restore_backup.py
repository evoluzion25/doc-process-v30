#!/usr/bin/env python3
"""
Backup Restore Utility for doc-process-v31
Restores files from _backups directory
"""
import sys
from pathlib import Path
import shutil
from datetime import datetime

def list_backups(root_dir):
    """List all available backups"""
    backup_dir = root_dir / "_backups"
    
    if not backup_dir.exists():
        print("[ERROR] No backups directory found")
        return []
    
    backups = sorted([d for d in backup_dir.iterdir() if d.is_dir()], reverse=True)
    
    if not backups:
        print("[INFO] No backups available")
        return []
    
    print("\n" + "="*80)
    print("AVAILABLE BACKUPS")
    print("="*80)
    
    for idx, backup in enumerate(backups, 1):
        print(f"\n{idx}. {backup.name}")
        
        # Read metadata if exists
        metadata_file = backup / "BACKUP_METADATA.txt"
        session_file = backup / "SESSION_BACKUP_INFO.txt"
        
        if session_file.exists():
            print("   Type: Full Session Backup")
            with open(session_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if "Files Backed Up:" in line:
                        print(f"   {line.strip()}")
                        break
        elif metadata_file.exists():
            print("   Type: Individual File Backup")
            with open(metadata_file, 'r', encoding='utf-8') as f:
                content = f.read()
                ops = content.count("Operation:")
                print(f"   Files: {ops}")
        
        # Count files
        file_count = len(list(backup.rglob("*.pdf")))
        print(f"   PDFs: {file_count}")
    
    print("\n" + "="*80)
    return backups

def restore_backup(backup_dir, target_dir, dry_run=True):
    """Restore files from backup directory"""
    
    if not backup_dir.exists():
        print(f"[ERROR] Backup directory not found: {backup_dir}")
        return False
    
    # Find all files to restore (excluding metadata)
    files_to_restore = []
    for file_path in backup_dir.rglob("*"):
        if file_path.is_file() and not file_path.name.endswith("_INFO.txt") and not file_path.name.endswith("_METADATA.txt"):
            # Calculate relative path from backup dir
            rel_path = file_path.relative_to(backup_dir)
            target_path = target_dir / rel_path
            files_to_restore.append((file_path, target_path))
    
    if not files_to_restore:
        print("[INFO] No files to restore")
        return False
    
    print(f"\n{'='*80}")
    print(f"RESTORE PLAN: {len(files_to_restore)} files")
    print(f"{'='*80}")
    
    for source, target in files_to_restore[:10]:  # Show first 10
        print(f"  {source.name} → {target.relative_to(target_dir)}")
    
    if len(files_to_restore) > 10:
        print(f"  ... and {len(files_to_restore) - 10} more files")
    
    if dry_run:
        print(f"\n[DRY RUN] No files were modified")
        print(f"[DRY RUN] Run with --execute to perform actual restore")
        return True
    
    # Perform actual restore
    print(f"\n[RESTORE] Copying {len(files_to_restore)} files...")
    restored = 0
    skipped = 0
    
    for source, target in files_to_restore:
        try:
            # Create parent directory if needed
            target.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if target exists
            if target.exists():
                print(f"[SKIP] Already exists: {target.name}")
                skipped += 1
            else:
                shutil.copy2(str(source), str(target))
                restored += 1
                print(f"[OK] Restored: {target.name}")
        
        except Exception as e:
            print(f"[ERROR] Failed to restore {source.name}: {e}")
    
    print(f"\n{'='*80}")
    print(f"[DONE] Restored: {restored}, Skipped: {skipped}")
    print(f"{'='*80}")
    
    return True

def main():
    """Main restore utility"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Restore backups from doc-process-v31")
    parser.add_argument("--dir", required=True, help="Root directory with _backups folder")
    parser.add_argument("--backup", help="Specific backup directory name (e.g., 20251109-153045)")
    parser.add_argument("--execute", action="store_true", help="Actually perform restore (default is dry-run)")
    parser.add_argument("--latest", action="store_true", help="Restore most recent backup")
    
    args = parser.parse_args()
    
    root_dir = Path(args.dir)
    
    if not root_dir.exists():
        print(f"[ERROR] Directory not found: {root_dir}")
        sys.exit(1)
    
    # List available backups
    backups = list_backups(root_dir)
    
    if not backups:
        sys.exit(1)
    
    # Select backup
    if args.latest:
        selected_backup = backups[0]
        print(f"\n[SELECT] Using latest backup: {selected_backup.name}")
    elif args.backup:
        matching = [b for b in backups if args.backup in b.name]
        if not matching:
            print(f"[ERROR] No backup found matching: {args.backup}")
            sys.exit(1)
        selected_backup = matching[0]
        print(f"\n[SELECT] Using backup: {selected_backup.name}")
    else:
        # Interactive selection
        print("\nEnter backup number to restore (or 'q' to quit): ", end='')
        try:
            choice = input().strip()
            if choice.lower() == 'q':
                print("Cancelled")
                sys.exit(0)
            idx = int(choice) - 1
            if idx < 0 or idx >= len(backups):
                print("[ERROR] Invalid selection")
                sys.exit(1)
            selected_backup = backups[idx]
        except ValueError:
            print("[ERROR] Invalid input")
            sys.exit(1)
    
    # Perform restore
    dry_run = not args.execute
    if dry_run:
        print("\n[DRY RUN MODE] Use --execute to perform actual restore")
    
    restore_backup(selected_backup, root_dir, dry_run=dry_run)

if __name__ == "__main__":
    main()
