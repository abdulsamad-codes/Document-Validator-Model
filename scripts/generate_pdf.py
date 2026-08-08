import markdown
from fpdf import FPDF, HTMLMixin
import os

class HTML2PDF(FPDF, HTMLMixin):
    pass

def markdown_to_pdf(md_file, pdf_file):
    with open(md_file, 'r', encoding='utf-8') as f:
        text = f.read()
    
    # Sanitize text for standard fpdf fonts (replace smart quotes, dashes, etc.)
    text = text.replace('–', '-').replace('—', '-').replace('“', '"').replace('”', '"').replace('’', "'").replace('‘', "'")
    text = text.encode('ascii', 'ignore').decode('ascii')
    
    # Convert Markdown to HTML
    html = markdown.markdown(text, extensions=['tables'])
    
    # Create a simple valid HTML wrapper
    html = f"""
    <html>
        <body>
            {html}
        </body>
    </html>
    """
    
    # Initialize PDF
    pdf = HTML2PDF()
    pdf.add_page()
    
    # Add HTML to PDF
    # We replace some markdown specific outputs if they crash fpdf2, but usually it works.
    try:
        pdf.write_html(html)
        pdf.output(pdf_file)
        print(f"Successfully generated {pdf_file}")
    except Exception as e:
        print(f"Failed to generate PDF via HTML: {e}")

if __name__ == '__main__':
    md_path = 'docs/Master_Rules_Combined.md'
    pdf_path = 'docs/Master_Rules_Combined.pdf'
    
    markdown_to_pdf(md_path, pdf_path)
