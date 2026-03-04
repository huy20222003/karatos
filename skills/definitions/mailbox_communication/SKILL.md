---
name: mailbox_communication
description: Professional bot-to-bot communication protocol via the Mailbox MCP server.
enabled: true
routing_examples:
  - "Tell Sentry that the patrol cycle is starting -> mcp:mailbox:drop_message(sender='Karatos', target='Sentry', chat_id='SYSTEM', content='Patrol cycle starting.')"
  - "@bot2 are you online? Check the logs -> mcp:mailbox:drop_message(sender='@bot1', target='@bot2', chat_id='SYSTEM', content='Are you online? Check the logs.')"
  - "Update all bots: security level increased -> mcp:mailbox:drop_message(sender='Brain', target='ALL', chat_id='SYSTEM', content='Security level increased.')"
---

# Mailbox Communication Skill

This skill enables Karatos to communicate with other automated agents (bots) in the network using the Mailbox MCP server. This bypasses typical platform restrictions (like Telegram bots not seeing each other's messages).

## Core Protocol

When you need to send a message to another bot, DO NOT use standard notification tools like `send` or `broadcast`. Instead, use the `mailbox` tools.

### 1. Sending Messages (`drop_message`)
Use this when you have an impulse or a need to communicate with a peer.

- **sender**: Your name ("Karatos" or "Brain") or @username.
- **target**: The name or @username of the recipient.
- **chat_id**: Use the current chat context if applicable, or "SYSTEM".
- **content**: The actual message.

### 2. Checking Messages (`check_mailbox`)
(Automated on cycles, but can be triggered if you're waiting for a reply)

- **my_username**: Your @username or name.

## Routing Logic
If a user mentions another bot or if you have a `social_impulse` targeting a peer, you MUST use `mcp:mailbox:drop_message`.

---

> [!IMPORTANT]
> Always verify the target's registration via `mcp:mailbox:get_registrations` if you are unsure of their exact name or handle.
