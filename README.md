# translate_python

A lightweight Python toolkit and CLI for translating text between languages with pluggable backends.

---

## Features

- Simple, consistent API: one call to translate text between any supported language pair.
- Pluggable backend system: swap translation engines without changing your application code.
- Command-line interface for quick translations from the shell.
- Async-friendly: built on top of `asyncio` for high-throughput use cases.
- Zero hard dependencies beyond the Python standard library for the core; backends bring their own optional dependencies.

---

## Installation

```bash
pip install translate_python
```

Requires Python 3.9+.

---

## Quick start

### Python API

```python
from translate_python import Translator

# Using the default (free) backend
t = Translator(source="en", target="ru")
result = t.translate("Hello, world!")
print(result.text)  # "Привет, мир!"
```

Translate multiple strings in one call:

```python
texts = ["Good morning", "See you later", "Thank you"]
results = t.translate_batch(texts)
for r in results:
    print(r.text)
```

### CLI

```bash
# Translate a single phrase
translate_python --from en --to de "The quick brown fox"
# -> "Der schnelle braune Fuchs"

# Pipe stdin
echo "Hello" | translate_python --from en --to fr
# -> "Bonjour"

# List available backends
translate_python --list-backends
```

---

## Supported languages

`translate_python` supports all languages provided by the configured backend. With the default backend, the following language codes are available (ISO 639-1):

| Code | Language   | Code | Language   |
|------|-----------|------|-----------|
| `en` | English    | `de` | German     |
| `ru` | Russian    | `fr` | French     |
| `es` | Spanish    | `zh` | Chinese    |
| `ja` | Japanese   | `ar` | Arabic     |
| `pt` | Portuguese | `it` | Italian    |

Run `translate_python --list-languages` to see the full list for the active backend.

---

## Configuration

Configuration can be provided via environment variables or a `~/.translate_python.cfg` file:

```ini
[translate_python]
backend = default
source_lang = en
target_lang = ru
timeout = 10
```

Environment variables take precedence over the config file:

```bash
export TRANSLATE_BACKEND=default
export TRANSLATE_TIMEOUT=15
```

---

## Backends

| Backend name | Description                        | Extra dependency  |
|--------------|------------------------------------|-------------------|
| `default`    | Free, no key required              | —                 |
| `deepl`      | DeepL API (high quality)           | `deepl`           |
| `google`     | Google Cloud Translation           | `google-cloud-translate` |

Install a backend's dependencies with:

```bash
pip install translate_python[deepl]
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
