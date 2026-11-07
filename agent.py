import os
import time
from dotenv import load_dotenv  # NEW: reads .env file
from google import genai  # Google's official Gemini SDK (no LiteLLM)
from google.genai import types
from google.genai import errors as genai_errors
from tools import list_files, read_file, write_file, run_python, TOOLS_SCHEMA

# ============================================================
# STEP 1 — API Key (.env loader)
# ============================================================
# Old (Ollama): no key needed, model ran on your machine.
# New (Gemini): key tells Google who you are and which account pays.
# Get free key: https://aistudio.google.com -> Get API key -> Create key
# We load it from .env so you don't type it every terminal.
#   1. Create file ".env" in this folder with:
#        GEMINI_API_KEY=your_key_here
#   2. Never commit .env to git (see .gitignore)
load_dotenv()  # reads .env in current folder into os.environ
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise SystemExit(
        "Missing GEMINI_API_KEY.\n"
        "1. Go to https://aistudio.google.com and click 'Get API key'\n"
        "2. Create a key, copy it\n"
        "3. Create file .env in this folder with:  GEMINI_API_KEY=your_key_here\n"
        "4. Then run: python agent.py"
    )

# STEP 2 — Create the client (one-time setup)
# Old (Ollama): no client needed.
# New (Gemini): client holds your key and talks to Google's servers.
client = genai.Client(api_key=api_key)

tools = [list_files, read_file, write_file, run_python]
tool_obj = types.Tool(function_declarations=TOOLS_SCHEMA)

# We keep it in Gemini's own format now:
# {"role": "user"/"model", "parts": [...]}
# Old Ollama format had "system" role. Gemini wants system
# instructions separated — we pass them in GenerateContentConfig below.
messages = [
    types.Content(
        role="user",
        parts=[types.Part(text="Fix the bug in this Python project.")]
    )
]

available = {
    "list_files": list_files,
    "read_file": read_file,
    "write_file": write_file,
    "run_python": run_python
}

# ============================================================
# STEP 3 — THE AGENT LOOP
# ============================================================
# Old (Ollama):
#   response = chat(model="qwen3", messages=messages, tools=tools)
#   tool_calls: response.message.tool_calls
#   result:     {"role": "tool", "tool_name": ..., "content": ...}
#
# New (Google Gemini native SDK):
#   response = client.models.generate_content(model=..., contents=..., config=...)
#   tool_calls: response.candidates[0].content.parts (look for .function_call)
#   result:     send back a Content with role="user" + Part(function_response=...)
#   ^ tool_call_id included inside FunctionResponse.
while True:
    print("Calling Gemini...", flush=True)

    # STEP 4 — THE CALL
    # "gemini-2.5-flash" = fast + good at tools.
    # Other options: gemini-2.5-pro (smarter, slower), gemini-2.0-flash (older)
    # Retry on 503 - Google's servers get busy, it's normal.
    # Wait 5s, 10s, 20s... up to 5 tries.
    response = None
    for attempt in range(1, 6):
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=messages,
                config=types.GenerateContentConfig(
                    system_instruction="""You are a coding agent.
Work only inside the provided workspace.
Inspect files before modifying them.
After making changes, run relevant code or tests.
If execution fails, inspect the error and fix the problem.
Do not claim success until you have verified the result.""",
                    tools=[tool_obj],
                ),
            )
            break
        except genai_errors.ServerError:
            wait = min(5 * attempt, 30)
            print(f"Gemini 503 (high demand), retrying in {wait}s (attempt {attempt}/5)...", flush=True)
            time.sleep(wait)
            if attempt == 5:
                raise
        except genai_errors.ClientError as e:
            # 429 = free-tier rate limit hit. Too many requests / minute.
            if e.code == 429:
                if attempt == 5:
                    raise
                wait = 35
                print(f"Gemini 429 (rate limit, free tier), waiting {wait}s (attempt {attempt}/5)...", flush=True)
                time.sleep(wait)
            else:
                raise
        time.sleep(3)  # small pause between loop iterations to stay under API quota
    print("Received response.", flush=True)

    candidate = response.candidates[0].content
    messages.append(candidate)

    # Find function calls in the parts
    function_calls = [p.function_call for p in candidate.parts if p.function_call]
    if not function_calls:
        print(response.text)
        break

    # STEP 5 — RUN EACH TOOL CALL AND BUILD THE RESPONSE
    for call in function_calls:
        function = call.name
        # Old (Ollama): arguments was a dict already -> **arguments
        # New (Gemini): arguments is already a dict too (call.args)
        arguments = dict(call.args or {})

        if function in available:
            result = str(available[function](**arguments))
        else:
            result = "Unknown tool"
            print(f"Unknown tool: {function}", flush=True)

        # Send back each result as a user turn with a function_response part.
        # Gemini matches it to the call via "id" (call.id).
        messages.append(
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=call.id,
                            name=function,
                            response={"result": result},
                        )
                    )
                ],
            )
        )
