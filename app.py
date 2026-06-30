"""
Minimal Web UI for the Candidate Data Transformer.

This is a thin Streamlit wrapper over the core CLI pipeline.
It demonstrates how the pipeline's decoupled architecture allows
it to be easily embedded in different interfaces.
"""

import json
import shutil
import subprocess
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="Candidate Transformer",
    page_icon="🔄",
    layout="wide",
)

st.title("🔄 Multi-Source Candidate Data Transformer")
st.markdown(
    """
    **Upload messy candidate data (CSV, JSON, PDF Resumes, TXT notes)**
    and let the deterministic engine normalize, merge, score, and project it into clean JSON.
    """
)

# --- Sidebar Controls ---
st.sidebar.header("Configuration")

# Find available configs
config_dir = Path("sample_configs")
if config_dir.exists():
    config_files = list(config_dir.glob("*.json"))
    config_options = {f.name: str(f) for f in config_files}
else:
    config_options = {"default_config.json": "sample_configs/default_config.json"}

config_keys = list(config_options.keys())
default_index = config_keys.index("default_config.json") if "default_config.json" in config_keys else 0

selected_config = st.sidebar.selectbox(
    "Select Projection Config",
    options=config_keys,
    index=default_index,
    help="Determines the shape of the output JSON and how missing fields are handled.",
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    **Supported Formats:**
    - `.csv` (Recruiter exports)
    - `.json` (ATS data)
    - `.pdf` (Unstructured resumes)
    - `.txt` (Recruiter notes)
    """
)

# --- Main Workspace ---
uploaded_files = st.file_uploader(
    "Drop your source files here",
    accept_multiple_files=True,
    type=["csv", "json", "pdf", "txt"],
)

if st.button("Run Transformation Pipeline", type="primary", use_container_width=True):
    if not uploaded_files:
        st.error("Please upload at least one source file to process.")
    else:
        # Create a temporary workspace for this run
        run_dir = Path(".ui_workspace")
        input_dir = run_dir / "inputs"
        output_dir = run_dir / "outputs"
        
        # Clean previous run
        if run_dir.exists():
            shutil.rmtree(run_dir)
            
        input_dir.mkdir(parents=True)
        
        # Save uploaded files to the workspace
        for f in uploaded_files:
            file_path = input_dir / f.name
            with open(file_path, "wb") as out:
                out.write(f.getbuffer())
                
        # Define the CLI command
        config_path = config_options[selected_config]
        cmd = [
            "python", "main.py",
            "--input-dir", str(input_dir),
            "--config", config_path,
            "--output-dir", str(output_dir)
        ]
        
        with st.spinner("Pipeline is running..."):
            # Run the CLI via subprocess
            # This proves the UI is just a thin wrapper and the core logic
            # is entirely independent.
            result = subprocess.run(cmd, capture_output=True, text=True)
            
        if result.returncode == 0:
            st.success("✅ Pipeline completed successfully!")
            
            # Display CLI Logs
            with st.expander("View Pipeline Execution Logs"):
                st.code(result.stdout)
                
            # Display Output JSONs
            st.header("Projected Outputs")
            
            if output_dir.exists():
                out_files = sorted(list(output_dir.glob("*.json")))
                if out_files:
                    # Create tabs for each output file
                    tabs = st.tabs([f.name for f in out_files])
                    
                    for tab, f in zip(tabs, out_files):
                        with tab:
                            try:
                                data = json.loads(f.read_text(encoding="utf-8"))
                                # Show download button
                                st.download_button(
                                    label=f"Download {f.name}",
                                    data=json.dumps(data, indent=2),
                                    file_name=f.name,
                                    mime="application/json",
                                    key=f.name,
                                )
                                # Display JSON visually
                                st.json(data)
                            except Exception as e:
                                st.error(f"Failed to read output file: {e}")
                else:
                    st.warning("Pipeline succeeded but no output files were generated.")
        else:
            st.error("❌ Pipeline failed!")
            st.code(result.stdout + "\n" + result.stderr)
