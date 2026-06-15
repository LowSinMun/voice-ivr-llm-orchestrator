# Voice-to-Voice LLM IVR Orchestrator

An enterprise-grade, low-latency Voicebot orchestration system built with **FastAPI**, **n8n**, and **Vapi**. This project demonstrates how to significantly cut down workflow complexity by migrating heavy business logic from visual nodes into a centralized backend state machine.

## 🚀 Key Improvements
- **85% Node Reduction:** Streamlined the visual workflow from 60+ nodes to just 11 nodes by handling session memory and retries via backend APIs.
- **Latency Mitigation:** Integrated a dynamic "Filler" mechanism to cover LLM execution gaps, eliminating dead air.
- **Full-Duplex Interactive:** Supports native user barge-in (interruptions) and real-time error self-correction.

## 🛠️ Architecture

```text
[User Speech] -> (Vapi) -> (n8n Webhook Gateway) -> [FastAPI Backend]
                                     |
                          (Session Cache & Logic)
```


## 📦 Tech Stack
- **Backend:** FastAPI, Uvicorn, Pandas, Pyngrok
- **Orchestration:** n8n (Workflow automation)
- **Voice Layer:** Vapi / Webhook gateway

## 🔧 Setup & Installation
1. Clone the repository.
2. Set your environment variable: `export NGROK_TOKEN="your_token"`
3. Run `start.bat` to install dependencies and spin up the server.