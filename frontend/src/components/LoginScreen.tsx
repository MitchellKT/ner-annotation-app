import { useState } from "react";
import { useStore } from "../store";

/**
 * First screen, always shown on open: pick the annotator. The username scopes
 * all annotations and the source selection server-side, so signing back in
 * with the same name reloads exactly that person's work. The field starts
 * empty every time — each session names its annotator explicitly.
 */
export function LoginScreen() {
  const login = useStore((s) => s.login);
  const loading = useStore((s) => s.loading);
  const error = useStore((s) => s.error);
  const [name, setName] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (name.trim()) void login(name);
  }

  return (
    <div className="gate">
      <form className="gate-card" onSubmit={submit}>
        <h1 className="gate-title">NER Entity Annotator</h1>
        <p className="gate-sub">Enter your annotator name to start or resume your work.</p>
        <label className="gate-label" htmlFor="username">
          Annotator name
        </label>
        <input
          id="username"
          className="gate-input"
          autoFocus
          value={name}
          placeholder="e.g. alice"
          onChange={(e) => setName(e.target.value)}
        />
        {error && <div className="gate-error">{error}</div>}
        <button className="primary gate-btn" type="submit" disabled={!name.trim() || loading}>
          {loading ? "Loading…" : "Continue"}
        </button>
      </form>
    </div>
  );
}
