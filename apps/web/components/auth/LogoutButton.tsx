"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { logout } from "@/lib/auth";

export function LogoutButton() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  return (
    <button
      className="secondary"
      disabled={pending}
      onClick={async () => {
        setPending(true);
        try {
          await logout();
        } finally {
          router.replace("/login");
        }
      }}
    >
      {pending ? "Signing out…" : "Sign out"}
    </button>
  );
}
