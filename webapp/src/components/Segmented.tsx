import { haptic } from "../tg";

interface Option<T extends string> {
  value: T;
  label: string;
  tone?: "plus" | "minus";
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: Option<T>[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="segmented" role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={o.value === value}
          className={`segment ${o.value === value ? `active ${o.tone ?? ""}` : ""}`}
          onClick={() => {
            if (o.value !== value) haptic.select();
            onChange(o.value);
          }}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
