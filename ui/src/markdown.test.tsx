import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { renderAgentText } from "./markdown";

describe("renderAgentText", () => {
  it("renders plain paragraphs", () => {
    const { container } = render(<>{renderAgentText("Hello there.")}</>);
    expect(container.querySelectorAll("p")).toHaveLength(1);
    expect(container.textContent).toBe("Hello there.");
  });

  it("bolds **text** inline", () => {
    const { container } = render(<>{renderAgentText("This is **important**.")}</>);
    const strong = container.querySelector("strong");
    expect(strong).not.toBeNull();
    expect(strong?.textContent).toBe("important");
  });

  it("groups consecutive bullet lines into one list", () => {
    const { container } = render(<>{renderAgentText("* one\n* two\n- three")}</>);
    const lists = container.querySelectorAll("ul");
    expect(lists).toHaveLength(1);
    expect(lists[0].querySelectorAll("li")).toHaveLength(3);
  });

  it("flushes a list before starting a new paragraph", () => {
    const { container } = render(<>{renderAgentText("* one\nnot a bullet")}</>);
    expect(container.querySelectorAll("ul")).toHaveLength(1);
    expect(container.querySelectorAll("p")).toHaveLength(1);
  });

  it("skips blank lines", () => {
    const { container } = render(<>{renderAgentText("first\n\nsecond")}</>);
    expect(container.querySelectorAll("p")).toHaveLength(2);
  });
});
