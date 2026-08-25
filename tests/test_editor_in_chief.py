"""Construction tests for the Editor-in-Chief deep-agent assembly.

These build the agent with a real (proxy-bound) chat model but never invoke it,
so they run offline — constructing a ChatOpenAI / create_deep_agent does no
network I/O. The live agent loop is exercised by the end-to-end run, not here.
"""

from langgraph.graph.state import CompiledStateGraph

from content_pipeline.agent.editor_in_chief import build_brain, build_editor_in_chief


def test_build_brain_returns_proxy_bound_model():
    llm = build_brain("dgx/vllm/qwen3.8-27b-nvfp4")
    assert llm.model_name == "dgx/vllm/qwen3.8-27b-nvfp4"


def test_build_editor_in_chief_compiles_a_graph():
    agent = build_editor_in_chief(model=build_brain("dgx/vllm/qwen3.8-27b-nvfp4"))
    # create_deep_agent returns a compiled LangGraph we can invoke.
    assert isinstance(agent, CompiledStateGraph)
    assert hasattr(agent, "invoke")


def test_build_editor_in_chief_accepts_a_checkpointer():
    from langgraph.checkpoint.memory import InMemorySaver

    agent = build_editor_in_chief(
        model=build_brain("dgx/vllm/qwen3.8-27b-nvfp4"),
        checkpointer=InMemorySaver(),
    )
    assert isinstance(agent, CompiledStateGraph)
