from dotenv import load_dotenv

from models.main_agent import MainAgent

def main():
    agent = MainAgent()
    result = agent.message(user_msg="Are your tools working?")
    print(result)

if __name__ == "__main__":
    load_dotenv()
    main()