"use client";

/*
 * Login gateway, live against POST /api/v1/auth/login and the WebAuthn
 * ceremony (lib/api/passkeys.ts). Passkey-first: the button runs
 * options -> navigator.credentials.get() -> verify and needs only the
 * email; the password form is the fallback. Full states: inline validation
 * errors, loading, and a contextual failure region (aria-live).
 */

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FingerprintSimple } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { api, ApiError, writeToken } from "@/lib/api/client";
import { passkeyLogin } from "@/lib/api/passkeys";
import type { TokenOut } from "@/lib/api/types";

/* useSearchParams (the ?next= redirect) requires a Suspense boundary when
 * the page is prerendered. */
export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<"password" | "passkey" | null>(null);

  function finish(token: TokenOut) {
    writeToken(token.access_token);
    const next = search.get("next");
    router.replace(next && next.startsWith("/") ? next : "/dashboard");
  }

  function fail(err: unknown, fallback: string) {
    if (err instanceof ApiError && err.status === 401) {
      setFailure("Those credentials didn't match. Check the email and try again.");
    } else if (err instanceof ApiError) {
      setFailure(err.message);
    } else if (err instanceof Error && err.name === "NotAllowedError") {
      setFailure("Passkey prompt was dismissed. Try again, or use your password.");
    } else {
      setFailure(fallback);
    }
  }

  async function onPasskey() {
    setFailure(null);
    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setErrors({ email: "Enter your email first so we can find your passkeys." });
      return;
    }
    setErrors({});
    setSubmitting("passkey");
    try {
      finish(await passkeyLogin(email));
    } catch (err) {
      fail(err, "Passkey sign-in failed. Use your password below.");
    } finally {
      setSubmitting(null);
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFailure(null);
    const next: typeof errors = {};
    if (!/^\S+@\S+\.\S+$/.test(email)) next.email = "Enter the email on your enrollment record.";
    if (password.length === 0) next.password = "Enter your password, or use a passkey instead.";
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    setSubmitting("password");
    try {
      finish(await api.post<TokenOut>("/api/v1/auth/login", { email, password }));
    } catch (err) {
      fail(err, "Sign-in failed. Try again in a moment.");
    } finally {
      setSubmitting(null);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Welcome back</h1>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Sign in to reach your labs, courses, and the arena.
      </p>

      <div className="mt-8 grid gap-2">
        <Label htmlFor="email">School email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="email webauthn"
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

      <Button
        className="mt-5 w-full"
        size="lg"
        onClick={onPasskey}
        disabled={submitting !== null}
      >
        <FingerprintSimple size={19} weight="bold" />
        {submitting === "passkey" ? "Waiting for your passkey..." : "Sign in with a passkey"}
      </Button>

      <div className="my-7 flex items-center gap-4">
        <Separator className="flex-1" />
        <span className="text-xs text-muted">or use your password</span>
        <Separator className="flex-1" />
      </div>

      <form onSubmit={onSubmit} noValidate className="space-y-5">
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
          {submitting === "password" && (
            <p className="text-[13px] text-muted">Checking your credentials...</p>
          )}
          {failure && <p className="text-[13px] text-danger">{failure}</p>}
        </div>

        <Button
          type="submit"
          variant="secondary"
          size="lg"
          className="w-full"
          disabled={submitting !== null}
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
