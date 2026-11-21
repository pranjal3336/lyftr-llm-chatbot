export const SIMULATIONS = [
  { label: "Failure simulation: Off", value: "" },
  { label: "key_1=429", value: "key_1=429" },
  { label: "key_1=500", value: "key_1=500" },
  { label: "key_1=429,key_2=500", value: "key_1=429,key_2=500" },
  { label: "*=429 (all keys fail)", value: "*=429" },
];

interface Props {
  sessionId: string;
  simulation: string;
  onSimulationChange: (value: string) => void;
  onNewSession: () => void;
}

export default function Header({ sessionId, simulation, onSimulationChange, onNewSession }: Props) {
  return (
    <header className="header">
      <div>
        <h1>Lyftr AI Chatbot</h1>
        <span className="session-id">session: {sessionId}</span>
      </div>
      <div className="header-controls">
        <select
          aria-label="Failure simulation"
          value={simulation}
          onChange={(e) => onSimulationChange(e.target.value)}
        >
          {SIMULATIONS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <button type="button" className="secondary" onClick={onNewSession}>
          New Session
        </button>
      </div>
    </header>
  );
}
