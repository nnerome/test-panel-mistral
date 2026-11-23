import { describe, expect, test } from "bun:test";
import { cleanup, render, screen } from "@testing-library/react";

import { renderMarkdown } from "./markdown";

describe("renderMarkdown", () => {
  test("renders bold, italic, inline code, citation badges, lists and paragraphs", () => {
    const { container, unmount } = render(
      <div>{renderMarkdown("Salut **gras** et *italique* et `code` et [1] (knowledge/fr/x.md)\n\n- item A\n- item B")}</div>,
    );
    expect(container.querySelector("strong")?.textContent).toBe("gras");
    expect(container.querySelector("em")?.textContent).toBe("italique");
    expect(container.querySelector("code")?.textContent).toBe("code");
    expect(container.querySelector("sup")?.textContent).toBe("[1]");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelectorAll("p")).toHaveLength(1);
    unmount();
  });

  test("raw HTML stays literal text (no injection, no innerHTML)", () => {
    const { container, unmount } = render(<div>{renderMarkdown("<img src=x onerror=alert(1)> **ok**")}</div>);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText(/<img src=x onerror=alert\(1\)>/)).toBeTruthy();
    expect(container.querySelector("strong")?.textContent).toBe("ok");
    unmount();
  });

  test("line breaks inside a paragraph become <br>", () => {
    const { container, unmount } = render(<div>{renderMarkdown("ligne 1\nligne 2")}</div>);
    expect(container.querySelectorAll("br")).toHaveLength(1);
    cleanup();
    unmount();
  });
});
