# Multi-Agent System

A proof-of-concept multi-agent system where LLM-powered agents communicate through a transport-agnostic messaging layer. Agent logic is entirely independent of the communication medium.

## Prerequisites

- Python 3.12
- [uv](https://github.com/astral-sh/uv) — package manager
- [just](https://github.com/casey/just) — task runner

## Setup

```bash
just setup
```

Copy `.env.defaults` to `.env` and set required secrets (e.g., `GREETING_SECRET`).

## First Run

```bash
just run
```

## Running Tests

```bash
just test
```

## Documentation

- [Implementation Guide](docs/implementation-guide.md)
- [ADR Index](docs/adr/README.md)
