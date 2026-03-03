# 04 — Multi-Provider Setup

## The Core Insight

LangChain's ChatModel abstraction means every provider has the same interface:

```python
llm.invoke([HumanMessage(content="Hello")])  # Works for ALL of these:
# ChatAnthropic, ChatGoogleGenerativeAI, ChatOpenAI, ChatOllama...
```

This is what makes the comparator site possible. Same prompt template, same chain code,
same output parser — the only difference is which LLM object you put in the middle.

---

## Provider 1: Claude (Anthropic)

**Package:** `langchain-anthropic`
**Auth:** `ANTHROPIC_API_KEY` environment variable
**API Docs:** https://docs.anthropic.com/en/api

```python
from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(
    model="claude-3-5-sonnet-20241022",  # or claude-3-opus, claude-3-haiku
    api_key="sk-ant-...",                # or set ANTHROPIC_API_KEY env var
    temperature=0.8,
    max_tokens=1024,
    timeout=60,
    max_retries=3,
)
```

**Available models (early 2026):**

| Model                        | Speed | Cost  | Best for               |
|------------------------------|-------|-------|------------------------|
| claude-3-5-sonnet-20241022   | Fast  | Mid   | Creative writing ✓     |
| claude-3-5-haiku-20241022    | V.Fast| Low   | High volume tasks      |
| claude-opus-4-6              | Slow  | High  | Complex reasoning      |

**Claude's personality in the comparator:**
Claude tends to write longer, more structured responses with careful hedging.
It rarely breaks character. Great at following complex formatting instructions.

---

## Provider 2: Gemini (Google)

**Package:** `langchain-google-genai`
**Auth:** `GOOGLE_API_KEY` environment variable
**Get a free key:** https://aistudio.google.com/app/apikey

```python
from langchain_google_genai import ChatGoogleGenerativeAI

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",         # or gemini-1.5-pro, gemini-ultra
    google_api_key="AIza...",
    temperature=0.8,
    max_output_tokens=1024,
    # IMPORTANT: Gemini doesn't support a system role natively.
    # This setting prepends the system message as a human turn.
    convert_system_message_to_human=True,
    timeout=60,
    max_retries=3,
)
```

**Available models (early 2026):**

| Model               | Context  | Speed  | Best for               |
|---------------------|----------|--------|------------------------|
| gemini-2.0-flash    | 1M tokens| Fast   | General use ✓          |
| gemini-2.0-flash-lite | 1M     | V.Fast | Cost-sensitive tasks   |
| gemini-1.5-pro      | 2M tokens| Medium | Long document tasks    |

**Gemini's personality in the comparator:**
Gemini loves bullet points and structured markdown. It's enthusiastic and
tends to add helpful context you didn't ask for. Has a distinctly Google-ish
"here are 5 things to consider" energy.

**Important quirk:** `convert_system_message_to_human=True` is required because
Gemini's API doesn't have a native "system" role. Without it, LangChain raises an error.

---

## Provider 3: Local LLM via LM Studio

**Package:** `langchain-openai` (reused — the magic of the OpenAI-compatible spec)
**Auth:** No real key needed — LM Studio accepts any non-empty string
**Download LM Studio:** https://lmstudio.ai

```python
from langchain_openai import ChatOpenAI
import httpx

llm = ChatOpenAI(
    model="local-model",                       # Matches whatever model is loaded in LM Studio
    base_url="http://localhost:1234/v1",        # LM Studio's OpenAI-compatible server
    api_key="lm-studio",                        # Placeholder — LM Studio doesn't check this
    temperature=0.8,
    max_tokens=1024,
    max_retries=1,                             # Fail fast if server is down
    http_client=httpx.Client(verify=False),    # Localhost doesn't have a real SSL cert
)
```

**Setting up LM Studio:**

1. Download and install LM Studio from https://lmstudio.ai
2. In the "Discover" tab, search for and download a model:
   - `meta-llama/llama-3.2-3b-instruct` (fast, 2GB)
   - `microsoft/phi-4` (smart, 8GB)
   - `mistralai/mistral-7b-instruct` (balanced, 4GB)
3. Go to the "Local Server" tab
4. Select your model and click "Start Server"
5. Confirm it's running at `http://localhost:1234`

**The LM Studio model name:** Set `LM_STUDIO_MODEL` to the model identifier shown
in the server UI, or use `"local-model"` — LM Studio maps this to the loaded model.

**Local LLM personality in the comparator:**
Varies dramatically by model! Smaller models (3B params) struggle with complex
formatting instructions. Larger models (7B+) are surprisingly capable.
Response time is much slower than cloud APIs (seconds vs milliseconds).

---

## Swapping Ollama for LM Studio

If you use Ollama instead of LM Studio, change one environment variable:

```bash
# LM Studio (default)
LM_STUDIO_BASE_URL=http://localhost:1234/v1

# Ollama (same ChatOpenAI class, different port)
LM_STUDIO_BASE_URL=http://localhost:11434/v1
```

No code changes needed. This is LCEL's portability in action.

---

## Environment Variables Summary

```bash
# .env (local development — never commit this file)

ANTHROPIC_API_KEY=sk-ant-api03-...
GOOGLE_API_KEY=AIzaSy...

LM_STUDIO_BASE_URL=http://localhost:1234/v1
LM_STUDIO_MODEL=local-model
LM_STUDIO_API_KEY=lm-studio

AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=craicgpt-ie-production
CLOUDFRONT_DISTRIBUTION_ID=E1234...

WEATHER_LOCATION=Dublin
DRY_RUN=false
SKIP_LOCAL_LLM=false
```

---

## Provider Comparison Matrix

| Feature              | Claude (Anthropic) | Gemini (Google) | Local (LM Studio)    |
|----------------------|-------------------|-----------------|----------------------|
| Cost per run         | ~$0.02–0.10       | Free tier / low | FREE                 |
| Latency              | 1–3s              | 0.5–2s          | 3–30s (model-dependent) |
| JSON compliance      | Excellent         | Good            | Variable             |
| Instruction-following| Excellent         | Very good       | Varies by model size |
| Privacy              | Cloud (Anthropic) | Cloud (Google)  | 100% local           |
| Context window       | 200K tokens       | 1M+ tokens      | Model-dependent      |
| Setup complexity     | API key only      | API key only    | Install + run server |
