import uuid
from dotenv import load_dotenv

from models.main_agent import MainAgent

WEEKLY_INSTRUCTIONS = """
You are running the weekly audit of the user's portfolio repository.

Goals
- Make ONLY minimal, high-impact improvements.
- Only change things that align with the repo's stated future plans/roadmap (as described in the portfolio pages/readme/case studies).
- Prefer clarity and simplicity over features. Avoid refactors unless they remove obvious confusion or breakage.
- Keep changes small: 1 to 3 focused improvements maximum.

Workflow
1) Identify the portfolio repo (or use the configured default).
2) Scan for “future plans”, “roadmap”, “next steps”, “TODO”, “planned”, etc. Capture the intended direction.
3) Find the top 1 to 3 issues that most block that direction:
   - broken links / broken builds
   - missing or unclear content where the roadmap expects it
   - confusing navigation or naming that prevents understanding
   - small code/docs cleanup that improves maintainability
4) Propose changes before writing:
   - Describe each change in 1 to 2 sentences.
   - Explain why it supports the roadmap.
5) Apply changes with minimal edits and no style churn.
6) Summarize what you changed and what you intentionally did NOT change.

Output format (SAVE THIS INTO MEMORY EXACTLY)
{
  "type": "weekly_portfolio_audit",
  "run_id": "<uuid>",
  "repo": "<owner/repo or local path>",
  "date": "<YYYY-MM-DD>",
  "roadmap_signals": [
    {"source": "<file>", "excerpt": "<short excerpt>"}
  ],
  "changes": [
    {
      "title": "<short change title>",
      "files": ["<file1>", "<file2>"],
      "summary": "<what changed>",
      "reason": "<how it supports roadmap>",
      "risk": "<low/medium/high>"
    }
  ],
  "skipped": [
    {"item": "<thing you chose not to change>", "reason": "<why>"}
  ],
  "next_week_suggestions": [
    "<1-3 tiny suggestions max>"
  ]
}

Constraints
- Do not invent plans. Only use plans found in the repo.
- Do not add new dependencies unless absolutely required for a fix.
- Do not do large rewrites. Keep diffs small and readable.
"""

def main():
    load_dotenv()

    thread_id = str(uuid.uuid4())
    print("[Debug] Thread Id:", thread_id)

    agent = MainAgent()
    print("[Debug] Agent created. Messaging Agent now . . .")

    agent.message(user_msg=WEEKLY_INSTRUCTIONS, thread_id=thread_id)
    print("[Debug] Message complete.")

if __name__ == "__main__":
    main()