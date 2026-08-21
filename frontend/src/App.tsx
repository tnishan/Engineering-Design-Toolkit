import { useCallback, useState } from "react";
import BeamDesign from "./tools/beam/BeamDesign";
import PostDesign, { type PostSeed } from "./tools/post/PostDesign";
import SoilPressure from "./tools/soil/SoilPressure";
import "./styles/global.css";

type Tab = "beam" | "post" | "soil";

const TABS: { key: Tab; label: string; blurb: string }[] = [
  { key: "beam", label: "Beam design", blurb: "Continuous wood beams — CSA O86-19" },
  { key: "post", label: "Post design", blurb: "Posts and columns — CSA O86-19 Cl. 6.5.6" },
  { key: "soil", label: "Pipe surcharge", blurb: "Plant loads on buried pipes — Boussinesq" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("beam");
  const [postSeed, setPostSeed] = useState<PostSeed | null>(null);

  // A beam support reaction can be carried straight into the post tab.
  const sendReactionToPost = useCallback((seed: PostSeed) => {
    setPostSeed(seed);
    setTab("post");
    window.scrollTo({ top: 0 });
  }, []);

  return (
    <>
      <header className="top">
        <h1>Engineering Design Toolkit</h1>
        <p>
          OBC 2024 / NBC 2020 / CSA O86-19. Design aid only — the engineer of record
          verifies all input, material properties and results.
        </p>
        <nav className="tabs" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              className={tab === t.key ? "tab on" : "tab"}
              onClick={() => setTab(t.key)}
            >
              {t.label}
              <span>{t.blurb}</span>
            </button>
          ))}
        </nav>
      </header>

      {tab === "beam" && <BeamDesign onDesignPostFor={sendReactionToPost} />}
      {tab === "post" && (
        <PostDesign seed={postSeed} onSeedConsumed={() => setPostSeed(null)} />
      )}
      {tab === "soil" && <SoilPressure />}
    </>
  );
}
