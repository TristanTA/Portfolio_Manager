import uuid
from dotenv import load_dotenv

from models.main_agent import MainAgent

WEEKLY_INSTRUCTIONS = """
You are running the weekly audit of the user's portfolio repository.

Goals
- Make ONLY minimal, high-impact improvements.
- Only change things that align with the repo's stated future plans/roadmap (portfolio pages/readme/case studies).
- Prefer clarity and simplicity over features. Avoid refactors unless they remove obvious confusion or breakage.
- Keep changes small: 1 to 3 focused improvements maximum.
- Keep code extremely simple and straightforward. Less is better. We can improve robustness later.

Workflow
1) Identify the portfolio repo (or use the configured default).
2) Scan for “future plans”, “roadmap”, “next steps”, “TODO”, “planned”, etc. Capture the intended direction.
3) Choose the top 1 to 3 issues that most block that direction:
   - broken links / broken builds
   - missing or unclear content where the roadmap expects it
   - confusing navigation or naming that prevents understanding
   - small code/docs cleanup that improves maintainability
4) Convert each suggested change into an independent job with its own job_id (one job per idea).
5) Save all jobs + roadmap_signals to memory using the output format below.
6) Send the full proposal to the user via Telegram:
   - include run_id
   - list each job_id with title + 1-2 sentence summary + affected files + risk
   - instructions for approval:
     - /approve <job_id> <optional notes>
     - /reject <job_id> <optional notes>
     - user may send multiple approvals in one message
7) After sending the proposal and saving to memory, call telegram_get_response to wait for approval.
8) Parse the Telegram response:
   - extract approved job_ids and optional notes per job_id
   - ignore rejected job_ids
9) For each approved job_id:
   - implement only that job
   - incorporate the user notes
   - keep diffs minimal and readable
   - verify that the repo will run and operate normally
   - fix any errors or issues
   - keep things simple and minimal
   - create a PR (1 PR per job_id)
   - send a Telegram message with the PR link + what changed
10) If no jobs are approved before timeout, do nothing else.

Output format (SAVE THIS INTO MEMORY EXACTLY)
{
  "type": "weekly_portfolio_audit",
  "run_id": "<uuid>",
  "repo": "<owner/repo or local path>",
  "date": "<YYYY-MM-DD>",
  "roadmap_signals": [
    {"source": "<file>", "excerpt": "<short excerpt>"}
  ],
  "jobs": [
    {
      "job_id": "<uuid or short id>",
      "title": "<short change title>",
      "files": ["<file1>", "<file2>"],
      "summary": "<1-2 sentences: what will change>",
      "reason": "<how it supports roadmap>",
      "risk": "<low/medium/high>"
    }
  ],
  "skipped": [
    {"item": "<thing you chose not to change>", "reason": "<why>"}
  ]
}

Constraints
- Do not invent plans. Only use plans found in the repo.
- Do not add new dependencies unless absolutely required for a fix.
- Do not do large rewrites. Keep diffs small and readable.
- Do not bundle jobs: one PR per approved job_id only.
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