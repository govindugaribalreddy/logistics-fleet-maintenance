import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import App from "./App";

vi.mock("./services/api", () => ({ getHealth: vi.fn().mockResolvedValue({ status: "ok" }) }));

test("renders the application shell", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: /logistics fleet maintenance/i })).toBeTruthy();
});
