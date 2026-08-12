import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Attribution } from "./Attribution";

describe("Attribution", () => {
  it("links to the source footage", () => {
    render(<Attribution />);
    const link = screen.getByRole("link", { name: "Tears of Steel" });
    expect(link).toHaveAttribute("href", "https://mango.blender.org");
  });
});
