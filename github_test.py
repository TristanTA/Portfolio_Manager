from dotenv import load_dotenv

load_dotenv()

from tools.github_tools import github_list_tree, github_read_text_file, github_search_code, github_propose_change

print("List Tree:", github_list_tree(owner="tristanTA", repo="tristan-allen-portfolio"))
print("Read Text File:", github_read_text_file(owner="tristanTA", repo="tristan-allen-portfolio", path="index.md",))
print("Search Code:", github_search_code(query="Future Work", owner="TristanTA", repo="tristan-allen-portfolio"))
print("Propose Change:", github_propose_change(owner="TristanTA", repo="tristan-allen-portfolio", path="test_file.txt", content="This is a test change from the agent.\n", message="Test commit from automation", branch="main"))
print(
    "Propose Change (No SHA - Should Fail if file exists):",
    github_propose_change(
        owner="TristanTA",
        repo="tristan-allen-portfolio",
        path="index.md",  # Existing file → requires SHA
        content="Temporary test change\n",
        message="Test commit without SHA",
        branch="main",
        sha=""  # Explicitly empty
    )
)