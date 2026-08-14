import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { CoverageGapCallout } from "./CoverageGapCallout";
import type { ResultRow } from "../types";

function renderCallout(row: ResultRow) {
  return render(
    <MemoryRouter>
      <CoverageGapCallout row={row} />
    </MemoryRouter>
  );
}

describe("CoverageGapCallout", () => {
  it("renders nothing when the row carries no real gap fields", () => {
    const { container } = renderCallout({ scene: "S01" });
    expect(container).toBeEmptyDOMElement();
  });

  it("Add to shot list is a real link to the shot list, not a disabled stub", () => {
    renderCallout({ scene: "S01", no_tight_shot: ["MAN", "WOMAN"] });

    const link = screen.getByRole("link", { name: "Add to shot list" });
    expect(link).toHaveAttribute("href", "/shot-list");
    expect(link).not.toBeDisabled();
  });

  it("Open coverage grid links to the real coverage grid", () => {
    renderCallout({ scene: "S01", no_tight_shot: ["MAN"] });

    expect(screen.getByRole("link", { name: "Open coverage grid" })).toHaveAttribute("href", "/coverage");
  });
});
