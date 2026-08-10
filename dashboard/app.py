"""
Streamlit Dashboard for the KPITB Document Verification System.

Provides a user-friendly interface for uploading documents,
running verification, and viewing detailed reports.
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

import streamlit as st

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.document_schemas import DocumentType
from app.schemas.verification_schemas import VerificationStatus
from app.pipeline.orchestrator import PipelineOrchestrator
from app.rules.rule_engine import RuleEngine


# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="KPITB Document Validator",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    * { font-family: 'Inter', sans-serif; }
    
    .main-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        margin-bottom: 2rem;
        color: white;
    }
    .main-header h1 {
        margin: 0;
        font-size: 1.8rem;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    .main-header p {
        margin: 0.5rem 0 0 0;
        opacity: 0.8;
        font-size: 0.95rem;
    }

    .status-pass { 
        background: linear-gradient(135deg, #00b09b, #96c93d);
        color: white; padding: 4px 12px; border-radius: 8px; font-weight: 600; font-size: 0.85rem;
    }
    .status-fail { 
        background: linear-gradient(135deg, #eb3349, #f45c43);
        color: white; padding: 4px 12px; border-radius: 8px; font-weight: 600; font-size: 0.85rem;
    }
    .status-warning { 
        background: linear-gradient(135deg, #f7971e, #ffd200);
        color: #333; padding: 4px 12px; border-radius: 8px; font-weight: 600; font-size: 0.85rem;
    }
    .status-review { 
        background: linear-gradient(135deg, #667eea, #764ba2);
        color: white; padding: 4px 12px; border-radius: 8px; font-weight: 600; font-size: 0.85rem;
    }

    .metric-card {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
    }
    .metric-card h3 { font-size: 2rem; margin: 0; font-weight: 700; }
    .metric-card p { font-size: 0.85rem; color: #666; margin: 0.3rem 0 0 0; }

    .rule-row {
        background: #fff;
        border: 1px solid #eee;
        border-radius: 10px;
        padding: 0.8rem 1.2rem;
        margin-bottom: 0.5rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.6rem 2rem;
        font-weight: 600;
        font-size: 1rem;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
    }
</style>
""", unsafe_allow_html=True)


def get_status_badge(status_val):
    """Return an HTML badge for a verification status."""
    if isinstance(status_val, VerificationStatus):
        status_str = status_val.value
    else:
        status_str = str(status_val)
    
    css_class = {
        "PASS": "status-pass",
        "FAIL": "status-fail",
        "WARNING": "status-warning",
        "MANUAL_REVIEW": "status-review",
        "REJECTED": "status-fail"
    }.get(status_str, "status-review")
    
    label = status_str.replace("_", " ")
    return f'<span class="{css_class}">{label}</span>'


def render_header():
    st.markdown("""
    <div class="main-header">
        <h1>🔍 KPITB Document Verification System</h1>
        <p>AI-assisted financial document validation for Sub-Biller Onboarding</p>
    </div>
    """, unsafe_allow_html=True)


def render_sidebar():
    with st.sidebar:
        st.markdown("### ⚙️ Configuration")
        st.markdown("---")
        
        mode = st.radio(
            "Verification Mode",
            ["📄 Single Document", "📦 Full Package"],
            index=0
        )
        
        st.markdown("---")
        st.markdown("### 📊 System Status")
        st.success("✅ Pipeline Ready")
        st.info("🧠 Rule Engine: 5 rules loaded")
        st.markdown("---")
        st.caption(f"v0.1.0 • {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
    return mode


def render_single_upload():
    """Render the single document upload and verification UI."""
    st.markdown("### 📄 Single Document Verification")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_file = st.file_uploader(
            "Upload a document (PDF or Image)",
            type=["pdf", "png", "jpg", "jpeg"],
            key="single_upload"
        )
    
    with col2:
        doc_type_options = {dt.name.replace("_", " ").title(): dt for dt in DocumentType}
        selected_type = st.selectbox(
            "Document Type",
            options=list(doc_type_options.keys()),
            key="single_type"
        )
        doc_type = doc_type_options[selected_type]
    
    if uploaded_file and st.button("🚀 Run Verification", key="btn_single"):
        with st.spinner("Processing document..."):
            # Save temp file
            temp_dir = Path("temp_uploads")
            temp_dir.mkdir(exist_ok=True)
            temp_path = temp_dir / uploaded_file.name
            
            try:
                with open(temp_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                orchestrator = PipelineOrchestrator()
                engine = RuleEngine()
                
                extracted = orchestrator.process_document(temp_path, doc_type)
                result = engine.verify_document(extracted)
                
                # ── Display Results ──
                st.markdown("---")
                st.markdown(f"### Results: {uploaded_file.name}")
                st.markdown(f"**Overall Status:** {get_status_badge(result.overall_status)}", unsafe_allow_html=True)
                
                # Metrics row
                m1, m2, m3, m4 = st.columns(4)
                with m1:
                    st.markdown(f"""<div class="metric-card">
                        <h3 style="color: #00b09b;">{result.pass_count}</h3><p>✅ Passed</p>
                    </div>""", unsafe_allow_html=True)
                with m2:
                    st.markdown(f"""<div class="metric-card">
                        <h3 style="color: #eb3349;">{result.fail_count}</h3><p>❌ Failed</p>
                    </div>""", unsafe_allow_html=True)
                with m3:
                    st.markdown(f"""<div class="metric-card">
                        <h3 style="color: #f7971e;">{result.warning_count}</h3><p>⚠️ Warnings</p>
                    </div>""", unsafe_allow_html=True)
                with m4:
                    st.markdown(f"""<div class="metric-card">
                        <h3 style="color: #667eea;">{result.manual_review_count}</h3><p>👁️ Manual Review</p>
                    </div>""", unsafe_allow_html=True)
                
                # Rule details
                st.markdown("#### Detailed Rule Results")
                for rule_result in result.rule_results:
                    badge = get_status_badge(rule_result.status)
                    st.markdown(f"""
                    <div class="rule-row">
                        <div>
                            <strong>{rule_result.rule_name}</strong>
                            <br><small style="color: #888;">{rule_result.message}</small>
                        </div>
                        <div>{badge}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
            except Exception as e:
                st.error(f"❌ Error processing document: {e}")
            finally:
                if temp_path.exists():
                    temp_path.unlink()


def render_package_upload():
    """Render the full package upload and verification UI."""
    st.markdown("### 📦 Full Package Verification")
    st.info("Upload multiple documents that form a complete sub-biller onboarding package.")
    
    case_id = st.text_input("Case ID (optional)", placeholder="Auto-generated if empty")
    
    # Dynamic file upload slots
    num_docs = st.number_input("Number of documents", min_value=1, max_value=11, value=2)
    
    uploads = []
    for i in range(num_docs):
        col1, col2 = st.columns([2, 1])
        with col1:
            f = st.file_uploader(f"Document {i+1}", type=["pdf", "png", "jpg", "jpeg"], key=f"pkg_file_{i}")
        with col2:
            doc_type_options = {dt.name.replace("_", " ").title(): dt for dt in DocumentType}
            t = st.selectbox(f"Type for Doc {i+1}", options=list(doc_type_options.keys()), key=f"pkg_type_{i}")
            dt = doc_type_options[t]
        uploads.append((f, dt))
    
    if st.button("🚀 Run Full Verification", key="btn_package"):
        # Check all files uploaded
        valid_uploads = [(f, dt) for f, dt in uploads if f is not None]
        if not valid_uploads:
            st.warning("Please upload at least one file.")
            return
            
        with st.spinner("Processing package..."):
            temp_dir = Path("temp_uploads")
            temp_dir.mkdir(exist_ok=True)
            saved_paths = []
            
            try:
                orchestrator = PipelineOrchestrator()
                engine = RuleEngine()
                extracted_docs = []
                
                for uploaded_file, doc_type in valid_uploads:
                    temp_path = temp_dir / uploaded_file.name
                    with open(temp_path, "wb") as fp:
                        fp.write(uploaded_file.getbuffer())
                    saved_paths.append(temp_path)
                    
                    extracted = orchestrator.process_document(temp_path, doc_type)
                    extracted_docs.append(extracted)
                
                cid = case_id if case_id else f"CASE-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                report = engine.generate_verification_report(cid, extracted_docs)
                report.verified_at = datetime.now()
                
                # ── Display Report ──
                st.markdown("---")
                st.markdown(f"### 📋 Verification Report: `{cid}`")
                st.markdown(f"**Overall Verdict:** {get_status_badge(report.overall_status)}", unsafe_allow_html=True)
                
                # Summary metrics
                m1, m2, m3, m4, m5 = st.columns(5)
                with m1:
                    st.metric("Total Rules", report.total_rules_checked)
                with m2:
                    st.metric("✅ Passed", report.total_pass)
                with m3:
                    st.metric("❌ Failed", report.total_fail)
                with m4:
                    st.metric("⚠️ Warnings", report.total_warnings)
                with m5:
                    st.metric("👁️ Review", report.total_manual_review)
                
                # Per-document results
                st.markdown("#### Per-Document Results")
                for doc_result in report.document_results:
                    with st.expander(f"📄 {doc_result.file_name} — {get_status_badge(doc_result.overall_status)}", expanded=False):
                        for rr in doc_result.rule_results:
                            badge = get_status_badge(rr.status)
                            st.markdown(f"""
                            <div class="rule-row">
                                <div><strong>{rr.rule_name}</strong><br><small>{rr.message}</small></div>
                                <div>{badge}</div>
                            </div>
                            """, unsafe_allow_html=True)
                
                # Cross-document checks
                if report.cross_document_checks:
                    st.markdown("#### 🔗 Cross-Document Consistency Checks")
                    for check in report.cross_document_checks:
                        badge = get_status_badge(check.status)
                        icon = "✅" if check.is_consistent else "❌"
                        with st.expander(f"{icon} {check.field_name.upper()} — {badge}", expanded=not check.is_consistent):
                            st.markdown(f"**Message:** {check.message}")
                            st.markdown("**Values Found:**")
                            for doc_name, val in check.values_found.items():
                                st.markdown(f"- `{doc_name}`: **{val}**")
                
                # Download report as JSON
                report_json = report.model_dump_json(indent=2)
                st.download_button(
                    label="📥 Download Report (JSON)",
                    data=report_json,
                    file_name=f"verification_report_{cid}.json",
                    mime="application/json"
                )
                
            except Exception as e:
                st.error(f"❌ Error processing package: {e}")
            finally:
                for p in saved_paths:
                    if p.exists():
                        p.unlink()


# ── Main App ──────────────────────────────────────────────────────────────
def main():
    render_header()
    mode = render_sidebar()
    
    if "Single" in mode:
        render_single_upload()
    else:
        render_package_upload()


if __name__ == "__main__":
    main()
