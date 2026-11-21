import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";

// The open project id is kept in localStorage; don't let one test reopen another's project.
// (live.smoke.test.ts runs in Node, where there is no window.)
afterEach(() => {
  if (typeof window !== "undefined") window.localStorage.clear();
});
