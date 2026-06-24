"""
OpenTelemetry -> Azure Monitor (Application Insights).
If APPLICATIONINSIGHTS_CONNECTION_STRING isn't set (local dev) the tracer is a no-op.

Spans:
  agent.run    one per question (tokens, cost, tools used, latency)
  agent.plan   the planning llm call
  agent.llm    each agent llm call
  tool.<name>  each tool call
FastAPI requests are traced automatically by configure_azure_monitor.
"""
import os
import json
from opentelemetry import trace

tracer = trace.get_tracer("filingspilot")
_setup_done = False


def setup():
    global _setup_done
    conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if _setup_done or not conn:
        return
    from azure.monitor.opentelemetry import configure_azure_monitor
    configure_azure_monitor(connection_string=conn)
    _setup_done = True
    print("telemetry -> application insights")


def traced_tool(name, fn, parent):
    """wraps a tool function so every call becomes a child span of agent.run"""
    def wrapper(*args, **kwargs):
        with tracer.start_as_current_span("tool." + name, context=parent) as span:
            span.set_attribute("tool.args", json.dumps(kwargs, default=str)[:500])
            try:
                result = fn(*args, **kwargs)
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                raise
            span.set_attribute("tool.result_chars", len(str(result)))
            span.set_attribute("tool.rejected", str(result).startswith(("Query rejected", "SQL error")))
            return result
    return wrapper


def record_llm_usage(span, msg):
    usage = getattr(msg, "usage_metadata", None) or {}
    span.set_attribute("llm.input_tokens", usage.get("input_tokens", 0))
    span.set_attribute("llm.output_tokens", usage.get("output_tokens", 0))
