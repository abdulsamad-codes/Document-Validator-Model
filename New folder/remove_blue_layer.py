import fitz
import os

def remove_pdf_layers_all_pages(pdf_path, output_path):
    print(f"Opening {pdf_path} to remove blue layers from ALL pages...")
    doc = fitz.open(pdf_path)
    
    total_annots_removed = 0
    
    # Loop through every single page in the PDF
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # 1. Look for and remove any PDF annotations (the blue stamps were added as annotations)
        # Using list() to ensure we safely iterate while deleting
        annots = list(page.annots())
        for annot in annots:
            page.delete_annot(annot)
            total_annots_removed += 1
            
    print(f"Removed a total of {total_annots_removed} annotation layer(s) across all {len(doc)} pages.")
    
    # Save the cleaned PDF
    doc.save(output_path)
    print(f"Saved the perfectly cleaned PDF as: {output_path}")

if __name__ == "__main__":
    pdf_file = "DGAM Onboarding file.pdf"
    if os.path.exists(pdf_file):
        remove_pdf_layers_all_pages(pdf_file, "Cleaned_Document_Full.pdf")
    else:
        print(f"Error: {pdf_file} not found in this folder.")
