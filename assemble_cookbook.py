# assemble_cookbook.py
import os
import shutil
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

from build_cookbook_engine import (
    ASSETS_DIR, OUT_DOCX_LOCAL, OUT_DOCX_ROOT, MD_PATH,
    add_heading_1, add_heading_2, add_para, add_image_figure
)
from cookbook_data_core import render_page_1, render_page_2, render_metadata_and_ch1, render_ch2_and_ch3
from cookbook_data_phases import render_phases_1_to_5, render_phases_6_to_10, render_phases_11_to_15, render_phases_16_to_20
from cookbook_data_reference import render_ch5_api_spec, render_ch6_troubleshooting, render_ch7_traceability
from cookbook_data_viva import render_ch8_viva_voce, render_ch9_and_ch10

def main():
    print("Initializing Document...")
    doc = Document()

    # Set margins
    for s in doc.sections:
        s.top_margin = Inches(0.75)
        s.bottom_margin = Inches(0.75)
        s.left_margin = Inches(0.75)
        s.right_margin = Inches(0.75)
        
        # Header & Footer
        p_h = s.header.paragraphs[0]
        p_h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_h = p_h.add_run("VESIT | Department of Computer Engineering | Project Cookbook")
        r_h.font.size = Pt(8.5)
        r_h.font.color.rgb = RGBColor(120, 120, 120)

        p_f = s.footer.paragraphs[0]
        p_f.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_f = p_f.add_run("SOCKETSCALE • Operational and Demonstration Guide")
        r_f.font.size = Pt(8.5)
        r_f.font.color.rgb = RGBColor(120, 120, 120)

    print("[Step 1] Rendering Page 1: Cover Page...")
    render_page_1(doc)

    print("[Step 2] Rendering Page 2: Table of Contents...")
    render_page_2(doc)

    print("[Step 3] Rendering Metadata & Chapter 1...")
    render_metadata_and_ch1(doc)

    print("[Step 4] Rendering Chapter 2 & Chapter 3...")
    render_ch2_and_ch3(doc)

    print("[Step 5] Rendering Chapter 4: Practical Implementation (Phases 1 - 20)...")
    render_phases_1_to_5(doc)
    render_phases_6_to_10(doc)
    render_phases_11_to_15(doc)
    render_phases_16_to_20(doc)

    print("[Step 6] Rendering Chapter 5: REST & WebSocket API Specification...")
    render_ch5_api_spec(doc)

    print("[Step 7] Rendering Chapter 6: Troubleshooting Manual (18 Issues)...")
    render_ch6_troubleshooting(doc)

    print("[Step 8] Rendering Chapter 7: Requirement Traceability Matrix (27 Reqs)...")
    render_ch7_traceability(doc)

    print("[Step 9] Rendering Chapter 8: Viva-Voce Examination Guide...")
    render_ch8_viva_voce(doc)

    print("[Step 10] Rendering Chapter 9 & 10: CAP Trade-offs & Conclusion...")
    render_ch9_and_ch10(doc)

    print("[Step 11] Rendering Appendix A: Demonstration Screenshots...")
    add_heading_1(doc, "Appendix A — Visual Prototype & Demonstration Screenshots")
    add_para(
        doc,
        "The following high-resolution terminal outputs, dashboard views, and test executions demonstrate the operational verification of SocketScale captured directly from the running environment."
    )

    screenshots = [
        ("01_login_screen.png", "A.1", "SocketScale Authenticated Access Interface with Demo Accounts"),
        ("08_live_user_chat.png", "A.2", "Multi-Room Real-Time Chat Dashboard with Active Gateway Node Indicator"),
        ("02_admin_overview.png", "A.3", "Cluster Overview Telemetry: Active Connections, Persistent Messages & Health"),
        ("03_gateway_cluster_nodes.png", "A.4", "Elastic Gateway Cluster Management & Live Node Telemetry"),
        ("04_infrastructure_health.png", "A.5", "Infrastructure Component Health: PostgreSQL, Redis & Outbox Worker"),
        ("05_fault_tolerance_lab.png", "A.6", "Fault Tolerance & Chaos Engineering Simulation Lab"),
        ("06_dynamic_benchmarks.png", "A.7", "Dynamic Multi-Client Benchmarking Console with Latency Percentiles"),
        ("07_system_event_logs.png", "A.8", "Auditable System Event Logs Stored Durably in PostgreSQL")
    ]
    for img_name, fig_num, caption in screenshots:
        add_image_figure(doc, img_name, fig_num, caption)

    print("[Step 12] Enforcing Justified Text Formatting...")
    for p in doc.paragraphs:
        txt = p.text.strip()
        if not txt:
            continue
        style_name = p.style.name
        if style_name.startswith('Heading') or style_name in ['Title', 'Subtitle']:
            continue
        if any(r._r.xpath('.//a:blip') for r in p.runs) or txt.startswith('Figure ') or txt.startswith('Appendix '):
            continue
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    print("[Step 13] Saving Word Document...")
    doc.save(OUT_DOCX_LOCAL)
    print(f"  -> Saved {OUT_DOCX_LOCAL}")
    
    try:
        shutil.copyfile(OUT_DOCX_LOCAL, OUT_DOCX_ROOT)
        print(f"  -> Saved {OUT_DOCX_ROOT}")
    except Exception as e:
        print(f"  [Notice on root copy]: {e}")

    print("[SUCCESS] All files assembled successfully.")

if __name__ == "__main__":
    main()
