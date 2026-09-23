# Your first agent-memory conversation

By the end, you will see the adviser remember Alex’s camera in a new conversation
and check that Jordan does not receive Alex’s memories. You need basic terminal
skills, but no previous experience with agent memory.

## What you are learning

In this app, the model receives the current message plus context selected by the
application. **Session memory** supplies earlier messages in the same conversation.
**Long-term memory** supplies saved facts about the shopper, even in a new conversation.

For example, “I own a Sony ZV-E10” is first saved as a conversation message.
Redis Agent Memory later extracts a fact about camera ownership. **Extraction**
means turning messages into useful facts; it runs in the background and takes time.
The app retrieves relevant facts before asking the model for its next reply.

Three pieces work together:

| Piece | Where it runs | What it does |
| --- | --- | --- |
| Redis for the catalogue | Docker on your computer | Stores products and supports search. |
| Redis Agent Memory (RAM) | Redis Cloud | Stores conversation history and extracts long-term facts. |
| Chat model | OpenAI API | Writes the reply using the context supplied by the app. |

Starting Docker does not create the cloud memory service. You will connect that
separately in step 2. The [Redis overview](https://redis.io/docs/latest/develop/ai/context-engine/agent-memory/)
explains the two memory types in more detail.

## 1. Get the project

Install [Git](https://git-scm.com/install/),
[Docker](https://docs.docker.com/get-started/get-docker/),
[uv](https://docs.astral.sh/uv/getting-started/installation/), and
[Node.js](https://nodejs.org/en/download) 22.18 or later. You also need Make
(on macOS, install Apple’s command-line tools with `xcode-select --install`).
The commands below use Bash or Zsh; local setup has been verified on macOS.

Start Docker Desktop or your Docker engine. Check that Docker is reachable and
install the project’s Python version:

```bash
docker info
uv python install 3.12
```

For a **new checkout**, run:

```bash
git clone --branch agent-memory https://github.com/s-agbede/redis-iris-webinars.git
cd redis-iris-webinars
cp .env.example .env
```

If you already have this branch checked out, use that directory and keep your
existing `.env`. Run all subsequent commands from the repository root.
While the repository is private, you need a GitHub invitation and Git access.
If `agent-memory` is unavailable, ask the presenter for the published webinar branch.

## 2. Connect the memory service and chat model

### Get the memory-service credentials

Open the [Redis Cloud console](https://cloud.redis.io/) and select **Agent Memory**.
Create a service using **Quick create** if offered. If you need **Create custom**,
follow the [Redis service setup guide](https://redis.io/docs/latest/operate/iris/agent-memory/create-service/)
to select an eligible database. Keep the built-in memory types and Redis-managed
model credentials for this first exercise; no custom memory type is required.

Save the service API key when it is displayed. In the service’s **Configuration**
tab, copy its **Endpoint** and **Store ID**. The
[Redis connection instructions](https://redis.io/docs/latest/develop/ai/context-engine/agent-memory/python-sdk-quickstart/#save-the-connection-values)
show where to find these values. Use the memory-service key, not your Redis
database password.

### Fill in `.env`

Create an OpenAI API key using the
[OpenAI API quickstart](https://developers.openai.com/api/docs/quickstart#create-and-export-an-api-key).
This key is for the shop’s replies, separate from the memory service’s credentials.

Open the `.env` file in your editor and replace these four empty values:

```dotenv
AGENT_MEMORY_BASE_URL=https://your-memory-service-endpoint
AGENT_MEMORY_STORE_ID=your-store-id
AGENT_MEMORY_API_KEY=your-memory-service-key
OPENAI_API_KEY=your-openai-api-key
```

Replace every example value with your own. Keep the endpoint’s `https://` prefix.
Leave `SHOP_CHAT_MODEL=gpt-5-mini` as supplied by the project.

Set `SHOP_OWNER_PREFIX` to a fresh label, such as `sam-camera-01`, using your own
name or initials. Use 1–48 letters, digits or hyphens. This separates your Alex
and Jordan from other attendees’ demo shoppers if you share a memory store.
Keep that label unchanged throughout the exercise.

For this first run, leave the three `SHOP_PLAYBOOK_*` values empty and
`AGENT_MEMORY_NAMESPACE_ID` commented out. Keep `REDIS_URL`, `REDIS_PORT`,
`NAMESPACE` and the other defaults. Save `.env`; it is ignored by Git.

## 3. Start the app

```bash
make up
```

The first run installs dependencies, downloads the local search model, builds
the frontend and indexes the bundled products. Allow several minutes. Wait for
`Application startup complete`, then open [the adviser](http://127.0.0.1:8000/).
Keep the terminal running.

Check these two pages if the adviser cannot connect:

- [Catalogue health](http://127.0.0.1:8000/api/health): expect `status: "ready"`.
- [Shop configuration](http://127.0.0.1:8000/api/shop/status): expect
  `configured: true`, `missing: []` and `catalogue_ready: true`.

`configured: true` means the required settings are present. It does **not** test
the keys or cloud connections. The first successful reply is the next checkpoint.

If port 8000 is occupied, use `make up PORT=8001` and replace 8000 with 8001 in
the browser URLs. See [port settings](local-development.md#ports) for Redis conflicts.

## 4. Try one memory conversation

Use fictional details; chat sends them to the configured cloud services.
Open **⋯ Chat settings** beside the message box. Select
**Alex** and choose **New conversation** so earlier messages do not affect the test.

### Remember within this conversation

Choose **Memory for the next reply → Short-term: this session only**. Send:

> I own a Sony ZV-E10 and film walking tours. I prefer lightweight equipment.

Wait for a reply, then ask:

> What camera do I own?

**Check:** the reply should identify the Sony ZV-E10. Under that reply, expand
**What the model saw**. Your earlier message should appear in **Earlier conversation**,
and **Retrieved memories** should say no long-term memories were supplied.
This shows the answer had access to this conversation’s history.

### See what changes with memory off

Choose **No conversation memory** and ask the same question again, without naming
the camera in the new message.

**Check:** **What the model saw** should show no previous turns and no long-term
memories. The adviser should ask for the missing information. Inspect the context
even if the model guesses: a correct guess alone does not prove recall.

These modes control what the next reply receives. Messages are still saved for
background extraction, even when memory context is off.

### Wait for a long-term fact

Open **⋯ Chat settings → Open memory inspector**. Under **Long-term memory**, use
**Refresh** or enable **Refresh every 10 seconds**. Wait until a record says that
Alex owns the Sony ZV-E10. Its wording may differ from your message.

The default extraction interval is five minutes; a configured service may use
a different interval. Allow additional processing time. Refresh reads the store;
it does not trigger extraction. See the
[Redis extraction settings](https://redis.io/docs/latest/operate/iris/agent-memory/create-service/#memory-configuration).
An empty list immediately after a reply is normal. If no fact appears after
several intervals, use the troubleshooting table below.

### Remember across conversations

Once the fact is visible, choose **Short-term + long-term**, keep **Alex**, and
select **New conversation**. Ask:

> What camera do I own?

**Check:** the adviser should identify the Sony ZV-E10. In **What the model saw**,
**Earlier conversation** should be empty and **Retrieved memories** should contain
the ownership fact. That is the evidence of recall across conversations.

### Keep shoppers separate

Switch **Demo shopper** to **Jordan**, select **New conversation**, choose
**Short-term + long-term**, and ask the same ownership question.

**Check:** Alex’s ownership fact must not appear in Jordan’s **Retrieved memories**.
With a fresh demo prefix, Jordan’s long-term inventory should be empty. The adviser
should ask which camera Jordan owns. Shopper selection is a teaching control,
not a login system.

You have now checked memory within one conversation, across conversations, and
between shoppers. Optionally return to Alex and ask for lightweight gear to see
the same context used with catalogue search.

## 5. Stop, restart or start fresh

Press **Ctrl+C** in the server terminal to stop the app. `make down` also stops
local Redis while preserving its data. To return later:

```bash
make redis
make serve
```

After editing Python code or `.env`, stop and restart `make serve`.
**New conversation** clears the context for the new chat while keeping the same
shopper’s long-term facts. For a fresh pair of demo shoppers, change
`SHOP_OWNER_PREFIX`, restart the backend, and start new conversations. Old records
are retained until the memory service’s configured expiry; this does not delete them.

## If something does not work

| What you see | What to do |
| --- | --- |
| Git cannot find the repository or branch | Check your invitation, Git authentication and the presenter’s published branch name. |
| A command is missing or Docker cannot connect | Finish step 1 and start Docker. `docker info` must succeed. |
| The page says “Finish connecting your adviser” | Fill the named settings in `.env`, save, stop the backend and run `make serve` again. |
| Settings say configured, but chat fails | Read the error. Verify the memory endpoint, Store ID and service key belong together, and that the OpenAI key has API/model access. Check your network. Settings presence does not establish connectivity. |
| Chat works, but no long-term fact appears | Confirm the ownership message is in the session context. Check the service’s extraction settings and expiry in Redis Cloud; wait several extraction intervals. Refresh the inspector. |
| A new conversation cannot recall the camera | Keep the same shopper and owner prefix, select **Short-term + long-term**, and first verify the ownership fact exists. Inspect **Retrieved memories** to see whether that fact was actually supplied. |
| Changing mode does not change an old reply | Modes apply to the next message. Send the question again and inspect the new reply. |
| A saved conversation will not restore, or you see HTTP 500 | Restart the backend after code or configuration changes, then use **Retry restoring conversation**. If it persists, read the server terminal error before retrying; keep the saved data for diagnosis. |
| Search/model setup or ports fail | Use the [local troubleshooting reference](local-development.md#troubleshooting). |

## After your first successful run

See the [presenter runbook](../demos/agent-memory.md) for a timed version of this
exercise, the [architecture](../architecture/agent-memory.md) for the code flow,
or [advanced examples](agent-memory-advanced.md) for Playbook, corrections and custom
memory types. None is required to complete this guide.
