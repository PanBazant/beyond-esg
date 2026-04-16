// frontend/src/WizardBar.jsx
const STEPS = [
  { n: 1, label: "Start" },
  { n: 2, label: "Wartości" },
  { n: 3, label: "Parametry" },
  { n: 4, label: "Wyniki" },
];

export default function WizardBar({ step, maxStep, onStep }) {
  return (
    <nav className="wizard-bar">
      {STEPS.map(({ n, label }) => {
        const done = n < step;
        const active = n === step;
        const locked = n > maxStep;
        return (
          <button
            key={n}
            className={`wizard-step-btn${active ? " active" : ""}${done ? " done" : ""}${locked ? " locked" : ""}`}
            onClick={() => !locked && onStep(n)}
            disabled={locked}
            type="button"
          >
            <span className="wizard-step-num">{done ? "✓" : n}</span>
            <span className="wizard-step-label">{label}</span>
          </button>
        );
      })}
    </nav>
  );
}
