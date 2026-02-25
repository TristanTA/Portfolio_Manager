from langchain.agents import create_agent

from models.code_agent import message_code_agent
from models.reason_agent import message_reasoning_agent

class AgentRouter:
    def __init__(self):
        self.agent = create_agent(
            model="gpt-5-nano",
            tools=[message_code_agent, message_reasoning_agent],
            system_prompt="You are an agentic router. Based on the agent message provided to you, choose the best tool."
        )

    def message(self, agent_msg: str) -> str:
        response = self.agent.invoke(agent_msg)
        return response