"use client";

/*
 * Registration gateway. Collects identity, then offers passkey enrollment
 * as the primary credential; the password is the fallback. Inline
 * validation demonstrates the full error state cycle for the template.
 */

import { useState } from "react";
import Link from "next/link";
import { FingerprintSimple } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function RegisterPage() {
  const [form, setForm] = useState({ name: "", handle: "", email: "", password: "" });
  const [errors, setErrors] = useState<Partial<typeof form>>({});
  const [submitting, setSubmitting] = useState(false);

  function set(field: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [field]: e.target.value }));
  }

  function validate() {
    const next: Partial<typeof form> = {};
    if (form.name.trim().length < 2) next.name = "Enter your full name as enrolled.";
    if (!/^[a-z0-9_-]{3,20}$/.test(form.handle))
      next.handle = "3 to 20 characters: lowercase letters, digits, - or _.";
    if (!/^\S+@\S+\.\S+$/.test(form.email))
      next.email = "Use your school email so we can match your enrollment.";
    if (form.password.length < 12)
      next.password = "At least 12 characters. A passphrase works well.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;
    setSubmitting(true);
    /* Phase 2: POST /api/v1/auth/register, then WebAuthn create() ceremony. */
    setTimeout(() => setSubmitting(false), 900);
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Create your account</h1>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Your handle is public on leaderboards and writeups. Everything else
        stays between you and your teachers.
      </p>

      <form onSubmit={onSubmit} noValidate className="mt-8 space-y-5">
        <div className="grid gap-2">
          <Label htmlFor="name">Full name</Label>
          <Input
            id="name"
            autoComplete="name"
            value={form.name}
            onChange={set("name")}
            aria-invalid={!!errors.name}
            aria-describedby="name-error"
          />
          {errors.name && (
            <p id="name-error" className="text-[13px] text-danger">{errors.name}</p>
          )}
        </div>

        <div className="grid gap-2">
          <Label htmlFor="handle">Handle</Label>
          <Input
            id="handle"
            autoComplete="username"
            value={form.handle}
            onChange={set("handle")}
            aria-invalid={!!errors.handle}
            aria-describedby="handle-help handle-error"
          />
          {errors.handle ? (
            <p id="handle-error" className="text-[13px] text-danger">{errors.handle}</p>
          ) : (
            <p id="handle-help" className="text-[13px] text-muted">
              How you appear in the arena, like amihan or 0xkidlat.
            </p>
          )}
        </div>

        <div className="grid gap-2">
          <Label htmlFor="reg-email">School email</Label>
          <Input
            id="reg-email"
            type="email"
            autoComplete="email"
            value={form.email}
            onChange={set("email")}
            aria-invalid={!!errors.email}
            aria-describedby="reg-email-error"
          />
          {errors.email && (
            <p id="reg-email-error" className="text-[13px] text-danger">{errors.email}</p>
          )}
        </div>

        <div className="grid gap-2">
          <Label htmlFor="reg-password">Password</Label>
          <Input
            id="reg-password"
            type="password"
            autoComplete="new-password"
            value={form.password}
            onChange={set("password")}
            aria-invalid={!!errors.password}
            aria-describedby="reg-password-help reg-password-error"
          />
          {errors.password ? (
            <p id="reg-password-error" className="text-[13px] text-danger">
              {errors.password}
            </p>
          ) : (
            <p id="reg-password-help" className="text-[13px] text-muted">
              Fallback only. We will ask you to add a passkey next.
            </p>
          )}
        </div>

        <div aria-live="polite">
          {submitting && (
            <p className="text-[13px] text-muted">Creating your account...</p>
          )}
        </div>

        <Button type="submit" size="lg" className="w-full" disabled={submitting}>
          <FingerprintSimple size={19} weight="bold" />
          Continue to passkey setup
        </Button>
      </form>

      <p className="mt-8 text-sm text-muted">
        Already enrolled?{" "}
        <Link href="/login" className="font-medium text-accent hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
