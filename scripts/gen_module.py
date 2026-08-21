#!/usr/bin/env python3
import os
import sys

def scaffold_module(module_path):
    if not module_path:
        print("Usage: python scripts/gen_module.py <module_path>")
        sys.exit(1)
        
    parts = module_path.split('/')
    if len(parts) < 2:
        print("Error: module_path must be at least in format 'folder/module_name'")
        sys.exit(1)
        
    # Tạo thư mục code chính
    os.makedirs(os.path.dirname(module_path), exist_ok=True)
    
    # Tạo file __init__.py nếu chưa có
    init_path = os.path.join(os.path.dirname(module_path), '__init__.py')
    if not os.path.exists(init_path):
        with open(init_path, 'w', encoding='utf-8') as f:
            f.write("# Tự động sinh bởi gen_module.py\n")

    # Tạo file code chính
    main_file = f"{module_path}.py"
    if not os.path.exists(main_file):
        with open(main_file, 'w', encoding='utf-8') as f:
            f.write(f'"""\nModule {os.path.basename(module_path)}.\n\nVì sao chọn cách này: (Viết giải thích kiến trúc vào đây)\n"""\n\n')
            f.write("def process() -> None:\n    pass\n")
            print(f"Created {main_file}")

    # Tạo thư mục và file test
    test_dir = os.path.join("tests", os.path.dirname(module_path))
    os.makedirs(test_dir, exist_ok=True)
    test_file = os.path.join(test_dir, f"test_{os.path.basename(module_path)}.py")
    if not os.path.exists(test_file):
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(f'def test_process():\n    assert True\n')
            print(f"Created {test_file}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        scaffold_module(sys.argv[1])
    else:
        print("Missing module path.")
