"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { register } from "@/lib/auth";

export function RegisterForm() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const data = new FormData(event.currentTarget);
    const password = String(data.get("password"));
    if (password !== String(data.get("confirmPassword"))) {
      setError("Passwords do not match.");
      return;
    }
    setPending(true);
    try {
      await register(String(data.get("email")), password);
      router.replace("/dashboard");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Registration failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="form-card">
      <label htmlFor="email">Email</label>
      <input id="email" name="email" type="email" autoComplete="email" required />
      <label htmlFor="password">Password</label>
      <input id="password" name="password" type="password" minLength={12} autoComplete="new-password" required />
      <p className="hint">Use at least 12 characters.</p>
      <label htmlFor="confirmPassword">Confirm password</label>
      <input id="confirmPassword" name="confirmPassword" type="password" minLength={12} autoComplete="new-password" required />
      {error && <p className="error" role="alert">{error}</p>}
      <button disabled={pending}>{pending ? "Creating account…" : "Create account"}</button>
    </form>
  );
}
