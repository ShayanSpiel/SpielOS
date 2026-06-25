---
name: post
description: Dispatch a /post request. Reads content/current.md (written by the deterministic hook) and invokes @director.
---

# /post

The hook (tools/post-hook.py) already wrote:
- content/current.md (routing context)
- content/sessions/current.md (session artifact)

Read `{vault_root}/content/current.md`. Invoke @director.
