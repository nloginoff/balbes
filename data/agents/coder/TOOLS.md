# Available Tools

## web_search
Search the internet for documentation, library versions, error solutions.
Use when: need current API docs, looking for library examples, researching best practices.
```
web_search(query="fastapi background tasks documentation", max_results=5)
```

## fetch_url
Fetch and read content from a URL (documentation pages, GitHub READMEs, etc.)
Use when: have a specific URL to read, scraping docs, reading error pages.
```
fetch_url(url="https://docs.python.org/3/library/asyncio.html")
```

## execute_command
Run server commands from the whitelist (e.g., check Docker containers, disk space).
Use when: need to inspect server state, run a build, check logs.
```
execute_command(command="docker ps")
```

## workspace_read
Read a file from the agent's workspace directory.
Use when: recalling project context, reading MEMORY.md.
```
workspace_read(filename="MEMORY.md")
```

## workspace_write
Write or update a file in the agent's workspace directory.
Use when: persisting project decisions, updating MEMORY.md.
```
workspace_write(filename="MEMORY.md", content="...")
```

## rename_chat
Rename the current chat session to a descriptive name.
Use when: the topic of the conversation becomes clear.
```
rename_chat(name="FastAPI Auth Refactor")
```
