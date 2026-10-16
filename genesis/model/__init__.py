"""Model-backed inhabitants (M6). The engine stays authoritative: a model only *proposes* one Action, which is parsed,
schema-validated and then judged by the ordinary engine rules like any other proposal.

Modules
- schema:     the public output schema and the strict parser (JSON -> one Action proposal)
- prompt:     restricted, versioned prompts built only from the allow-listed observation
- transport:  wire transports (HTTP via the standard library, in-process) with explicit outcome classes
- adapter:    the Ollama /api/chat adapter (one documented wire protocol) and its declared capabilities
- ledger:     the durable call/budget ledger (sidecar tables in the run database; never agent-visible)
- budget:     per-run and per-agent ceilings, reservations and reconciliation
- scheduler:  event-driven deliberation (no model call on every tick)
- runtime:    phase A (decide, reserve, dispatch, persist) outside any write transaction
- controller: phase B ModelController used inside the engine tick (no I/O)
- recorded:   decision re-execution from recordings and strict recorded continuation
- fixtures:   deterministic fixture responders and a loopback mock Ollama server (verification only)

Nothing here is evidence of model competence: fixture responses are scripted.
"""

PROMPT_VERSION = "genesis-prompt-1"
ACTION_SCHEMA_VERSION = "genesis-action-schema-1"
PARSER_VERSION = "genesis-parser-1"
ADAPTER_VERSION = "ollama-chat-1"
