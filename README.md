# 🦂 Karatos: Scaling Brain Architecture (V2.6)

<p align="center">
  <img src="assets/karatos_scorpion_logo.png" width="300" alt="Karatos Scorpion Logo">
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#getting-started">Getting Started</a> •
  <a href="#usage">Usage</a>
</p>

> [!NOTE]
> This repository documentation reflects the **V2.6 "Scorpion" Upgrade**, a major breakthrough in agentic cognition and peer-to-peer scaling.

**Karatos** (formerly Little Niva) is a state-of-the-art autonomous system agent. With the V2.6 upgrade, Karatos has evolved from a reactive assistant into a highly scalable, communicative, and self-correcting cognitive entity designed for enterprise production environments.

---

## ✨ Key Features

### 🧠 Dynamic Intent Escalation
Karatos features **Neural Pivoting**. If a simple conversation (`CHAT`) intent is found insufficient for a complex request, the Brain automatically escalates to a `PLAN` intent. This self-correcting logic ensures the agent autonomously reaches for tools and data whenever a knowledge gap is detected during execution.

### 💬 Inter-Agent Messaging (Zero-Config)
We have decentralized Karatos' communication layer. Agents now coordinate via **Direct Messaging**. Each discovered agent in the cluster is exposed as a dynamic `agent:` tool, allowing the Brain to call other bots directly for collaborative planning and social interaction without manual configuration.

### 🎞️ Episode-Aware Context & Critic
Interaction history is segmented into discrete **Cognitive Episodes**, ensuring relevant memory retrieval without context pollution. Every generation cycle is strictly preceded by a **Context Critic** audit, which critiques the sufficiency of available information and prevents vague or generic responses.

### 🛡️ Hardened Private Routing
Routing integrity is reinforced with real-time metadata. Karatos guarantees consistent and context-aware responses in private 1-on-1 chats, ensuring the agent remains a reliable partner even in highly ambiguous interaction states.

---

## 🏛️ Architecture Overview

Karatos operates on the **OTAR Cognitive Loop**:
1. **Observation**: Multimodal perception (Vision via Llama-Vision, Audio via Whisper) gathers environmental inputs.
2. **Thinking**: The Context Critic audits memory and intent to establish logical planning.
3. **Action**: Tool execution and inter-agent dynamic dispatching.
4. **Reflection**: Neural Identity Reconciliation refines the persona based on persistent, AES-256 encrypted memory streams.

---

## 🚀 Getting Started

### Prerequisites
- **Python:** 3.10+
- **Environment:** Dedicated virtual environment recommended.
- **Dependencies:** API Keys for configured LLM/Vision/Audio providers (e.g., Anthropic, OpenAI, Local Ollama).

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/your-org/karatos.git
   cd karatos
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Setup environment configuration:
   ```bash
   cp .env.example .env
   # Edit .env with your specific providers and API keys
   ```

---

## 💻 Usage

### Running the Agent
Start the Karatos agent in standard daemon mode:
```bash
python main.py
```

### Launching the Dashboard GUI
To monitor cognitive states, memory streams, and configuration visually, start the dashboard:
```bash
python main.py --gui 
# The Dashboard will be available at http://localhost:7860
```

---

## 🔒 Security & Privacy

Karatos ensures **Secure Sovereignty** by default. Memory streams are encrypted at rest using AES-256 to ensure that sensitive conversation traces and neural identity data cannot be compromised. Strict ethical guardrails dictate the boundaries of its dynamic intent execution.

---

## 📄 License
Proprietary - NivaSound Internal Use Only

*Copyright © 2026 NivaSound.*
