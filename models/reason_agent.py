from openai import OpenAI

from langchain_core.tools import tool

@tool
def message_reasoning_agent(agent_msg: str) -> str:
    """
    Agent specific to reasoning and planning. Input prompt of to reason on. Output is str. 
    """
    client = OpenAI()

    response = client.responses.create(
        model="gpt-5",
        input=agent_msg
    )
    return response.output_text
    