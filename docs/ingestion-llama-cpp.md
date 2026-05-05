# Corpus ingestion with llama.cpp

Hermes corpus ingestion does not send source text to any model by default. LLM extraction only runs when you explicitly pass `--extractor llm` or `--extractor deterministic,llm` plus an explicit command.

For a local llama.cpp server, use the bundled OpenAI-compatible wrapper:

```bash
python -m continuity.ingest.scripts.llama_cpp_extract \
  --endpoint http://127.0.0.1:8080/v1/chat/completions
```

Start llama.cpp separately, for example:

```bash
llama-server -hf bartowski/Llama-3.2-3B-Instruct-GGUF:Q4_K_M -c 8192
```

Then run ingestion:

```bash
continuity-ingest run ~/docs \
  --extractor llm \
  --llm-command "continuity-ingest-llama-cpp --endpoint http://127.0.0.1:8080/v1/chat/completions" \
  --policy require-review \
  --output .ingestion/run-llama
```

Useful options:

```bash
continuity-ingest-llama-cpp \
  --endpoint http://127.0.0.1:8080/v1/chat/completions \
  --model local-model \
  --temperature 0 \
  --max-tokens 1024 \
  --timeout 120
```

Privacy note: this wrapper sends source segment text only to the endpoint you provide. Use `127.0.0.1`/`localhost` for a local-only llama.cpp server. The default deterministic extractor does not send corpus text anywhere.
