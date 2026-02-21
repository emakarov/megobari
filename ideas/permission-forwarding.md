# Idea: Forward Permission Prompts to Telegram

## Problem

In `default` permission mode, Claude Code CLI blocks waiting for interactive
approval on file writes and bash commands. Since the Telegram bot is
non-interactive, these prompts have nowhere to go -- the agent just hangs.

Current workaround: use `acceptEdits` or `bypassPermissions` mode.

## Idea

Forward permission requests to Telegram as inline keyboard messages:

1. SDK yields a permission request event (e.g. "Write to bot.py?")
2. Bot sends a Telegram message with inline keyboard: [Approve] [Deny]
3. User taps a button
4. Bot sends the response back to the SDK
5. Agent continues

## Blockers

- The Claude Agent SDK does not currently expose permission prompts as
  interceptable events. It either blocks on stdin or skips them entirely
  based on the permission_mode setting.
- Would need SDK changes or a custom stdin bridge to make this work.

## When

Revisit if/when the Agent SDK adds a permission callback or event type.
