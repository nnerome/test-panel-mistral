"""Agents SDK definitions: the FAQ agent, the read-only account agent and the action agent.

The rule that shapes every tool here: the model proposes, the application decides. Tool
schemas contain NO identity parameter — the session's customer id reaches the tool only
through `BankSessionInput` (a session input the model never sees), and the server resolves
masked labels to real ids inside the tool, after an ownership check."""
