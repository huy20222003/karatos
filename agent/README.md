# Brain - Autonomous System Agent

An AI-powered autonomous agent that monitors, analyzes, and takes actions on the NivaSound platform.

## Architecture

```
agent/
├── config/           # Configuration & environment settings
├── core/             # Brain logic, identity, and main loop
├── tools/            # Database access, crypto
├── memory/           # Short-term memory & context management
├── utils/            # Logging, helpers
└── main.py           # Entry point
```

## Quick Start

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
```

3. Run the agent:
```bash
python main.py
```

## Core Concepts

### Identity (Bản ngã)
The agent operates with a persistent identity defined in `core/identity.py`. It doesn't wait for commands - it thinks and acts autonomously.

### Thinking Loop
1. **OBSERVE**: Scan audit logs (3-hour rolling window)
2. **REASON**: Analyze patterns, detect anomalies
3. **INVESTIGATE**: Deep dive into suspicious entities
4. **DECIDE**: Choose appropriate action based on rules
5. **EXECUTE**: Direct system interaction or CLI commands
6. **REFLECT**: Verify result and learn

### Tools
- **Database Reader**: Direct PostgreSQL access (read-only)
- **Crypto Module**: Securely handle sensitive data

### Safety Guardrails
- Maximum actions per hour limit
- Human-in-the-loop for critical decisions
- Action audit trail
- Rollback capability

## Configuration

See `config/settings.py` for all available options.

## License

Proprietary - NivaSound Internal Use Only

agent/
├── config/                    # Cấu hình & môi trường
│   ├── __init__.py
│   ├── settings.py            # Quản lý biến môi trường (Pydantic)
│   └── rules.py               # Luật lệ & ngưỡng hành vi (Guardrails)
│
├── core/                      # Bộ não & vòng lặp tự trị
│   ├── __init__.py
│   ├── identity.py            # "Bản ngã" của Agent (System Prompt)
│   ├── brain.py               # Kết nối LLM (NivaCore-GGUF)
│   └── loop.py                # Vòng lặp Observe-Think-Act
│
├── tools/                     # Công cụ tương tác với hệ thống
│   ├── __init__.py
│   ├── database_reader.py            # Đọc trực tiếp DB (Read-only)
│   └── crypto.py              # Giải mã dữ liệu (AES-256-GCM)
│
├── memory/                    # Trí nhớ ngắn hạn
│   ├── __init__.py
│   ├── short_term.py          # Cửa sổ 3 giờ (Rolling Window)
│   └── context.py             # Quản lý Investigation đang diễn ra
│
├── actions/                   # Hành động có thể thực thi
│   ├── __init__.py
│   ├── base.py                # Abstract base class
│   ├── user_lookup.py         # Search and analyze user status
│   └── system_actions.py      # Alert, Escalate, Block IP
│
├── utils/                     # Tiện ích
│   ├── __init__.py
│   ├── logger.py              # Logger với "Thought" & "Observation"
│   └── helpers.py             # Hàm tiện ích chung
│
├── main.py                    # Entry point
├── requirements.txt           # Dependencies Python
├── .env.example               # Template biến môi trường
└── README.md                  # Tài liệu hướng dẫn