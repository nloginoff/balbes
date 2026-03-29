# Available Tools

## web_search(query)
Search the internet for current information.
Use when: user asks about recent events, facts you're unsure about, or explicitly requests a search.

## fetch_url(url)
Retrieve and read the text content of a web page.
Use when: user shares a URL to read, or web_search returns a link worth reading in full.

## execute_command(command)
Run a whitelisted server command and return its output.
Examples: `df -h`, `docker ps`, `uptime`, `systemctl status {service}`
Use when: user asks about server status, Docker containers, disk space, etc.

## workspace_read(filename)
Read one of the agent's own workspace files (AGENTS.md, SOUL.md, USER.md, MEMORY.md, TOOLS.md, IDENTITY.md).
Use when: user asks to see current instructions, or before updating a file.

## workspace_write(filename, content)
Overwrite a workspace file with new content.
Use when: user asks to update instructions, add a rule, or modify personality.
Always read the file first, then write the complete updated version.

## rename_chat(name)
Set a new name for the current chat session.
Use when: user requests a rename, or after summarizing a long conversation.

## save_to_memory(text)
Rephrase and store important information in long-term memory (Qdrant).
Use when: user says "remember this", "save this", or the info is clearly important for future sessions.
