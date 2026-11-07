# AI Coding Agent Project

## Status: Working with Gemini

- Ollama with `qwen3` was the original local setup, then migrated to Google Gemini (`gemini-3.6-flash`) for speed
- Agent successfully fixes `workspace/calculator.py` and prints `Average: 25.0`

## Project Structure

```
my_coding_agent/
├── agent.py          # Main agent loop (Gemini tool-calling loop)
├── tools.py          # 4 workspace tools + Gemini tool schemas
├── requirements.txt  # pip dependencies (google-genai, python-dotenv)
├── .env              # GEMINI_API_KEY (never commit - see .gitignore)
├── .gitignore        # Blocks .env and __pycache__
└── workspace/
    └── calculator.py # Sample buggy file the agent fixes
```

## Setup (Gemini)

### 1. Get a free API key (1 minute)

1. Go to https://aistudio.google.com
2. Click **"Get API key"** → **"Create API key"**
3. Copy the key

### 2. Create `.env` file

Create a file named `.env` in the project root (next to `agent.py`):

```ini
GEMINI_API_KEY=your_key_here
```

> The key is loaded automatically at startup. Never commit `.env` to git — `.gitignore` already blocks it. If you paste a key in chat or a screenshot, treat it as compromised and generate a new one at aistudio.google.com.

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Run the agent

```powershell
python agent.py
```

That's it — no need to set `$env:GEMINI_API_KEY` in the terminal anymore.

## tools.py — The 4 Tools

| Tool | What it does |
|------|--------------|
| `list_files()` | List all files in `workspace/` |
| `read_file(path)` | Read a file safely (blocks paths outside `workspace/`) |
| `write_file(path, content)` | Write/overwrite a file safely |
| `run_python(path)` | Run a `.py` file with a 10s timeout, returns stdout/stderr |

`TOOLS_SCHEMA` (in `tools.py`) declares these tools for Gemini in Google's `FunctionDeclaration` format. Gemini only sees this schema — it doesn't see your Python code — and uses it to decide which tool to call and what arguments to send.

## agent.py — How the Loop Works

1. **Load key:** `load_dotenv()` reads `.env` → `os.getenv("GEMINI_API_KEY")`
2. **Create client:** `genai.Client(api_key=api_key)` — one-time setup
3. **Start loop:**
   - Call `client.models.generate_content(...)` with the conversation messages
   - If the model returns function calls, run the matching Python tool
   - Send the tool result back as a `FunctionResponse` (matches the call by `id`)
   - Repeat until the model replies with plain text (no tool call)

## Migration Log: Ollama → Gemini

### Why switch from Ollama?

- Local `qwen3` takes 5-15s per call (CPU/GPU inference on your machine)
- Hosted Gemini is ~0.3-1s per call (Google's infrastructure)
- No model downloads, no VRAM, no `ollama serve`

### What changed

| Area | Before (Ollama) | After (Gemini) |
|------|----------------|----------------|
| Import | `from ollama import chat` | `from google import genai` |
| Model | `model="qwen3"` | `model="gemini-3.6-flash"` |
| Tool passing | `tools=[list_files, ...]` (functions) | `TOOLS_SCHEMA` with `FunctionDeclaration` objects |
| System prompt | `{"role": "system", ...}` in messages | `system_instruction=...` in `GenerateContentConfig` |
| Messages | `{"role": "user", "content": "..."}` | `types.Content(role="user", parts=[types.Part(text=...)])` |
| Tool results | `{"role": "tool", "tool_name": ..., "content": ...}` | `types.Part(function_response=types.FunctionResponse(id=..., name=..., response={"result": ...}))` |
| Arguments | Already a dict (`**arguments`) | Also a dict (`dict(call.args)`), no `json.loads` needed |
| Client | None | `genai.Client(api_key=...)` created once |

Core loop is identical: ask model → if it wants a tool, run it → give result back → repeat. Only the API plumbing changed.

### Why NOT LiteLLM?

LiteLLM is a wrapper that talks to 100+ providers, but it pulls in C-compiled packages (`pyyaml`, `pydantic-core`, `tiktoken`, `aiohttp`) that have **no pre-built wheel for Python 3.15**. Pip tried to compile them and failed with "Microsoft Visual C++ 14.0 or greater is required". `google-genai` is pure Python and installs cleanly. Switch to LiteLLM later only if you need multi-provider support and downgrade to Python 3.11/3.12.

### Why NOT Google ADK?

ADK (Agent Development Kit) is a framework for building agents *on top of* Gemini — it's not a model. It's overkill for a 57-line tool loop. Only add it later if you want to deploy the agent as a service, add memory, or use multi-agent patterns.

### Why NOT Hugging Face?

Yes, HF hosts open models (Qwen, Llama) and you could call one via HF Inference Endpoints. But you'd still be calling a hosted API, not running it locally — same setup effort as Gemini, with less free-tier quota and more provider management. Gemini is simpler to start.

## Sample Test: calculator.py

The sample buggy file in `workspace/calculator.py`:

```python
def calculate_average(numbers):
    return sum(numbers) / len(number)  # BUG: 'number' should be 'numbers'

numbers = [10, 20, 30, 40]
print("Average:", calculate_average(numbers))
```

Run `python agent.py` — the agent should:
1. `list_files` → find `calculator.py`
2. `read_file` → spot the bug
3. `write_file` → fix `number` → `numbers`
4. `run_python` → verify `Average: 25.0`
5. Print a final summary

## Common Issues

**`Missing GEMINI_API_KEY`**
Create `.env` in the project root with `GEMINI_API_KEY=your_key_here`, then run `python agent.py` again.

**`404 NOT_FOUND` — model retired**
Google retires old models. The error message names the replacement. Copy the new model name into `agent.py` (one line). The current working model is `gemini-3.6-flash`.

**`503 UNAVAILABLE` — high demand**
Google's servers are overloaded — not a code bug. The agent retries automatically up to 5 times with backoff (5s, 10s, 15s, 20s, 25s). If it keeps failing, switch to `gemini-3.5-flash` or wait a minute.

**`429 RESOURCE_EXHAUSTED` — free-tier rate limit**
Free tier allows **5 requests per minute**. Your agent loop makes ~7 calls in < 5s, so a single run can hit the limit mid-loop. The agent retries automatically (waits 35s, up to 5 tries) and adds a 3s pause between iterations to stay under quota. If you hit this often:
- Wait 1 minute and rerun (quota resets per minute)
- Or add a billing method at `console.cloud.google.com` (lifts the free-tier limit)

**`Import "dotenv" / "google.genai" could not be resolved` (Pylance)**
VS Code can't see the packages yet. Run `pip install -r requirements.txt` in the same Python interpreter VS Code is using. If it persists, `Ctrl+Shift+P` → `Python: Select Interpreter` and pick that one.

**`Failed building wheel for pyyaml` / `Microsoft Visual C++ 14.0 required`**
You're on Python 3.15 and a package (usually via LiteLLM) has no pre-built binary. Either use `google-genai` (pure Python, no build) or downgrade to Python 3.11/3.12.

**Ollama not responding (old setup)**
- Make sure Ollama is running: `ollama serve` or open the Ollama app
- Check the model is pulled: `ollama list`

## Expected Output

When working correctly:

```
Calling Gemini...
Received response.
Calling Gemini...
Received response.
Calling Gemini...
Received response.
The bug in `calculator.py` has been fixed.

### Cause of Bug
...

### Solution
...Running `calculator.py` now outputs `Average: 25.0` without errors.
```

## Success Criteria

- [x] Create the project structure
- [x] Create `tools.py` with all 4 functions
- [x] Create `agent.py` with main loop
- [x] Add `calculator.py` with intentional bug
- [x] Run `python agent.py` and see agent fix the bug
- [x] Migrate from Ollama to Gemini
- [x] Add `.env` loader for the API key
- [x] Handle 503/429 errors with retries

## Notes

This project demonstrates an AI agent that can:
- Read and analyze code
- Fix bugs programmatically
- Execute and test its changes
- Learn from mistakes and iterate

Perfect for beginners learning about agent-based AI systems!
