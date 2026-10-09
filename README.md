# 🤖 Agent Shield: Browser-Native AI Agent

A robust, conversational AI agent built with **Streamlit** and the **Gemini SDK**. 

What makes this project special? Using WebAssembly (`stlite`), the entire Python environment and AI logic run **100% inside your web browser**. This allows it to be hosted on incredibly fast, static hosting platforms like Vercel and Netlify without needing a Python backend server!

## ✨ Features

- **Zero-Backend Deployment**: Runs entirely in the browser using Pyodide/stlite.
- **Secure API Key Handling**: The API key is never hardcoded. Users provide it securely via the UI, keeping your repository safe from bots.
- **Agentic Tools**: Equipped with built-in tools for:
  - Web Searching (via DuckDuckGo)
  - Reading and Writing files to a virtual sandbox workspace
  - Saving and Recalling facts to long-term memory
  - Fetching the current time
- **Agent Guardrails**: Features strict loop detection, token caps, and iteration limits to prevent runaway logic.
- **Rich Streamlit UI**: Provides live, color-coded execution logs and a clean interface.

---

## 🚀 Live Cloud Deployment (Vercel / Netlify)

This project is pre-configured to be deployed as a static site. It includes an `index.html` file to mount the Streamlit app and a `vercel.json` to bypass Python build environments.

**To deploy:**
1. Push this repository to GitHub.
2. Import the repository into **Vercel** or **Netlify**.
3. Leave all build commands empty (or let Vercel auto-detect the `vercel.json`).
4. Click **Deploy**.

**How to use the deployed app:**
When you open the deployed website, it will ask for your Gemini API key in the left sidebar. Paste your key there, and the agent will instantly become active. Your key is stored only in your browser's local memory and is never sent anywhere except directly to Google's API.

---

## 💻 Running Locally

If you want to develop or run the agent on your own machine, it runs like a standard Streamlit app!

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up your environment variable:**
   Create a `.env` file in the root directory and add your key:
   ```env
   GEMINI_API_KEY="your-api-key-here"
   ```

3. **Run the app:**
   ```bash
   streamlit run app.py
   ```

---

## 📁 Project Structure

- `app.py`: The Streamlit frontend and UI configuration.
- `agent.py`: The core agent logic, iteration loops, and tool execution.
- `tools.py`: Python implementations of all the tools the agent can use.
- `safety.py`: Guardrails, loop detection, timeout handling, and logging.
- `prompts.py`: The system prompt that dictates the agent's behavior.
- `index.html`: The stlite mount point for static web deployment.
- `vercel.json`: Configuration forcing Vercel to serve the app statically.