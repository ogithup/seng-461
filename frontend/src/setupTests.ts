import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";

// The open project id is kept in localStorage; don't let one test reopen another's project.
afterEach(() => {
  window.localStorage.clear();
});
