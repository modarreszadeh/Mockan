import * as React from "react"

const MOBILE_BREAKPOINT = 768

/** Subscribes to a CSS media query. */
export function useMediaQuery(query: string): boolean {
  return React.useSyncExternalStore(
    (onChange) => {
      const mql = window.matchMedia(query)
      mql.addEventListener("change", onChange)
      return () => mql.removeEventListener("change", onChange)
    },
    () => window.matchMedia(query).matches,
    () => false,
  )
}

/** `< 768px`: the sidebar becomes a sheet and tables become stacked cards (prompt §8). */
export function useIsMobile() {
  return useMediaQuery(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
}
