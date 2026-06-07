import { Check, ChevronDown, Languages } from "lucide-react";
import { useState } from "react";

export default function LanguageSelect({ label, onChange, options, value }) {
  const [isOpen, setIsOpen] = useState(false);
  const selected = options.find((option) => option.id === value) || options[0];

  function selectLanguage(nextValue) {
    onChange(nextValue);
    setIsOpen(false);
  }

  return (
    <div className="language-select" onBlur={() => window.setTimeout(() => setIsOpen(false), 120)}>
      <button
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        className="language-select-trigger"
        type="button"
        onClick={() => setIsOpen((current) => !current)}
      >
        <Languages size={14} />
        <span className="language-select-label">{label}</span>
        <strong>{selected.label}</strong>
        <ChevronDown size={14} />
      </button>
      {isOpen && (
        <div className="language-select-menu" role="listbox" aria-label={label}>
          {options.map((option) => (
            <button
              className={option.id === value ? "selected" : ""}
              key={option.id}
              role="option"
              aria-selected={option.id === value}
              type="button"
              onClick={() => selectLanguage(option.id)}
            >
              <span>{option.label}</span>
              {option.id === value && <Check size={14} />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
