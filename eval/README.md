# eval/

This folder holds LLM-as-Judge evaluation artifacts for the CV Assistant AI
agents (CV Gap Analysis Agent, Mock Interview Agent).

- `datasets/` — synthetic CV/JD test cases used as evaluation input (added by agent_ai).
- `judges/` — LLM-as-Judge scripts that score agent outputs against a rubric (added by agent_ai).
- `results/` — output of evaluation runs (scores, transcripts). Only `.gitkeep` is tracked;
  generated result files are git-ignored since they can be re-run at any time.

Target from CLAUDE.md KPI table: LLM eval score >= 8.5/10.

Rule: all evaluation input data must be synthetic (fake CV/JD) — never real student data.
