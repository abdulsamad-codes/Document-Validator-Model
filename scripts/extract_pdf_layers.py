import fitz
import os

def dissect_pdf_page(pdf_path, page_num=2):
    print(f"Opening {pdf_path} and dissecting Page {page_num}...")
    doc = fitz.open(pdf_path)
    page_index = page_num - 1
    page = doc[page_index]
    
    # 1. Check for actual text (if it's not just a scanned image)
    text = page.get_text()
    if text.strip():
        print("\n--- HIDDEN TEXT FOUND IN PDF LAYER ---")
        print(text)
        print("--------------------------------------")
    else:
        print("\nNo embedded text found. This is likely a scanned document (images only).")
        
    # 2. Extract all separate images from the page
    # If the blue stamp was added as a separate image layer, we can extract the base layer without it.
    image_list = page.get_images(full=True)
    print(f"\nFound {len(image_list)} separate image layers on this page.")
    
    for img_index, img_info in enumerate(image_list):
        xref = img_info[0]
        base_image = doc.extract_image(xref)
        image_bytes = base_image["image"]
        image_ext = base_image["ext"]
        
        image_filename = f"page_{page_num}_layer_{img_index}.{image_ext}"
        with open(image_filename, "wb") as f:
            f.write(image_bytes)
        print(f"Saved image layer to: {image_filename}")
        
    # 3. Remove all vector drawings/annotations and save a clean PDF
    # If the blue stamp is a PDF vector shape (like a colored rectangle) or an annotation
    for annot in page.annots():
        page.delete_annot(annot)
        
    # To remove vector graphics like rectangles, we can redact the page contents, 
    # but let's first save the PDF without annotations.
    clean_pdf_path = f"Cleaned_Annotations_{pdf_path}"
    doc.save(clean_pdf_path)
    print(f"\nSaved a new PDF with annotations removed: {clean_pdf_path}")

if __name__ == "__main__":
    pdf_file = "DGAM Onboarding file.pdf"
    if os.path.exists(pdf_file):
        dissect_pdf_page(pdf_file)
    else:
        print(f"Could not find {pdf_file}")
