# Gmail Inbox Agent

This agent is intentionally conservative:

- Default to dry-run.
- Never delete, spam, reply to, or forward messages.
- Archive only by removing the Gmail `INBOX` label.
- Process only messages currently in the inbox.
- Skip anything already marked with `AI Reviewed` or present in local SQLite memory.
