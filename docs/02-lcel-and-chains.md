# 02 — LCEL and Chains

## What is LCEL?

LCEL (LangChain Expression Language) is LangChain's composition system.
It lets you build pipelines using the **pipe `|` operator**, similar to Unix pipes.

```python
chain = prompt | llm | output_parser
result = chain.invoke({"topic": "potatoes"})
```

When you call `chain.invoke()`, LangChain runs each stage in sequence:
1. `prompt.invoke(input)` → produces `ChatPromptValue` (list of messages)
2. `llm.invoke(messages)` → produces `AIMessage`
3. `output_parser.invoke(ai_message)` → produces your final value (e.g. a string or dict)

---

## Basic Chain Anatomy

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import StrOutputParser

# 1. Prompt Template — defines the message structure with {variable} slots
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a witty Irish newspaper editor."),
    ("human", "Write a headline about {topic}."),
])

# 2. LLM — any ChatModel (Claude, Gemini, ChatOpenAI...)
llm = ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0.8)

# 3. Output Parser — converts AIMessage → plain string
parser = StrOutputParser()

# 4. Chain — composed with |
chain = prompt | llm | parser

# 5. Invoke — pass variables, get result
headline = chain.invoke({"topic": "the price of tea in Dublin"})
# → "GOVERNMENT CONFIRMS TEA PRICES: NATION SOMEHOW SURPRISED"
```

---

## RunnableParallel — The Comparator's Core

`RunnableParallel` runs multiple chains with the **same input simultaneously**.
This is how the Craic Gazette sends identical prompts to all three providers at once.

```python
from langchain_core.runnables import RunnableParallel

# Build one chain per provider (same prompt, different LLM)
claude_chain = prompt | claude_llm | parser
gemini_chain = prompt | gemini_llm | parser
local_chain  = prompt | local_llm  | parser

# RunnableParallel runs all three with the same input
parallel = RunnableParallel(
    claude = claude_chain,
    gemini = gemini_chain,
    local  = local_chain,
)

# .invoke() blocks until ALL three have finished
results = parallel.invoke({"topic": "AI taking over Irish newspapers"})

# results is a dict with the output of each chain
print(results["claude"])   # → Claude's headline
print(results["gemini"])   # → Gemini's headline
print(results["local"])    # → Local LLM's headline
```

**Under the hood:** `RunnableParallel` uses Python's `ThreadPoolExecutor`.
All three LLM API calls happen in separate threads simultaneously.
Total time ≈ slowest provider, not sum of all providers.

---

## RunnableLambda — Wrapping Any Function

You can wrap any Python function as a Runnable to include it in a chain:

```python
from langchain_core.runnables import RunnableLambda

def add_metadata(text: str) -> dict:
    """Add provider metadata to the output."""
    return {"content": text, "generated_by": "pipeline_v2"}

# Wrap it for use in a chain
chain = prompt | llm | parser | RunnableLambda(add_metadata)
```

The Craic Gazette uses `RunnableLambda` to:
- Time each LLM call and attach `_latency_ms`
- Parse and validate JSON responses from LLMs
- Handle per-provider errors without crashing the pipeline

---

## Streaming

LCEL chains support streaming out of the box with `.stream()`:

```python
for chunk in chain.stream({"topic": "potatoes"}):
    print(chunk, end="", flush=True)
```

The Craic Gazette doesn't use streaming (the pipeline runs headlessly in CI),
but for an interactive web UI, streaming would let users see responses as they type.

---

## Async Support

All LCEL Runnables support async with `.ainvoke()` and `.astream()`:

```python
import asyncio

async def run():
    result = await chain.ainvoke({"topic": "potatoes"})
    return result

asyncio.run(run())
```

---

## Where to Find This in the Craic Gazette

| Concept            | File                                          |
|--------------------|-----------------------------------------------|
| Prompt templates   | `content_pipeline/prompts/templates.py`       |
| Claude chain       | `content_pipeline/providers/claude.py`        |
| Gemini chain       | `content_pipeline/providers/gemini.py`        |
| LM Studio chain    | `content_pipeline/providers/lmstudio.py`      |
| RunnableParallel   | `content_pipeline/chains/newspaper_chain.py`  |
| Output parsing     | `content_pipeline/chains/newspaper_chain.py`  |

---

## Key Takeaway

> The entire multi-provider comparator is powered by three lines of code:
>
> ```python
> parallel = RunnableParallel(claude=c, gemini=g, local=l)
> results = parallel.invoke(inputs)
> ```
>
> Everything else is configuration, prompts, and output formatting.
