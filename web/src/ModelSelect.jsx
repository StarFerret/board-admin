import { useEffect, useRef, useState } from "react";
import { getOllama, setOllamaModel } from "./api.js";

export default function ModelSelect() {
  const [ollama, setOllamaState] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const requestId = useRef(0);

  async function refresh() {
    const id = ++requestId.current;
    const status = await getOllama();
    if (id === requestId.current) setOllamaState(status);
  }

  useEffect(() => {
    refresh().catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    function onFailover(event) {
      const next = event.detail?.model;
      if (!next) return;
      setOllamaState((current) => (current ? { ...current, model: next } : current));
      setNotice(`Failover → ${next}`);
      setError("");
    }
    window.addEventListener("starferret-ollama-model", onFailover);
    return () => window.removeEventListener("starferret-ollama-model", onFailover);
  }, []);

  async function onChange(event) {
    const id = ++requestId.current;
    const model = event.target.value;
    setOllamaState((current) => (current ? { ...current, model } : current));
    setError("");
    setNotice("");
    try {
      const status = await setOllamaModel(model);
      if (id !== requestId.current) return;
      setOllamaState(status);
      if (status.fallback && status.switched_from) {
        setNotice(`Switched to ${status.model} (from ${status.switched_from})`);
      }
    } catch (err) {
      if (id !== requestId.current) return;
      try {
        const status = await getOllama();
        setOllamaState(status);
        if (status?.model) {
          setNotice(`Using ${status.model}`);
        } else {
          setError(err.message);
        }
      } catch {
        setError(err.message);
      }
    }
  }

  if (!ollama?.reachable) return null;
  const models = ollama.models || [];
  if (!models.length) return <span className="text-xs text-muted-foreground">No models</span>;

  return (
    <label className="flex items-center gap-2 text-xs text-muted-foreground">
      Model
      <select
        className="h-8 max-w-[11rem] rounded-md border border-input bg-background px-2 text-xs text-foreground"
        value={ollama.model || models[0]}
        onFocus={() => refresh().catch(() => {})}
        onChange={onChange}
      >
        {models.map((name) => (
          <option key={name} value={name}>
            {name}
          </option>
        ))}
      </select>
      {error ? (
        <span className="text-destructive">{error}</span>
      ) : notice ? (
        <span className="text-muted-foreground">{notice}</span>
      ) : null}
    </label>
  );
}
