import { Edit3 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export default function EditableTitle({
  ariaLabel = "Edit title",
  className = "",
  fallback = "Untitled",
  onSave,
  showEditButton = true,
  value,
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(value || "");
  const inputRef = useRef(null);

  useEffect(() => {
    if (!isEditing) {
      setDraft(value || "");
    }
  }, [isEditing, value]);

  useEffect(() => {
    if (isEditing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [isEditing]);

  function startEdit(event) {
    event?.stopPropagation();
    setDraft(value || "");
    setIsEditing(true);
  }

  function save() {
    const nextValue = draft.trim() || fallback;
    setIsEditing(false);
    if (nextValue !== value) {
      onSave?.(nextValue);
    }
  }

  function cancel() {
    setDraft(value || "");
    setIsEditing(false);
  }

  if (isEditing) {
    return (
      <input
        ref={inputRef}
        aria-label={ariaLabel}
        className={`editable-title-input ${className}`}
        value={draft}
        onBlur={save}
        onChange={(event) => setDraft(event.target.value)}
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            save();
          }
          if (event.key === "Escape") {
            event.preventDefault();
            cancel();
          }
        }}
      />
    );
  }

  return (
    <span className={`editable-title ${className}`} onDoubleClick={startEdit}>
      <span>{value || fallback}</span>
      {showEditButton && (
        <button aria-label={ariaLabel} className="editable-title-button" type="button" onClick={startEdit}>
          <Edit3 size={13} />
        </button>
      )}
    </span>
  );
}
