import os

from dotenv import load_dotenv
from phoenix.otel import register
from openinference.instrumentation.openai import OpenAIInstrumentor

load_dotenv()

PROJECT_NAME = "agent-R"

tracer_provider = register(
    project_name=PROJECT_NAME,
    endpoint=os.environ["PHOENIX_COLLECTOR_ENDPOINT"],  # must end in /v1/traces
    batch=True,
)

OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)

tracer = tracer_provider.get_tracer(__name__)
