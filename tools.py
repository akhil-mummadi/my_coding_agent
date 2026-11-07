from pathlib import Path
import subprocess
from google.genai import types

ROOT = Path("./workspace").resolve()

def list_files():
    """List all files in workspace directory"""
    return [
        str(p.relative_to(ROOT))
        for p in ROOT.rglob("*")
        if p.is_file()
    ]

def read_file(path):
    """Read file content with path validation"""
    target = (ROOT / path).resolve()
    if not target.is_relative_to(ROOT):
        raise ValueError("Access outside workspace is not allowed")
    return target.read_text()

def write_file(path, content):
    """Write content to file with path validation"""
    target = (ROOT / path).resolve()
    if not target.is_relative_to(ROOT):
        raise ValueError("Access outside workspace is not allowed")
    target.write_text(content)
    return f"Updated {path}"

def run_python(path):
    """Execute Python code with timeout protection"""
    target = (ROOT / path).resolve()
    if not target.is_relative_to(ROOT):
        raise ValueError("Access outside workspace is not allowed")

    try:
        result = subprocess.run(
            ["python", str(target)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )
        return {
            "return_code": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:]
        }
    except subprocess.TimeoutExpired:
        return {
            "return_code": -1,
            "stdout": "",
            "stderr": "Execution timed out."
        }

# ============================================================
# Tool declarations for Google Gemini (native SDK)
# ============================================================
# Why: Gemini does not see your Python code. It only sees this list.
# Each FunctionDeclaration says: name + description + params.
# Google's SDK uses its own types here - NOT OpenAI/LiteLLM format.
# Leave optional args as None when empty.
TOOLS_SCHEMA = [
    types.FunctionDeclaration(
        name="list_files",
        description="List all files in workspace directory",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={},
            required=[],
        ),
    ),
    types.FunctionDeclaration(
        name="read_file",
        description="Read file content with path validation",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "path": types.Schema(type=types.Type.STRING, description="Relative path inside workspace, e.g. calculator.py"),
            },
            required=["path"],
        ),
    ),
    types.FunctionDeclaration(
        name="write_file",
        description="Write content to file with path validation",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "path": types.Schema(type=types.Type.STRING, description="Relative path inside workspace"),
                "content": types.Schema(type=types.Type.STRING, description="Full file content to write"),
            },
            required=["path", "content"],
        ),
    ),
    types.FunctionDeclaration(
        name="run_python",
        description="Execute Python code with timeout protection",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "path": types.Schema(type=types.Type.STRING, description="Relative path to a .py file inside workspace"),
            },
            required=["path"],
        ),
    ),
]
