# CsoulGPT

CsoulGPT is a local browser chatbot for friendly conversation in English. It runs Qwen3.5-4B through Ollama and provides both a browser interface and a Python command-line client.

## Requirements

- Windows 10 or newer
- Python 3.12 or newer
- [Ollama for Windows](https://ollama.com/download/windows)
- The Qwen3.5 4B Q4_K_M model (about 3.3 GB)

## Run the browser app

1. Start Ollama.
2. In PowerShell, download the model once:

   ```powershell
   ollama pull qwen3.5:4b-q4_K_M
   ```

3. Run `Start-CsoulGPT.cmd`.
4. Keep the launcher window open while chatting. Press Ctrl+C there to stop the app.

The launcher checks Python, Ollama, and the model, then starts the local server and opens the browser. Chats remain in the active browser tab and are cleared when it is refreshed or closed.

## Command-line use

```powershell
python .\main.py chat
python .\main.py chat --prompt "I just started learning guitar. Any tips?"
```

Run `python .\main.py chat --help` for generation options. To start the web interface from PowerShell instead, run `python .\main.py web`.

## Tests and evaluation

```powershell
python -m unittest -v test_local_chat
```

With Ollama running, generate the fixed 24-case evaluation transcript:

```powershell
python .\evaluate_chat.py
```

The evaluation uses temperature 0 and a 256-token reply cap. Review the expected behavior and score each final answer for task fit, natural English and formatting, and avoiding unnecessary follow-up questions.

## Project notes

The [implementation walkthrough](docs/How%20CsoulGPT%20Was%20Built.docx) explains setup and architecture. It contains local machine paths that may need adjustment on another computer.

CsoulGPT is an independently owned project by John Kelvin G. De Asis.
