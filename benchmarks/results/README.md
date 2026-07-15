# Benchmark results index

Per-run reports (tables + legend) live in each run's own `README.md`.

| run | profile | models | config | runs | load time | tokens in/out |
|---|---|---|---|---|---|---|
| [baseline-fa64565119](baseline-fa64565119/README.md) | baseline | gemma-4-26b-a4b-it-awq-4bit, llama-3.2-3b-instruct-awq-int4 | `2b00c31a85` | 32 | 20.0 min | 4,647,702 / 670,329 |
| [solo-gemma-26b-a4b-8k-2d44e6f25d](solo-gemma-26b-a4b-8k-2d44e6f25d/README.md) | solo-gemma-26b-a4b-8k | gemma-4-26b-a4b-it-awq-4bit | `2d44e6f25d` | 8 | 4.3 min | 1,157,309 / 174,138 |
| [solo-gemma-26b-a4b-8k-kv-172239b7cb](solo-gemma-26b-a4b-8k-kv-172239b7cb/README.md) | solo-gemma-26b-a4b-8k-kv | gemma-4-26b-a4b-it-awq-4bit | `172239b7cb` | 8 | 4.2 min | 1,157,309 / 173,938 |
| [solo-gemma-31b-32k-85c6e75d60](solo-gemma-31b-32k-85c6e75d60/README.md) | solo-gemma-31b-32k | gemma-4-31b-it-awq-4bit | `85c6e75d60` | 8 | 50.4 min | 4,185,103 / 173,047 |
