# Sam’s Camera Shop

A small camera adviser for learning **agent memory**. Tell it which camera you
own, start a new conversation, and see how it can use that fact again.

The app supplies context with each request to the model:

- **Session memory:** messages from the current conversation.
- **Long-term memory:** facts saved for the shopper and retrieved across conversations.

Redis Agent Memory extracts long-term facts from conversations in the background.
The app lets you turn memory context off and inspect exactly what the model received.

## Start here

**[Follow the beginner quickstart →](docs/guides/agent-memory-quickstart.md)**

It takes you through setup, one conversation, and a check that memory works.
You need basic terminal skills, Docker, Python/uv, Node.js, a Redis Agent Memory
service and an OpenAI API key. The guide explains where to get them. Allow several
minutes for the first setup and for background memory extraction.

Playbook, custom memory types and privacy-filter demonstrations are optional.
They are not needed for your first run.

Already set up? From the repository root:

```bash
make redis
make serve
```

Open [the adviser](http://127.0.0.1:8000/), then follow
[your first memory conversation](docs/guides/agent-memory-quickstart.md#4-try-one-memory-conversation).
Use fictional details: Alex and Jordan are demo shoppers, not authenticated accounts.

## Other ways to explore

| You want to… | Go here |
| --- | --- |
| Try search without cloud credentials | [Local search setup](docs/guides/local-development.md#run-locally), then [Search lab](http://127.0.0.1:8000/?view=compare) |
| Present the 15-minute memory webinar | [Presenter runbook](docs/demos/agent-memory.md) |
| Change ports, edit code or troubleshoot local setup | [Local development reference](docs/guides/local-development.md) |
| Understand how the memory code works | [Memory architecture](docs/architecture/agent-memory.md) |
| Explore optional memory features | [Advanced memory guide](docs/guides/agent-memory-advanced.md) |
| Browse the search and production webinars | [Documentation index](docs/README.md) |

The catalogue contains real product listings. Purchase histories are fictional;
the adviser cannot verify prices, stock or compatibility. The same catalogue also
supports the search and production-pattern demos.
