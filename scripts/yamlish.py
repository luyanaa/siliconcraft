"""yamlish -- minimal YAML subset parser for siliconcraft-generated files.

Parses exactly the shape emitted by siliconcraft generators (and the
hand-written official/manifest.yaml): indent-based block mappings and
sequences, inline flow mappings/sequences, quoted/plain scalars, booleans, null,
ints, and floats.
Comments (`#`) and blank lines are ignored.  Anything else fails loudly --
this is intentionally NOT a general YAML parser.
"""


class YamlishError(ValueError):
    pass


def _split_flow(s):
    """Split a flow-map or flow-sequence body at top-level commas."""
    parts, cur, q, depth = [], "", None, 0
    for ch in s:
        if q:
            cur += ch
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            cur += ch
        elif ch in "[{":
            depth += 1
            cur += ch
        elif ch in "]}":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts


def _flow_map(tok):
    """Parse an inline flow mapping {key: value, ...}."""
    inner = tok[1:-1].strip()
    out = {}
    for part in _split_flow(inner):
        if not part.strip():
            continue
        k, _, v = part.partition(":")
        out[k.strip()] = _scalar(v.strip())
    return out


def _flow_seq(tok):
    """Parse an inline flow sequence, including nested sequences and maps."""
    inner = tok[1:-1].strip()
    if not inner:
        return []
    return [_scalar(part) for part in _split_flow(inner)]


def _scalar(tok):
    tok = tok.strip()
    if tok.startswith("[") and tok.endswith("]"):
        return _flow_seq(tok)
    if tok.startswith("{") and tok.endswith("}"):
        return _flow_map(tok)
    if tok.startswith('"') and tok.endswith('"') and len(tok) >= 2:
        return tok[1:-1]
    if tok.startswith("'") and tok.endswith("'") and len(tok) >= 2:
        return tok[1:-1]
    if tok == "true":
        return True
    if tok == "false":
        return False
    if tok == "null":
        return None
    if tok == "[]":
        return []
    if tok == "{}":
        return {}
    try:
        return int(tok)
    except ValueError:
        pass
    try:
        return float(tok)
    except ValueError:
        pass
    return tok


def load(text):
    raw = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        raw.append((indent, line.strip()))
    if not raw:
        return {}
    pos = 0

    def is_item(line):
        return line == "-" or line.startswith("- ")

    def block(indent):
        nonlocal pos
        if pos >= len(raw) or raw[pos][0] != indent:
            raise YamlishError(f"line {pos}: expected indent {indent}")
        if is_item(raw[pos][1]):
            return seq(indent)
        return mapping(indent)

    def mapping(indent):
        nonlocal pos
        out = {}
        while pos < len(raw) and raw[pos][0] == indent and not is_item(raw[pos][1]):
            line = raw[pos][1]
            pos += 1
            if ":" not in line:
                raise YamlishError(f"line {pos}: expected 'key: value'")
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            # strip inline comments (not inside the quoted portion)
            if val.startswith('"'):
                end = val.find('"', 1)
                if end >= 0:
                    val = val[: end + 1]
            elif "#" in val:
                val = val[: val.index("#")].strip()
            if not val:
                if pos < len(raw) and raw[pos][0] > indent:
                    out[key] = block(raw[pos][0])
                else:
                    out[key] = None
            else:
                out[key] = _scalar(val)
        return out

    def seq(indent):
        nonlocal pos
        out = []
        while pos < len(raw) and raw[pos][0] == indent and is_item(raw[pos][1]):
            rest = raw[pos][1][1:].strip()
            pos += 1
            if rest and ":" in rest and not rest.startswith(("{", "[", '"', "'")):
                key, _, val = rest.partition(":")
                item = {key.strip(): _scalar(val.strip()) if val.strip() else None}
                if pos < len(raw) and raw[pos][0] > indent:
                    child = block(raw[pos][0])
                    if not isinstance(child, dict):
                        raise YamlishError("sequence mapping item has non-mapping continuation")
                    item.update(child)
                out.append(item)
            elif rest:
                out.append(_scalar(rest))
            else:
                if pos < len(raw) and raw[pos][0] > indent:
                    out.append(block(raw[pos][0]))
                else:
                    out.append(None)
        return out

    return block(raw[0][0])
