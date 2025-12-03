
import vertexai
from main_agent.agent import root_agent
from vertexai import agent_engines
from vertexai.preview import reasoning_engines

vertexai.init(project="[SEU_PROJETO]", staging_bucket="gs://000-staging-adk")

app = reasoning_engines.AdkApp(
    agent=root_agent,
    enable_tracing=True,
)

remote_app = agent_engines.create(
    display_name="BB Cast",
    agent_engine=app,
    requirements=[
        "google-cloud-aiplatform[adk,agent_engines]",
    ],
    extra_packages=["main_agent"],
)