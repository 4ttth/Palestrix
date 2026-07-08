"use client";

/*
 * Mobile navigation state, shared between the Topbar (hamburger trigger)
 * and the Sidebar (slide-over drawer below lg). Desktop never touches it.
 */

import { createContext, useContext, useState } from "react";

type Nav = {
  open: boolean;
  setOpen: (v: boolean) => void;
};

const NavContext = createContext<Nav | null>(null);

export function useNav(): Nav {
  const nav = useContext(NavContext);
  if (!nav) throw new Error("useNav outside NavProvider");
  return nav;
}

export function NavProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <NavContext.Provider value={{ open, setOpen }}>
      {children}
    </NavContext.Provider>
  );
}
