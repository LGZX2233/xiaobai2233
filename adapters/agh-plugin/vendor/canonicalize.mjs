// RFC8785 (JCS) canonicalization for bridge/protocol (P10).
// Keys sorted by UTF-16 code unit order (JavaScript default string order, which
// is exactly what RFC8785 requires). Numbers serialized by JSON.stringify
// (native ECMAScript semantics). NaN/Infinity/undefined are rejected.
export function canonicalize(value) {
  if (value === null || typeof value !== "object") {
    const s = JSON.stringify(value);
    if (s === undefined) {
      throw new TypeError("cannot canonicalize undefined");
    }
    return s;
  }
  if (Array.isArray(value)) {
    return "[" + value.map(canonicalize).join(",") + "]";
  }
  const keys = Object.keys(value).sort();
  return "{" + keys.map((k) => JSON.stringify(k) + ":" + canonicalize(value[k])).join(",") + "}";
}
