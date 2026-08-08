import zipfile
import xml.etree.ElementTree as ET
import glob

def read_docx(path):
    text = []
    try:
        with zipfile.ZipFile(path) as docx:
            xml_content = docx.read('word/document.xml')
            tree = ET.XML(xml_content)
            for paragraph in tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                texts = [node.text for node in paragraph.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t') if node.text]
                if texts:
                    text.append(''.join(texts))
    except Exception as e:
        print(f"Error reading {path}: {e}")
    return '\n'.join(text)

for file in glob.glob('*.docx'):
    print(f"--- {file} ---")
    print(read_docx(file))