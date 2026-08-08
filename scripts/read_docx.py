#!/usr/bin/env python3
"""
Read and extract plain text from .docx files.
Useful for parsing Rules.docx and Document_Verification_Pipeline.docx.
"""

import zipfile
import xml.etree.ElementTree as ET
import glob
import sys


def read_docx(path: str) -> str:
    """
    Extract all paragraph text from a .docx file.

    Args:
        path: Path to the .docx file.

    Returns:
        Extracted text as a single string, paragraphs separated by newlines.
    """
    text = []
    ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    try:
        with zipfile.ZipFile(path) as docx:
            xml_content = docx.read('word/document.xml')
            tree = ET.XML(xml_content)
            for paragraph in tree.iter(f'{ns}p'):
                texts = [
                    node.text
                    for node in paragraph.iter(f'{ns}t')
                    if node.text
                ]
                if texts:
                    text.append(''.join(texts))
    except FileNotFoundError:
        print(f"Error: File not found — {path}")
    except zipfile.BadZipFile:
        print(f"Error: Not a valid .docx file — {path}")
    except Exception as e:
        print(f"Error reading {path}: {e}")
    return '\n'.join(text)


if __name__ == "__main__":
    # If a specific file is provided as argument, read that
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        print(f"--- {file_path} ---")
        print(read_docx(file_path))
    else:
        # Otherwise read all .docx files in current directory
        docx_files = glob.glob('*.docx')
        if not docx_files:
            print("No .docx files found in current directory.")
        for file in docx_files:
            print(f"\n{'='*60}")
            print(f"--- {file} ---")
            print('='*60)
            print(read_docx(file))
