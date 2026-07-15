# Benchmark results index

Per-run reports (tables + legend) live in each run's own `README.md`.

| run | profile | models | config | runs | load time | tokens in/out |
|---|---|---|---|---|---|---|
| [baseline-fa64565119](baseline-fa64565119/README.md) | baseline | gemma-4-26b-a4b-it-awq-4bit, llama-3.2-3b-instruct-awq-int4 | `2b00c31a85` | 32 | 20.0 min | 4,647,702 / 670,329 |
| [solo-gemma-31b-32k-85c6e75d60](solo-gemma-31b-32k-85c6e75d60/README.md) | solo-gemma-31b-32k | gemma-4-31b-it-awq-4bit | `85c6e75d60` | 8 | 50.4 min | 4,185,103 / 173,047 |
