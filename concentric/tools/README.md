# Generated tools

One file per tool, named after it. A file here defines exactly four names:

```python
NAME = "lookup_rate"
DESCRIPTION = "one sentence the model reads to decide when to call it"
INPUT_SCHEMA = {"type": "object", "properties": {...}, "required": [...]}
def run(**kwargs) -> str: ...
```

Standard library only. `run` returns a string and never raises — return an error
sentence instead, the way every waku tool does.

**Nothing here is available to anyone until it is assigned.** The assignment lives
in `.waku-concentric/toolbox.json`, written from **Tools → Market**, and a file
sitting here that nobody holds is simply never imported.

Two things worth knowing before adding one by hand:

- Reading this folder for the Market page does **not** import these files. The
  name, description and shape are read out of the source with `ast`, so a broken
  or hostile file cannot run just by being listed.
- A tool runs inside the agent's own process with the agent's own reach. There is
  no sandbox here, which is why the page makes a generated tool be read before it
  can be handed to a seat.

Files beginning with `_` are ignored, so a shared helper can live here too.
