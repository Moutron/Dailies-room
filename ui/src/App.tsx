import { useState } from "react";
import { Attribution } from "./components/Attribution";
import { ClipPlayer } from "./components/ClipPlayer";
import { SessionView } from "./components/SessionView";
import type { ActiveClip } from "./types";

export default function App() {
  const [active, setActive] = useState<ActiveClip | null>(null);

  function onSeek(clipId: string, seconds: number) {
    setActive((prev) => ({
      clipId,
      seekSeconds: seconds,
      nonce: (prev?.nonce ?? 0) + 1,
    }));
  }

  return (
    <div className="app">
      <header className="app__header">
        <h1>The Dailies Room</h1>
      </header>
      <main className="app__main">
        <SessionView onSeek={onSeek} />
        <ClipPlayer active={active} />
      </main>
      <Attribution />
    </div>
  );
}
