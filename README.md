# AI Agent Demo

A conversational AI agent with a web interface built using **Streamlit** and the **Gemini SDK**.

## Features

- **Streamlit Web UI**: Easy-to-use graphical interface.
- **Tools**: Features web search, reading/writing files, and long-term memory.
- **Safety Guardrails**: Automatically limits iterations and tokens, detects loops, and optionally asks for human approval before running risky tools (like `write_file`).
- **Logs**: Detailed execution steps written to `./logs/`.

## Running Locally

1. Create a virtual environment and install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file in the root directory and add your Gemini API Key:
   ```env
   GEMINI_API_KEY="your-api-key-here"
   ```

3. Run the Streamlit app:
   ```bash
   streamlit run app.py
   ```

## Deploying to Streamlit Community Cloud

This project is fully ready to be deployed to [Streamlit Community Cloud](https://streamlit.io/cloud) (Free).

1. Push this repository to your GitHub account.
2. Go to [share.streamlit.io](https://share.streamlit.io/) and click **New app**.
3. Select this repository and set the main file path to `app.py`.
4. Before clicking Deploy, click **Advanced settings** and paste your API key into the **Secrets** field like this:
   ```toml
   GEMINI_API_KEY="your-api-key-here"
   ```
5. Click **Deploy!**

**Note for Cloud Deployment**:
Files created inside the `workspace/` and `logs/` folders, as well as the `memory.json`, are ephemeral on Streamlit Cloud and will be reset if the app goes to sleep or is redeployed.