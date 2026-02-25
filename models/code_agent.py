from openai import OpenAI

from langchain_core.tools import tool

@tool
def message_code_agent(agent_msg: str) -> str:
    """
    Agent specific to writing code. Input prompt of what code is to be written. Output is str. 
    """
    client = OpenAI()

    response = client.responses.create(
        model="gpt-5-codex",
        input=agent_msg
    )
    return response.output_text