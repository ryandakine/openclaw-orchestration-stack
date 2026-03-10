#!/usr/bin/env python3
"""
Simple JSON validity tests for all workflow and credential files.
"""

import json
import sys
from pathlib import Path


def validate_json_files(directory: Path, pattern: str = "*.json") -> dict:
    """Validate all JSON files in a directory."""
    results = {
        'valid': [],
        'invalid': [],
        'total': 0
    }
    
    for json_file in directory.rglob(pattern):
        # Skip node_modules and other common excludes
        if any(part.startswith('.') or part == 'node_modules' 
               for part in json_file.parts):
            continue
        
        results['total'] += 1
        
        try:
            with open(json_file, 'r') as f:
                json.load(f)
            results['valid'].append(json_file)
        except json.JSONDecodeError as e:
            results['invalid'].append((json_file, str(e)))
    
    return results


def main():
    """Main test runner."""
    base_dir = Path(__file__).parent.parent
    
    print("=" * 70)
    print("JSON Validity Tests")
    print("=" * 70)
    
    # Test workflows
    workflows_dir = base_dir / 'workflows'
    print(f"\n📋 Testing workflow files in: {workflows_dir}")
    workflow_results = validate_json_files(workflows_dir)
    
    for valid_file in workflow_results['valid']:
        print(f"  ✓ {valid_file.name}")
    
    for invalid_file, error in workflow_results['invalid']:
        print(f"  ✗ {invalid_file.name}: {error}")
    
    # Test credentials
    creds_dir = base_dir / 'credentials'
    print(f"\n📋 Testing credential files in: {creds_dir}")
    creds_results = validate_json_files(creds_dir)
    
    for valid_file in creds_results['valid']:
        print(f"  ✓ {valid_file.name}")
    
    for invalid_file, error in creds_results['invalid']:
        print(f"  ✗ {invalid_file.name}: {error}")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    total_valid = len(workflow_results['valid']) + len(creds_results['valid'])
    total_invalid = len(workflow_results['invalid']) + len(creds_results['invalid'])
    total = workflow_results['total'] + creds_results['total']
    
    print(f"Total files: {total}")
    print(f"Valid: {total_valid} ✓")
    print(f"Invalid: {total_invalid} ✗")
    
    if total_invalid == 0:
        print("\n✅ All JSON files are valid")
        return 0
    else:
        print("\n❌ Some JSON files are invalid")
        return 1


if __name__ == '__main__':
    sys.exit(main())
