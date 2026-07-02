"use client";

/*
 * Login gateway. Passkey-first (WebAuthn via SimpleWebAuthn on the client,
 * py_webauthn on the API from Phase 2), password as fallback. The form
 * ships full states: inline validation errors, loading, and a contextual
 * failure message region (aria-live).
 */

import { useState } from "react";
import Link from "next/link";
import { FingerprintSimple } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [submitting, setSubmitting] = useState(false);

  function validate() {
    const next: typeof errors = {};
    if (!/^\S+@\S+\.\S+$/.test(email)) next.email = "Enter the email on your enrollment record.";
    if (password.length === 0) next.password = "Enter your password, or use a passkey instead.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;
    setSubmitting(true);
    /* Phase 2: POST /api/v1/auth/login, then WebAuthn ceremony if enrolled. */
    setTimeout(() => setSubmitting(false), 900);
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Welcome back</h1>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Sign in to reach your labs, courses, and the arena.
      </p>

      <Button
        className="mt-8 w-full"
        size="lg"
        onClick={() => {
          /* Phase 2: navigator.credentials.get() with options from /api/v1/auth/webauthn/options */
        }}
      >
        <FingerprintSimple size={19} weight="bold" />
        Sign in with a passkey
      </Button>

      <div className="my-7 flex items-center gap-4">
        <Separator className="flex-1" />
        <span className="text-xs text-muted">or use your password</span>
        <Separator className="flex-1" />
      </div>

      <form onSubmit={onSubmit} noValidate className="space-y-5">
        <div className="grid gap-2">
          <Label htmlFor="email">School email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={!!errors.email}
            aria-describedby="email-help email-error"
          />
          {errors.email ? (
            <p id="email-error" className="text-[13px] text-danger">
              {errors.email}
            </p>
          ) : (
            <p id="email-help" className="text-[13px] text-muted">
              The address your institution registered for you.
            </p>
          )}
        </div>

        <div className="grid gap-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="password">Password</Label>
            <Link href="#" className="text-[13px] text-accent hover:underline">
              Forgot it?
            </Link>
          </div>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={!!errors.password}
            aria-describedby="password-error"
          />
          {errors.password && (
            <p id="password-error" className="text-[13px] text-danger">
              {errors.password}
            </p>
          )}
        </div>

        <div aria-live="polite">
          {submitting && (
            <p className="text-[13px] text-muted">Checking your credentials...</p>
          )}
        </div>

        <Button
          type="submit"
          variant="secondary"
          size="lg"
          className="w-full"
          disabled={submitting}
        >
          Sign in with password
        </Button>
      </form>

      <p className="mt-8 text-sm text-muted">
        New here?{" "}
        <Link href="/register" className="font-medium text-accent hover:underline">
          Create your account
        </Link>
      </p>
    </div>
  );
}
