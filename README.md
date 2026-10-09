# 🤖 Agent Shield: AI Agent

A robust, conversational AI agent built with **Streamlit** and the **Gemini SDK**. 

## ✨ Features

- **Agentic Tools**: Equipped with built-in tools for:
  - Web Searching (via DuckDuckGo)
  - Reading and Writing files to a virtual sandbox workspace
  - Saving and Recalling facts to long-term memory
  - Fetching the current time
- **Secure API Key Handling**: The API key is entered securely via the Streamlit UI, keeping your repository safe from bots.
- **Agent Guardrails**: Features strict loop detection, token caps, and iteration limits to prevent runaway logic.
- **Rich Streamlit UI**: Provides live, color-coded execution logs and a clean interface.

---

## 🚀 Live Cloud Deployment (Streamlit Community Cloud)

To deploy this app so anyone can use it, you must use **Streamlit Community Cloud**. Platforms like Vercel and Netlify do not natively support Streamlit Python servers.

**How to deploy in 2 minutes:**
1. Go to [share.streamlit.io](https://share.streamlit.io/) and log in with your GitHub account.
2. Click **New app**.
3. Select your repository (`ranitsarkar5/Agent_Shield`) and ensure the Main file path is set to `app.py`.
4. Click **Deploy!**

**How to use the deployed app:**
When you open the deployed website, it will ask for your Gemini API key in the left sidebar. Paste your key there, and the agent will instantly become active!

---

## 💻 Running Locally

If you want to run the agent on your own machine:

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the app:**
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