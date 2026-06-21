"""
generate_report_pdf.py
Converts report.md → report.pdf using only stdlib + optional libs.
Tries: weasyprint → reportlab → fpdf2 → fallback HTML file.
"""
import subprocess, sys, os

def try_weasyprint():
    try:
        import markdown
        from weasyprint import HTML
        with open("report.md", encoding="utf-8") as f:
            md_text = f.read()
        html_body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
        html = f"""<!DOCTYPE html><html><head>
        <meta charset="utf-8">
        <style>
          body{{font-family:Arial,sans-serif;font-size:11pt;max-width:800px;margin:40px auto;color:#111;line-height:1.6}}
          h1{{color:#3730a3;border-bottom:2px solid #3730a3;padding-bottom:6px}}
          h2{{color:#4338ca;margin-top:28px;border-bottom:1px solid #c7d2fe;padding-bottom:4px}}
          h3{{color:#5b21b6}}
          table{{border-collapse:collapse;width:100%;margin:12px 0;font-size:10pt}}
          th{{background:#3730a3;color:#fff;padding:8px 12px;text-align:left}}
          td{{border:1px solid #ddd;padding:7px 12px}}
          tr:nth-child(even){{background:#f5f3ff}}
          code,pre{{background:#1e1e2e;color:#cdd6f4;padding:2px 6px;border-radius:4px;font-size:9.5pt}}
          pre{{padding:12px;overflow-x:auto;border-radius:6px}}
          pre code{{background:none;padding:0}}
          blockquote{{border-left:4px solid #6366f1;margin:0;padding:8px 16px;background:#f5f3ff}}
          hr{{border:none;border-top:1px solid #e0e7ff;margin:20px 0}}
        </style></head><body>{html_body}</body></html>"""
        HTML(string=html).write_pdf("report.pdf")
        print("[OK] report.pdf generated via weasyprint")
        return True
    except Exception as e:
        print(f"weasyprint failed: {e}")
        return False

def try_reportlab():
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Preformatted
        from reportlab.lib.enums import TA_LEFT

        doc = SimpleDocTemplate("report.pdf", pagesize=A4,
                                leftMargin=2.5*cm, rightMargin=2.5*cm,
                                topMargin=2.5*cm, bottomMargin=2.5*cm)
        styles = getSampleStyleSheet()
        story = []

        heading_color = colors.HexColor("#3730a3")
        h2_color      = colors.HexColor("#4338ca")

        h1_style = ParagraphStyle("H1", parent=styles["Heading1"], textColor=heading_color, fontSize=18, spaceAfter=10)
        h2_style = ParagraphStyle("H2", parent=styles["Heading2"], textColor=h2_color, fontSize=14, spaceBefore=16, spaceAfter=6)
        h3_style = ParagraphStyle("H3", parent=styles["Heading3"], fontSize=11, spaceBefore=10, spaceAfter=4)
        body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=6)
        code_style = ParagraphStyle("Code", parent=styles["Code"], fontSize=9, leading=12, backColor=colors.HexColor("#f1f5f9"), textColor=colors.HexColor("#0f172a"), leftIndent=12, rightIndent=12, spaceBefore=6, spaceAfter=6, borderPadding=(6,6,6,6), fontName="Courier-Bold")

        with open("report.md", encoding="utf-8") as f:
            lines = f.readlines()

        in_code = False
        code_buf = []
        in_table = False
        table_rows = []

        def flush_table():
            if not table_rows: return
            col_count = max(len(r) for r in table_rows)
            data = []
            for i, row in enumerate(table_rows):
                if all(set(c.strip()) <= set("-:|") for c in row):
                    continue
                padded = (row + [""] * col_count)[:col_count]
                data.append([Paragraph(str(c).strip(), body_style) for c in padded])
            if not data: return
            col_w = (A4[0] - 5*cm) / col_count
            t = Table(data, colWidths=[col_w]*col_count)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), heading_color),
                ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                ("FONTSIZE", (0,0), (-1,-1), 9),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f5f3ff")]),
                ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#c7d2fe")),
                ("VALIGN", (0,0), (-1,-1), "TOP"),
                ("TOPPADDING", (0,0), (-1,-1), 5),
                ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ]))
            story.append(t)
            story.append(Spacer(1, 8))

        for line in lines:
            stripped = line.rstrip("\n")

            # Code fences
            if stripped.startswith("```"):
                if not in_code:
                    in_code = True
                    code_buf = []
                else:
                    in_code = False
                    code_text = "\n".join(code_buf)
                    story.append(Preformatted(code_text, code_style))
                continue
            if in_code:
                code_buf.append(stripped)
                continue

            # Table rows
            if "|" in stripped and stripped.strip().startswith("|"):
                if in_table is False:
                    in_table = True
                    table_rows = []
                cells = [c for c in stripped.split("|") if c != ""]
                table_rows.append(cells)
                continue
            else:
                if in_table:
                    flush_table()
                    table_rows = []
                    in_table = False

            # Headings
            if stripped.startswith("# "):
                story.append(Paragraph(stripped[2:], h1_style))
                story.append(HRFlowable(width="100%", thickness=1, color=heading_color))
            elif stripped.startswith("## "):
                story.append(Paragraph(stripped[3:], h2_style))
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#c7d2fe")))
            elif stripped.startswith("### "):
                story.append(Paragraph(stripped[4:], h3_style))
            elif stripped.startswith("---"):
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e0e7ff")))
            elif stripped.strip() == "":
                story.append(Spacer(1, 6))
            else:
                # Strip markdown bold/code to plain text to avoid XML parse errors
                import re
                text = re.sub(r'\*\*(.+?)\*\*', r'\1', stripped)
                text = re.sub(r'`(.+?)`', r'\1', text)
                # Escape XML special chars
                text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                story.append(Paragraph(text, body_style))

        if in_table:
            flush_table()

        doc.build(story)
        print("[OK] report.pdf generated via reportlab")
        return True
    except Exception as e:
        print(f"reportlab failed: {e}")
        return False

def install_and_retry(pkg, fn):
    print(f"Installing {pkg}…")
    subprocess.run([sys.executable, "-m", "pip", "install", pkg], check=True, capture_output=True)
    return fn()

if __name__ == "__main__":
    if not try_reportlab():
        install_and_retry("reportlab", try_reportlab)
    print("Done. Check report.pdf")
