# Package Managers

Use `uv run main.py`
Use `uv add <dependency>` to always get the latest version

Prefer `pnpm` instead of `npm` where possible.

# Static Code Analysis

To ensure code quality stays high and readable: Use strong types, code formatting, max-lines-per-file, and complexity detection. See: https://gist.github.com/gardner/22f2fb13cf2103f7a0197437dfa71bc8

## Workflow

- Make descriptive commits at reasonable intervals.
- Rely on the pre-commit hooks to run the checks, don't manually run the pre-commit checks. Ensure the pre-commit hooks are installed and working.
- Before picking up a GitHub Issue to work on: Review the issue, then review the existing code, then conduct any research to validate the contents of the issue or update the issue with a plan. Make sure to include a plain language explanation of "The Problem" that we're solving, the proposed plan to solve it, and any other options considered.
- When working on a GitHub Issue, create a new branch so we can submit a PR when it is ready.
- After submitting a PR, monitor the PR for any review comments. Use a subagent that with the muse-spark-1.3 model:
    - If there are review comments then please evaluate if any of them are actually real or relevant, and then resolve the important issues with a new commit and resolve the GitHub PR conversation with information about the resolution, or with a comment saying why it is not relevant. After pushing a new commit, monitor the PR for new review comments and continue the process.
    - You can work on other things while waiting for the PR review comments. Remember: pushing code also requests a review, so only push code that is ready for review.
- Keep the GitHub Project board up to date: https://github.com/users/gardner/projects/4

## Pre-push review

- `git push` runs the pre-push hook `scripts/pre-push-review.sh`, where headless Muse (`claude -p`) reviews the outgoing commits and writes any P0/P1/P2 findings to `ISSUES.md`, which blocks the push. Fix every real finding, delete `ISSUES.md`, commit, then push again for a fresh review. State why any finding is not relevant. Install the hook with `uv run pre-commit install`. Never bypass with `--no-verify`. If the review cannot run or findings cannot be fixed, stop and ask. NO FALLBACKS.

# IMPORTANT

- Use TDD "Red, green, refactor" where possible. WRITE THE FAILING TESTS FIRST.
- Optimize for code readability and long-term maintenance.
- Write simple yet powerful code.
- Keep things elegant.
- Please make descriptive commits at reasonable intervals.
- Conduct a code review at the end of a large work slice and resolve any issues identified.
- NO FALLBACKS: accurate results are important. If a system or process fails then we need to fix it. If you need help then stop and ask.

