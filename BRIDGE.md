# techfriendcommunity bridge

`bridge.py` mirrors this server's **public** text channels to
[techfriendcommunity.com](https://github.com/aj47/techfriendcommunity), a web/email
front door to the community for people without a Discord account.

## What it does

- On `on_ready`: lists channels the `@everyone` role can read, creates (or reuses) a
  webhook named `techfriendcommunity` in each, and sends channel metadata + webhook URLs
  to the backend (`channel.sync`).
- On message create/edit/delete and reaction add: queues a small JSON event. Events are
  batched and POSTed once per second to `CONVEX_INGEST_URL/discord/ingest` with
  `Authorization: Bearer BRIDGE_SECRET`. Failed batches are retried with backoff.
- `!link ABCDEF` in any mirrored channel claims a web account (the code comes from the
  website's Settings page). The bot reacts ✅ and does not mirror that message.
- Outbound: web/email posts are delivered by the backend straight to the channel
  webhooks — the bot is not involved, so web posting keeps working if the bot is down.
  Those posts re-enter here as normal webhook messages and are de-duplicated server-side.

Everything is wrapped so a bridge failure never affects the rest of the bot.

## Enable

```
BRIDGE_ENABLED=true
CONVEX_INGEST_URL=https://<deployment>.convex.site
BRIDGE_SECRET=<same value set with `npx convex env set BRIDGE_SECRET ...`>
```

The bot needs the **Message Content** intent and **Manage Webhooks** permission.

## Run standalone

To run the mirror from another machine before redeploying the main bot:

```
python run_bridge_standalone.py
```

It uses the same env vars and its own bot token.
