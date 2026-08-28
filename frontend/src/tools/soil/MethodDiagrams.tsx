interface MethodDiagramProps {

  methodKey: string;
  coverM?: number;
  spreadFactor?: number;
}

export default function MethodDiagram({ methodKey, coverM = 1.0, spreadFactor = 1.15 }: MethodDiagramProps) {
  switch (methodKey) {
    case "boussinesq":
      return <BoussinesqDiagram coverM={coverM} />;
    case "boussinesq_point":
      return <PointLoadDiagram coverM={coverM} />;
    case "westergaard":
      return <WestergaardDiagram coverM={coverM} />;
    case "spread_2to1":
      return <TwoToOneMergedDiagram coverM={coverM} />;
    case "spread_superposed":
      return <TwoToOneSummedDiagram coverM={coverM} />;
    case "code_spread":
      return <CodeSpreadDiagram coverM={coverM} spreadFactor={spreadFactor} />;
    case "code_spread_superposed":
      return <TwoToOneSummedDiagram coverM={coverM} />;
    default:
      return null;
  }
}

export function BoussinesqDiagram({ coverM }: { coverM: number }) {
  return (
    <div style={{ padding: "8px 0", textAlign: "center" }}>
      <svg viewBox="0 0 460 160" width="100%" height="150" style={{ background: "#f8fafc", borderRadius: 6, border: "1px solid #e2e8f0" }}>
        {/* Surface Ground Line */}
        <line x1="20" y1="35" x2="440" y2="35" stroke="#475569" strokeWidth="2.5" strokeDasharray="none" />
        <text x="30" y="25" fill="#475569" fontSize="11" fontWeight="600">Ground Surface (z = 0)</text>

        {/* Surface Contact Patch B x L */}
        <rect x="180" y="27" width="100" height="15" fill="#3b82f6" fillOpacity="0.3" stroke="#1d4ed8" strokeWidth="2" rx="2" />
        <text x="230" y="20" fill="#1d4ed8" fontSize="11" fontWeight="700" textAnchor="middle">Contact Patch (q = Load / Area)</text>
        <text x="230" y="38" fill="#ffffff" fontSize="9.5" fontWeight="700" textAnchor="middle">q (kPa)</text>

        {/* Elastic Half-space Pressure Bulb Rays */}
        <path d="M 180 35 Q 150 90 230 130 Q 310 90 280 35 Z" fill="#93c5fd" fillOpacity="0.25" stroke="#2563eb" strokeWidth="1.5" strokeDasharray="4 3" />
        <path d="M 195 35 Q 175 80 230 110 Q 285 80 265 35 Z" fill="#60a5fa" fillOpacity="0.3" stroke="#1d4ed8" strokeWidth="1.5" />

        {/* Pipe Crown Level */}
        <line x1="40" y1="125" x2="420" y2="125" stroke="#ef4444" strokeWidth="2" strokeDasharray="5 4" />
        <text x="380" y="118" fill="#ef4444" fontSize="10.5" fontWeight="700">Crown Depth z = {coverM.toFixed(2)}m</text>

        {/* 4 Corner Superposition Annotations */}
        <line x1="230" y1="35" x2="230" y2="125" stroke="#94a3b8" strokeWidth="1" strokeDasharray="2 2" />
        <circle cx="230" cy="125" r="4" fill="#ef4444" stroke="#ffffff" strokeWidth="1.5" />

        {/* Explanatory Labels */}
        <text x="75" y="85" fill="#1e293b" fontSize="10" fontWeight="600">Newmark 4-Corner Superposition</text>
        <text x="75" y="98" fill="#64748b" fontSize="9">I = f(B/z, L/z) Influence Factors</text>

        <text x="300" y="85" fill="#1e293b" fontSize="10" fontWeight="600">Homogeneous Elastic Half-Space</text>
        <text x="300" y="98" fill="#64748b" fontSize="9">σ_z = q × Σ I (exact Boussinesq)</text>
      </svg>
    </div>
  );
}

export function PointLoadDiagram({ coverM }: { coverM: number }) {
  return (
    <div style={{ padding: "8px 0", textAlign: "center" }}>
      <svg viewBox="0 0 460 160" width="100%" height="150" style={{ background: "#f8fafc", borderRadius: 6, border: "1px solid #e2e8f0" }}>
        {/* Surface Ground Line */}
        <line x1="20" y1="35" x2="440" y2="35" stroke="#475569" strokeWidth="2.5" />
        <text x="30" y="25" fill="#475569" fontSize="11" fontWeight="600">Ground Surface</text>

        {/* Point Load Arrow */}
        <line x1="230" y1="5" x2="230" y2="35" stroke="#dc2626" strokeWidth="3.5" strokeLinecap="round" />
        <polygon points="224,27 230,37 236,27" fill="#dc2626" />
        <text x="242" y="20" fill="#dc2626" fontSize="12" fontWeight="800">P (Concentrated Load)</text>

        {/* Radial Rays */}
        <line x1="230" y1="35" x2="160" y2="125" stroke="#f87171" strokeWidth="1.5" strokeDasharray="3 3" />
        <line x1="230" y1="35" x2="300" y2="125" stroke="#f87171" strokeWidth="1.5" strokeDasharray="3 3" />
        <line x1="230" y1="35" x2="230" y2="125" stroke="#dc2626" strokeWidth="2" />

        {/* Crown Level Line */}
        <line x1="40" y1="125" x2="420" y2="125" stroke="#ef4444" strokeWidth="2" strokeDasharray="5 4" />
        <text x="380" y="118" fill="#ef4444" fontSize="10.5" fontWeight="700">z = {coverM.toFixed(2)}m</text>

        {/* Offset r indicator */}
        <line x1="230" y1="135" x2="300" y2="135" stroke="#475569" strokeWidth="1.5" />
        <text x="265" y="148" fill="#475569" fontSize="10" textAnchor="middle" fontWeight="600">Radius r</text>

        {/* Formula summary text */}
        <text x="70" y="80" fill="#991b1b" fontSize="10.5" fontWeight="700">σ_z = 3 P z³ / [2π (r² + z²)⁵/²]</text>
        <text x="70" y="95" fill="#7f1d1d" fontSize="9.5">Singular at z → 0 (Overstates shallow cover)</text>
      </svg>
    </div>
  );
}

export function WestergaardDiagram({ coverM }: { coverM: number }) {
  return (
    <div style={{ padding: "8px 0", textAlign: "center" }}>
      <svg viewBox="0 0 460 160" width="100%" height="150" style={{ background: "#f8fafc", borderRadius: 6, border: "1px solid #e2e8f0" }}>
        {/* Surface Ground Line */}
        <line x1="20" y1="35" x2="440" y2="35" stroke="#475569" strokeWidth="2.5" />

        {/* Surface Contact Patch */}
        <rect x="185" y="27" width="90" height="15" fill="#0891b2" fillOpacity="0.3" stroke="#0e7490" strokeWidth="2" rx="2" />
        <text x="230" y="22" fill="#0e7490" fontSize="11" fontWeight="700" textAnchor="middle">Contact Load q</text>

        {/* Horizontal Layer Reinforcement Lines (Westergaard Thin Lifts Model) */}
        <line x1="60" y1="55" x2="400" y2="55" stroke="#cbd5e1" strokeWidth="1.5" strokeDasharray="6 2" />
        <line x1="60" y1="75" x2="400" y2="75" stroke="#cbd5e1" strokeWidth="1.5" strokeDasharray="6 2" />
        <line x1="60" y1="95" x2="400" y2="95" stroke="#cbd5e1" strokeWidth="1.5" strokeDasharray="6 2" />
        <line x1="60" y1="115" x2="400" y2="115" stroke="#cbd5e1" strokeWidth="1.5" strokeDasharray="6 2" />

        {/* Lateral Strain Constraint Arrows */}
        <text x="70" y="50" fill="#0e7490" fontSize="9" fontWeight="700">Rigid horizontal sheets (ε_x = ε_y = 0)</text>

        {/* Westergaard Stress Cone */}
        <path d="M 185 35 L 140 125 L 320 125 L 275 35 Z" fill="#67e8f9" fillOpacity="0.25" stroke="#0891b2" strokeWidth="1.5" />

        {/* Crown Line */}
        <line x1="40" y1="125" x2="420" y2="125" stroke="#ef4444" strokeWidth="2" strokeDasharray="5 4" />
        <text x="380" y="118" fill="#ef4444" fontSize="10.5" fontWeight="700">z = {coverM.toFixed(2)}m</text>

        <text x="315" y="80" fill="#155e75" fontSize="10" fontWeight="700">Parameter η² = (1-2ν)/(2-2ν)</text>
        <text x="315" y="93" fill="#0e7490" fontSize="9">Thinly layered / varved clay model</text>
      </svg>
    </div>
  );
}

export function TwoToOneMergedDiagram({ coverM }: { coverM: number }) {
  return (
    <div style={{ padding: "8px 0", textAlign: "center" }}>
      <svg viewBox="0 0 460 160" width="100%" height="150" style={{ background: "#f8fafc", borderRadius: 6, border: "1px solid #e2e8f0" }}>
        {/* Ground Surface */}
        <line x1="20" y1="35" x2="440" y2="35" stroke="#475569" strokeWidth="2.5" />

        {/* Initial Contact Area (B x L) */}
        <rect x="190" y="27" width="80" height="15" fill="#d97706" fillOpacity="0.3" stroke="#b45309" strokeWidth="2" rx="2" />
        <text x="230" y="20" fill="#b45309" fontSize="11" fontWeight="700" textAnchor="middle">Contact B × L (Load Q)</text>

        {/* 2:1 Spread Lines (0.5z expansion on each side) */}
        <line x1="190" y1="35" x2="140" y2="125" stroke="#d97706" strokeWidth="2" />
        <line x1="270" y1="35" x2="320" y2="125" stroke="#d97706" strokeWidth="2" />

        <path d="M 190 35 L 140 125 L 320 125 L 270 35 Z" fill="#fcd34d" fillOpacity="0.3" />

        {/* Slope indicators 2:1 */}
        <text x="145" y="75" fill="#b45309" fontSize="9.5" fontWeight="700">1 : 0.5 slope (z/2)</text>
        <text x="285" y="75" fill="#b45309" fontSize="9.5" fontWeight="700">1 : 0.5 slope (z/2)</text>

        {/* Expanded Area at depth z */}
        <line x1="140" y1="125" x2="320" y2="125" stroke="#b45309" strokeWidth="3" />
        <text x="230" y="142" fill="#b45309" fontSize="10.5" fontWeight="700" textAnchor="middle">Grown Area (B + z) × (L + z)</text>

        {/* Crown Line */}
        <line x1="40" y1="125" x2="420" y2="125" stroke="#ef4444" strokeWidth="1.5" strokeDasharray="5 4" />
        <text x="380" y="118" fill="#ef4444" fontSize="10.5" fontWeight="700">z = {coverM.toFixed(2)}m</text>

        <text x="40" y="85" fill="#92400e" fontSize="10" fontWeight="700">Merged Overlap Rule</text>
        <text x="40" y="98" fill="#b45309" fontSize="9">σ_z = Q / [(B+z)(L+z)]</text>
      </svg>
    </div>
  );
}

export function TwoToOneSummedDiagram({ coverM }: { coverM: number }) {
  return (
    <div style={{ padding: "8px 0", textAlign: "center" }}>
      <svg viewBox="0 0 460 160" width="100%" height="150" style={{ background: "#f8fafc", borderRadius: 6, border: "1px solid #e2e8f0" }}>
        {/* Ground Surface */}
        <line x1="20" y1="35" x2="440" y2="35" stroke="#475569" strokeWidth="2.5" />

        {/* Two Separate Contact Patches (Tyres/Tracks) */}
        <rect x="140" y="27" width="50" height="15" fill="#7c3aed" fillOpacity="0.3" stroke="#6d28d9" strokeWidth="2" rx="2" />
        <rect x="270" y="27" width="50" height="15" fill="#7c3aed" fillOpacity="0.3" stroke="#6d28d9" strokeWidth="2" rx="2" />
        <text x="165" y="20" fill="#6d28d9" fontSize="10" fontWeight="700" textAnchor="middle">Tyre 1</text>
        <text x="295" y="20" fill="#6d28d9" fontSize="10" fontWeight="700" textAnchor="middle">Tyre 2</text>

        {/* Tyre 1 Spread Pyramid */}
        <path d="M 140 35 L 100 125 L 230 125 L 190 35 Z" fill="#c4b5fd" fillOpacity="0.3" stroke="#7c3aed" strokeWidth="1.5" strokeDasharray="3 3" />

        {/* Tyre 2 Spread Pyramid */}
        <path d="M 270 35 L 230 125 L 360 125 L 320 35 Z" fill="#c4b5fd" fillOpacity="0.3" stroke="#7c3aed" strokeWidth="1.5" strokeDasharray="3 3" />

        {/* Overlap Zone */}
        <polygon points="230,125 210,80 230,125" fill="#a78bfa" fillOpacity="0.5" />

        {/* Crown Evaluation Point */}
        <line x1="40" y1="125" x2="420" y2="125" stroke="#ef4444" strokeWidth="2" strokeDasharray="5 4" />
        <circle cx="230" cy="125" r="4" fill="#6d28d9" stroke="#ffffff" strokeWidth="1.5" />
        <text x="230" y="145" fill="#6d28d9" fontSize="10.5" fontWeight="700" textAnchor="middle">Evaluation Point (Sum of Reaching Footprints)</text>
        <text x="380" y="118" fill="#ef4444" fontSize="10.5" fontWeight="700">z = {coverM.toFixed(2)}m</text>

        <text x="30" y="75" fill="#5b21b6" fontSize="10" fontWeight="700">Individual 2:1 Spread</text>
        <text x="30" y="88" fill="#6d28d9" fontSize="9">Summed at point of interest</text>
      </svg>
    </div>
  );
}

export function CodeSpreadDiagram({ coverM, spreadFactor }: { coverM: number; spreadFactor: number }) {
  return (
    <div style={{ padding: "8px 0", textAlign: "center" }}>
      <svg viewBox="0 0 460 160" width="100%" height="150" style={{ background: "#f8fafc", borderRadius: 6, border: "1px solid #e2e8f0" }}>
        {/* Ground Surface */}
        <line x1="20" y1="35" x2="440" y2="35" stroke="#475569" strokeWidth="2.5" />

        {/* Surface Contact Patch */}
        <rect x="180" y="27" width="100" height="15" fill="#475569" fillOpacity="0.3" stroke="#334155" strokeWidth="2" rx="2" />
        <text x="230" y="20" fill="#334155" fontSize="11" fontWeight="700" textAnchor="middle">Wheel / Track Footprint</text>

        {/* Code Spread Slope (f * z expansion) */}
        <path d="M 180 35 L 120 125 L 340 125 L 280 35 Z" fill="#cbd5e1" fillOpacity="0.4" stroke="#475569" strokeWidth="2" />

        <text x="130" y="75" fill="#334155" fontSize="10" fontWeight="700">Spread Slope f = {spreadFactor.toFixed(2)}</text>
        <text x="300" y="75" fill="#334155" fontSize="10" fontWeight="700">Spread Slope f = {spreadFactor.toFixed(2)}</text>

        {/* Crown Line */}
        <line x1="40" y1="125" x2="420" y2="125" stroke="#ef4444" strokeWidth="2" strokeDasharray="5 4" />
        <text x="380" y="118" fill="#ef4444" fontSize="10.5" fontWeight="700">z = {coverM.toFixed(2)}m</text>

        {/* Expanded Base Dimensions */}
        <line x1="120" y1="125" x2="340" y2="125" stroke="#1e293b" strokeWidth="3" />
        <text x="230" y="142" fill="#1e293b" fontSize="10.5" fontWeight="700" textAnchor="middle">Expanded Area: (B + {spreadFactor.toFixed(2)}z) × (L + {spreadFactor.toFixed(2)}z)</text>

        <text x="40" y="85" fill="#1e293b" fontSize="10" fontWeight="700">Code Distribution Factor (LLDF)</text>
        <text x="40" y="98" fill="#475569" fontSize="9">AASHTO / CSA S6 Live-Load Spread</text>
      </svg>
    </div>
  );
}
