"""Generate PDF from the JobPilot Design Document markdown file."""
from fpdf import FPDF
import os

def generate_pdf():
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_font("Arial", "", "C:/Windows/Fonts/arial.ttf")
    pdf.add_font("Arial", "B", "C:/Windows/Fonts/arialbd.ttf")

    md_path = "pdfs/JobPilot_Design_Document.md"
    pdf_path = "pdfs/JobPilot_Design_Document.pdf"

    with open(md_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    pdf.add_page()
    pdf.set_font("Arial", "", 11)

    # Remove lines with problematic characters first
    clean_lines = []
    for line in lines:
        try:
            line.encode("latin-1")
            clean_lines.append(line)
        except UnicodeEncodeError:
            # Replace non-latin chars
            clean_line = line.encode("latin-1", errors="replace").decode("latin-1")
            clean_lines.append(clean_line)
    lines = clean_lines

    for line in lines:
        text = line.rstrip()
        if not text:
            pdf.ln(2)
            continue
        if line.startswith("# "):
            pdf.set_font("Arial", "B", 16)
            pdf.cell(0, 10, text[2:].strip(), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
            pdf.set_font("Arial", "", 11)
        elif line.startswith("## "):
            pdf.set_font("Arial", "B", 13)
            pdf.cell(0, 8, text[3:].strip(), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
            pdf.set_font("Arial", "", 11)
        elif line.startswith("### "):
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 7, text[4:].strip(), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
            pdf.set_font("Arial", "", 11)
        elif line.startswith("```"):
            continue
        elif line.startswith("- ") or line.startswith("* "):
            pdf.cell(4)
            pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin - 4, h=5, text=text)
        elif text and text[0].isdigit() and ". " in text[:4]:
            pdf.cell(4)
            pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin - 4, h=5, text=text)
        elif text.startswith("|") or text.startswith("|--"):
            continue
        else:
            pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin, h=5, text=text)

    pdf.output(pdf_path)
    size = os.path.getsize(pdf_path)
    print(f"PDF generated: {pdf_path}")
    print(f"File size: {size/1024:.0f} KB")

if __name__ == "__main__":
    generate_pdf()
