# PyMind AI 🤖

A text-only Python assistant powered by the **Groq API** (`openai/gpt-oss-20b`). Runs in a terminal, responds in Arabic or English, remembers recent messages during the current session, and has `/clear` and `/exit` commands.

## Setup (Windows / PowerShell)

1. Extract the ZIP to your Documents folder.
2. Open PowerShell in the extracted `PyMindAI` folder.
3. Create a virtual environment:

   ```powershell
   py -m venv .venv
   ```

4. Install dependencies (without activating the environment):

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

5. Copy `.env.example` to `.env`:

   ```powershell
   Copy-Item .env.example .env
   ```

6. Edit `.env` locally, replacing `paste_your_groq_key_here` with your real key. **Never commit or share this file.**
7. Run:

   ```powershell
   .\.venv\Scripts\python.exe bot.py
   ```

## Commands

- `/clear` — erase the current session chat context.
- `/exit` — close the bot.

## Local tests (no API calls)

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Notes

- Only text is supported. You need an internet connection and a valid Groq API key.
- Groq offers a free tier with usage limits; limits can change. Consult https://console.groq.com/docs/rate-limits.
- Chat history is kept in RAM during this run, not saved to a file.
- The `.env` file is excluded by `.gitignore`.
