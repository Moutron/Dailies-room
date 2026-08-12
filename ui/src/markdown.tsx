import type { ReactNode } from "react";

/** The agent's prose comes back with light markdown (**bold**, "* " bullets).
 * This is not a general renderer — just enough to keep that readable instead
 * of showing raw asterisks in a UI that otherwise has no markdown surface. */
function renderInline(text: string, key: number): ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <span key={key}>
      {parts.map((part, i) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={i}>{part.slice(2, -2)}</strong>
        ) : (
          part
        )
      )}
    </span>
  );
}

export function renderAgentText(text: string): ReactNode[] {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let list: string[] = [];

  const flushList = () => {
    if (list.length === 0) return;
    blocks.push(
      <ul key={`ul-${blocks.length}`}>
        {list.map((item, i) => (
          <li key={i}>{renderInline(item, i)}</li>
        ))}
      </ul>
    );
    list = [];
  };

  lines.forEach((line, i) => {
    const bullet = line.match(/^\s*[*-]\s+(.*)/);
    if (bullet) {
      list.push(bullet[1]);
      return;
    }
    flushList();
    if (line.trim()) blocks.push(<p key={`p-${i}`}>{renderInline(line, i)}</p>);
  });
  flushList();

  return blocks;
}
