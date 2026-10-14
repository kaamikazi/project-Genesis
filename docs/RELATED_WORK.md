# Related work

The titles, authors and licences below were checked against arXiv and the GitHub API on 2026-10-14. The summaries are brief characterisations of each paper's main contribution, not reproductions of their results.

| Work | What it established | Limits relevant to GENESIS | Licence (code) |
|---|---|---|---|
| **Generative Agents: Interactive Simulacra of Human Behavior.** Park, O'Brien, Cai, et al., 2023. [arXiv:2304.03442](https://arxiv.org/abs/2304.03442), [code](https://github.com/joonspk-research/generative_agents) | 25 LLM agents in a sandbox town with memory streams, reflection and planning produce believable individual and social behaviour. | Its consequences are mostly social and narrative. It has no conserved resource economy, and claims about artifacts are not executed or verified. | Apache-2.0 |
| **Voyager: An Open-Ended Embodied Agent with Large Language Models.** Wang, Xie, Jiang, et al., 2023. [arXiv:2305.16291](https://arxiv.org/abs/2305.16291), [project](https://voyager.minedojo.org/) | A single agent builds a growing library of executable code skills in Minecraft, driven by an automatic curriculum and refined through environment feedback. | There is one agent and no society, so it has no transmission between agents and no inheritance across generations. Minecraft knowledge is heavily represented in LLM training data. | MIT |
| **Generative agent-based modeling with actions grounded in physical, social, or digital space using Concordia.** Vezhnevets, Agapiou, Aharon, et al., 2023. [arXiv:2312.03664](https://arxiv.org/abs/2312.03664), [code](https://github.com/google-deepmind/concordia) | A library for LLM agent-based models in which a Game Master agent checks the plausibility of natural-language actions and grounds them. | Grounding is decided by an LLM game master rather than by enforced mechanics with conservation invariants. | Apache-2.0 |

The original GENESIS spec also mentions agent checkpointing and recovery research (for example, the gap between an agent's tool calls and their OS-level effects). That literature has **not** been reviewed here yet, so no reference is given.

## What GENESIS explores

GENESIS combines the following. Whether this combination is new has **not** been established by a literature review, and no novelty is claimed.

1. **Mechanical authority:** a deterministic engine with integer accounting and conservation invariants. Statements cannot change state.
2. **Executable invention:** bounded programs evaluated independently on held-out cases. Revisions must beat their parent.
3. **Provenance:** a hash-chained event log, content-addressed artifacts, and a logged transmission path for every claimed adoption.
4. **Retention experiments:** removing creators, with matched controls that account for lost labour and inventory.
5. **An unfamiliar mechanic:** the phase-conversion rule is fictional, which limits how far an LLM controller could rely on prior human knowledge. This matters once LLM controllers exist; the current controllers are not LLMs.

## Still to review

- agent checkpointing and recovery work
- cultural-evolution and cumulative-culture models (agent-based and laboratory)
- LLM multi-agent economics and governance simulations from 2024–2026
- open-endedness benchmarks
