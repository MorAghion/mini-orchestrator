/** Test setup — runs once before each test file. */
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// React Testing Library renders into jsdom; we clean up between tests so state
// and DOM don't leak.
afterEach(() => {
  cleanup();
});
