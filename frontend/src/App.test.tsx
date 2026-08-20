import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";
import { AppQueryProvider } from "./status/QueryProvider";

describe("App", () => {
  it("renders the MANDATE heading", () => {
    render(
      <AppQueryProvider>
        <App />
      </AppQueryProvider>,
    );
    expect(screen.getByRole("heading", { name: "MANDATE" })).toBeInTheDocument();
  });
});
