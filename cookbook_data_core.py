# cookbook_data_core.py
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from build_cookbook_engine import (
    ASSETS_DIR, add_heading_1, add_heading_2, add_heading_3,
    add_para, add_bullet, add_callout, add_code_block, style_table, set_cell_background
)
import os

def render_page_1(doc):
    # Banner / Title
    p_inst = doc.add_paragraph()
    p_inst.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_inst.paragraph_format.space_before = Pt(20)
    p_inst.paragraph_format.space_after = Pt(2)
    r_inst = p_inst.add_run("VIVEKANAND EDUCATION SOCIETY’S INSTITUTE OF TECHNOLOGY")
    r_inst.font.bold = True
    r_inst.font.size = Pt(14)
    r_inst.font.color.rgb = RGBColor(27, 54, 93)

    p_dept = doc.add_paragraph()
    p_dept.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_dept.paragraph_format.space_before = Pt(2)
    p_dept.paragraph_format.space_after = Pt(4)
    r_dept = p_dept.add_run("DEPARTMENT OF COMPUTER ENGINEERING")
    r_dept.font.bold = True
    r_dept.font.size = Pt(13)
    r_dept.font.color.rgb = RGBColor(27, 54, 93)

    p_cb = doc.add_paragraph()
    p_cb.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_cb.paragraph_format.space_before = Pt(4)
    p_cb.paragraph_format.space_after = Pt(14)
    r_cb = p_cb.add_run("MICRO PROJECT COOKBOOK")
    r_cb.font.bold = True
    r_cb.font.size = Pt(16)
    r_cb.font.color.rgb = RGBColor(30, 80, 150)

    # Divider line
    p_div = doc.add_paragraph()
    p_div.paragraph_format.space_after = Pt(12)
    p_div.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_div = p_div.add_run("━" * 55)
    r_div.font.color.rgb = RGBColor(180, 200, 220)

    # Project Title
    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_before = Pt(6)
    p_title.paragraph_format.space_after = Pt(8)
    r_t1 = p_title.add_run("Project Title : ")
    r_t1.font.bold = True
    r_t1.font.size = Pt(11)
    r_t2 = p_title.add_run("SOCKETSCALE - Fault-Tolerant Real-Time Pub/Sub WebSocket Gateway with Persistent Message History")
    r_t2.font.bold = True
    r_t2.font.size = Pt(11)

    # SDG Aligned & Logo
    p_sdg = doc.add_paragraph()
    p_sdg.paragraph_format.space_before = Pt(4)
    p_sdg.paragraph_format.space_after = Pt(4)
    r_s1 = p_sdg.add_run("SDG Aligned & Logo :")
    r_s1.font.bold = True
    r_s1.font.size = Pt(11)

    # Horizontal SDG Logos
    p_logos = doc.add_paragraph()
    p_logos.paragraph_format.space_before = Pt(4)
    p_logos.paragraph_format.space_after = Pt(4)
    p_logos.alignment = WD_ALIGN_PARAGRAPH.LEFT
    for logo_name in ["sdg9_logo.png", "sdg12_logo.png", "sdg8_logo.png"]:
        l_path = os.path.join(ASSETS_DIR, logo_name)
        if os.path.exists(l_path):
            p_logos.add_run().add_picture(l_path, width=Inches(1.15))
            p_logos.add_run("   ")

    p_sdg_txt = doc.add_paragraph()
    p_sdg_txt.paragraph_format.space_before = Pt(2)
    p_sdg_txt.paragraph_format.space_after = Pt(12)
    r_st = p_sdg_txt.add_run("SDG 9 - Industry, Innovation and Infrastructure; SDG 12 - Responsible Consumption and Production")
    r_st.font.size = Pt(9.5)
    r_st.font.italic = True

    # Course Details Table
    t0 = doc.add_table(rows=6, cols=2)
    t0.rows[0].cells[0].text = "Project / Course Details"
    t0.rows[0].cells[1].text = "To be filled by students"
    t0.rows[1].cells[0].text = "Course / Subject Name"
    t0.rows[1].cells[1].text = "Distributed Computing / System Design"
    t0.rows[2].cells[0].text = "Course Code / Semester / Academic Year"
    t0.rows[2].cells[1].text = "T.E. Computer Engineering / Semester V / 2026–2027"
    t0.rows[3].cells[0].text = "Faculty Incharge / Project Mentor"
    t0.rows[3].cells[1].text = "Dr. Priya R.L"
    t0.rows[4].cells[0].text = "Project Group No. (if applicable)"
    t0.rows[4].cells[1].text = "14"
    t0.rows[5].cells[0].text = "Submission Date"
    t0.rows[5].cells[1].text = "12 November 2026"
    for r in t0.rows:
        r.cells[0].paragraphs[0].runs[0].font.bold = True
    style_table(t0, [Inches(3.2), Inches(3.3)], header_bg="8B1E1E")

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # Team Details Table
    add_heading_3(doc, "Project Team Details")
    t1 = doc.add_table(rows=3, cols=4)
    t1.rows[0].cells[0].text = "Student Name"
    t1.rows[0].cells[1].text = "Roll No."
    t1.rows[0].cells[2].text = "Class"
    t1.rows[0].cells[3].text = "Institute Email ID"

    t1.rows[1].cells[0].text = "Mahek Ahuja"
    t1.rows[1].cells[1].text = "01"
    t1.rows[1].cells[2].text = "D12A"
    t1.rows[1].cells[3].text = "2024.mahek.ahuja@ves.ac.in"

    t1.rows[2].cells[0].text = "Piyush Kandhari"
    t1.rows[2].cells[1].text = "22"
    t1.rows[2].cells[2].text = "D12A"
    t1.rows[2].cells[3].text = "2024.piyush.kandhari@ves.ac.in"
    style_table(t1, [Inches(1.8), Inches(0.8), Inches(1.2), Inches(2.7)], header_bg="8B1E1E")

    p_bot = doc.add_paragraph()
    p_bot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_bot.paragraph_format.space_before = Pt(16)
    r_b1 = p_bot.add_run("Department of Computer Engineering\n")
    r_b1.font.bold = True
    r_b1.font.size = Pt(11)
    r_b1.font.color.rgb = RGBColor(27, 54, 93)
    r_b2 = p_bot.add_run("Academic Year: 2026–2027")
    r_b2.font.bold = True
    r_b2.font.size = Pt(10.5)

    doc.add_page_break()

def render_page_2(doc):
    # Table of Contents
    t_idx = doc.add_table(rows=16, cols=2)
    t_idx.rows[0].cells[0].text = "Chapter"
    t_idx.rows[0].cells[1].text = "Title"

    chapters = [
        ("Chapter 1", "Executive Summary & Abstract\n1.1 Academic Project Objectives"),
        ("Chapter 2", "System Architecture & Component Decomposition\n2.1 Tier Breakdown and Responsibilities\n2.2 Docker Deployment & Container Network Wiring"),
        ("Chapter 3", "Technology Stack & Host Environment Wiring"),
        ("Chapter 4", "Practical Implementation & System Verification\n4.1 Project Introduction & Requirements Verification\n4.2 System Architecture & Data Flow Inspection\n4.3 Development Environment Preparation\n4.4 Project Configuration & Environment Setup\n4.5 Docker Build & Cluster Startup\n4.6 Service Health Verification & Dashboard\n4.7–4.20 Authentication, Outbox, Pub/Sub, Elastic Scaling, Chaos, Testing, Shutdown"),
        ("Chapter 5", "Authoritative REST & WebSocket API Specification"),
        ("Chapter 6", "Comprehensive Troubleshooting Manual (18 Genuine Issues)"),
        ("Chapter 7", "Requirement Traceability Matrix (REQ-01 to REQ-27)"),
        ("Chapter 8", "Comprehensive University Viva-Voce Examination Guide\n8.1 Section A: 50 Core Technical & Distributed Systems Q&As\n8.2 Section B: 20 Architectural & Implementation Invariant Q&As\n8.3 Section C: 10 Complex Edge-Case Failure Scenarios"),
        ("Chapter 9", "Limitations, CAP & PACELC Trade-Offs & Future Scope"),
        ("Chapter 10", "Project Conclusion & Academic References")
    ]
    for i, (ch, tit) in enumerate(chapters):
        t_idx.rows[i+1].cells[0].text = ch
        t_idx.rows[i+1].cells[1].text = tit
        t_idx.rows[i+1].cells[0].paragraphs[0].runs[0].font.bold = True
    style_table(t_idx, [Inches(1.8), Inches(4.7)], header_bg="1B365D")

    doc.add_page_break()

def render_metadata_and_ch1(doc):
    add_heading_1(doc, "Document Control & Metadata")
    
    t_meta = doc.add_table(rows=10, cols=2)
    meta_rows = [
        ("Field", "Specification Details"),
        ("Project Title", "SOCKETSCALE — Fault-Tolerant Real-Time Pub/Sub WebSocket Gateway with Persistent Message History"),
        ("Document Type", "Comprehensive Academic Technical Cookbook & Operational Manual"),
        ("Version", "2.0 (Phase 6 Final Release — Expanded & Verified Edition)"),
        ("Academic Course", "Distributed Computing / System Design (Course Code: CSD501 / CSC601)"),
        ("Target Audience", "Students, Faculty Evaluators, Distributed Systems Engineers, Operators"),
        ("Primary Invariant", "Consistency First — Fail-Safe Transactional Persistence Before Delivery"),
        ("Authoritative Source", "PostgreSQL 16 Relational Storage + Transactional Outbox Engine"),
        ("Message Bus", "Redis 7 In-Memory Pub/Sub Real-Time Broadcast Backplane"),
        ("Submission Date", "12 November 2026")
    ]
    for i, (k, v) in enumerate(meta_rows):
        t_meta.rows[i].cells[0].text = k
        t_meta.rows[i].cells[1].text = v
        t_meta.rows[i].cells[0].paragraphs[0].runs[0].font.bold = True
    style_table(t_meta, [Inches(2.2), Inches(4.3)], header_bg="1B365D")

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    add_callout(
        doc,
        "Consistency first — fail-safe transactional persistence. A WebSocket message must never be reported as acknowledged or broadcast merely because an API Gateway process is reachable. Every state mutation must be atomically committed to PostgreSQL in the same database transaction as its outbox entry before asynchronous publication to Redis Pub/Sub.",
        title="[IMPORTANT INVARIANT]"
    )

    add_heading_1(doc, "Chapter 1 — Executive Summary & Abstract")
    add_para(
        doc,
        "SOCKETSCALE is an enterprise-grade, fault-tolerant distributed WebSocket gateway and real-time pub/sub platform engineered to resolve critical concurrency, cross-node fan-out, and message durability challenges in modern distributed collaborative systems. Built upon the architectural foundation of Nginx dynamic least-connection load balancing, asynchronous FastAPI gateway instances, and the Transactional Outbox Pattern, SOCKETSCALE guarantees absolute message persistence, sub-millisecond inter-gateway relay latency, and zero data loss under broker and gateway crash failures."
    )
    add_para(
        doc,
        "Unlike naive WebSocket implementations that drop messages when in-memory broker channels hiccup or gateway containers crash, SOCKETSCALE coordinates all state transitions across a decoupled PostgreSQL transactional engine. It combines an asynchronous outbox worker daemon with exponential retry policies, pattern-based Redis Pub/Sub broadcasting (`room:*`), dynamic elastic container provisioning via a Docker Fault Agent, and defense-in-depth security featuring Argon2id password hashing and HS256 JWT access control."
    )

    add_heading_2(doc, "1.1 Academic Project Objectives")
    objectives = [
        ("1. Elastic Multi-Node WebSocket Gateway:", " Deploy an elastic cluster of independent FastAPI instances balanced via Nginx with dynamic least_conn scheduling and sub-second failover."),
        ("2. Horizontal Real-Time Pub/Sub Relay:", " Synchronize message fan-out across disparate gateway nodes using Redis Pub/Sub with pattern-based routing (`room:*`)."),
        ("3. Guaranteed At-Least-Once Delivery:", " Implement the Transactional Outbox Pattern to atomically store messages and outbox events in PostgreSQL, eliminating dual-write loss."),
        ("4. Autonomous Outbox Drainage Worker:", " Build a background worker with exponential retry backoff to reliably publish pending outbox backlogs upon broker recovery."),
        ("5. Dynamic Elastic Node Scaling:", " Build Docker-integrated orchestration to provision and tear down gateway nodes on the fly with live Nginx upstream hot-reloading."),
        ("6. Chaos Engineering Simulation Lab:", " Implement web-based controls to intentionally inject faults (killing Gateways, Redis, PostgreSQL, Nginx) and measure automated self-healing."),
        ("7. High-Density Dynamic Benchmarking:", " Construct an integrated benchmarking suite measuring round-trip latency, concurrent throughput, and failure recovery times across varying workloads.")
    ]
    for pref, text in objectives:
        add_bullet(doc, text, bold_prefix=pref)

    doc.add_page_break()

def render_ch2_and_ch3(doc):
    add_heading_1(doc, "Chapter 2 — System Architecture & Component Decomposition")
    add_para(
        doc,
        "The SOCKETSCALE architecture is partitioned into four decoupled tiers: the Client Tier, the Edge Ingress Tier, the Distributed Gateway Cluster Tier, and the Persistence & Storage Tier. Each tier maintains clear responsibilities, independent failure domains, and strict isolation boundaries to maximize operational reliability and horizontal scalability."
    )

    add_heading_2(doc, "2.1 Tier Breakdown and Responsibilities")
    t_tiers = doc.add_table(rows=8, cols=4)
    tier_rows = [
        ("Tier / Component", "Internal Port", "Published Host Port", "Core Responsibilities"),
        ("Client Tier (React 18 SPA)", "80 (Nginx)", "8080 (Host)", "Single-page operator application providing live chat, admin telemetry, chaos controls, and benchmark graphs."),
        ("Edge Ingress (Nginx Proxy)", "80", "8080 (Host)", "Reverse proxy terminating HTTP/WS traffic, scheduling connections via least_conn, and hot-reloading upstreams."),
        ("FastAPI Gateway Cluster (A/B/C/D)", "8000", "Internal Network", "Asynchronous ASGI instances handling WebSocket sessions, JWT verification, and atomic PostgreSQL commits."),
        ("PostgreSQL Database", "5432", "5432 (Host)", "ACID relational storage for users, rooms, message histories, outbox events, and auditable system logs."),
        ("Transactional Outbox Worker", "Background Daemon", "Internal Network", "Asynchronous polling daemon tailing unpublished outbox records and relaying to Redis Pub/Sub."),
        ("Redis 7 Pub/Sub Broker", "6379", "6379 (Host)", "In-memory message backplane routing real-time room events across disparate gateway instances."),
        ("Docker Fault Agent", "8005", "Internal Network", "Chaos engineering controller manipulating container lifecycles and rewriting Nginx upstream configs.")
    ]
    for i, r in enumerate(tier_rows):
        for j, val in enumerate(r):
            t_tiers.rows[i].cells[j].text = val
    style_table(t_tiers, [Inches(1.8), Inches(1.1), Inches(1.1), Inches(2.5)], header_bg="1B365D")

    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    add_heading_2(doc, "2.2 Docker Deployment & Container Network Wiring")
    add_para(
        doc,
        "Docker Compose orchestrates the full multi-tier topology on a unified bridge network (`socketscale_default`). All internal inter-service traffic (Gateways to PostgreSQL, Gateways to Redis, Worker to PostgreSQL/Redis, Fault Agent to Docker daemon) is isolated from external client inspection. Only the Nginx reverse proxy publishes port 8080 to the host OS, serving as the sole secure ingress point."
    )

    add_heading_1(doc, "Chapter 3 — Technology Stack & Host Environment Wiring")
    add_para(
        doc,
        "SOCKETSCALE leverages a production-grade technology stack chosen specifically for deterministic asynchronous concurrency, low-latency network communication, and fault-tolerant message durability:"
    )

    t_tech = doc.add_table(rows=9, cols=4)
    tech_rows = [
        ("Subsystem / Layer", "Technology", "Version", "Technical Justification & Purpose"),
        ("Core Backend Framework", "Python / FastAPI", "3.10 / 0.115.5", "High-performance asynchronous ASGI web framework with native WebSocket support and coroutine event loop."),
        ("Asynchronous Database Driver", "AsyncPG / SQLAlchemy", "0.29 / 2.0.36", "Non-blocking PostgreSQL connection pooling for high-concurrency transactional commits."),
        ("Relational Database", "PostgreSQL (Alpine)", "16-alpine", "ACID-compliant relational database ensuring message durability and transactional outbox atomicity."),
        ("In-Memory Message Bus", "Redis (Alpine)", "7-alpine", "Sub-millisecond in-memory Pub/Sub broker enabling real-time cross-gateway broadcast synchronization."),
        ("Ingress Reverse Proxy", "Nginx (Alpine)", "1.27-alpine", "High-throughput edge proxy with least_conn load balancing and hot-reloadable upstream configuration."),
        ("Frontend Application", "React 18 / Vite", "18.3.1 / 6.1+", "Component-driven single page application with modern dashboard UI and real-time state management."),
        ("Security & Cryptography", "Passlib (Argon2) / JWT", "1.7.4 / 3.3.0", "Memory-hard password hashing and stateless HS256 JWT authentication tokens with role-based access."),
        ("Container Orchestration", "Docker & Docker Compose", "24+ / 2.20+", "Multi-stage reproducible microservice containerization with health probes and isolated networks.")
    ]
    for i, r in enumerate(tech_rows):
        for j, val in enumerate(r):
            t_tech.rows[i].cells[j].text = val
    style_table(t_tech, [Inches(1.8), Inches(1.3), Inches(1.0), Inches(2.4)], header_bg="1B365D")

    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    add_callout(
        doc,
        "The root docker-compose.yml file is the single source of truth for all published host ports. Nginx is published on host port 8080, PostgreSQL on port 5432, and Redis on port 6379. All gateway nodes (Gateway A, B, C, D) run on port 8000 internally and are reachable externally only through Nginx load balancing.",
        title="[NOTE] Authoritative Port Rule:"
    )

    doc.add_page_break()

print("Core data module ready.")
