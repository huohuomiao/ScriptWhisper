import { ChevronDown, Highlighter, PaintBucket, SlidersHorizontal } from "lucide-react";
import { useState } from "react";

import { highlightColors } from "../src/readingSettings.js";

export default function ReadingToolbar({
  compact = false,
  dropdown = false,
  settings,
  onClearHighlight,
  onFontSizeChange,
  onHighlightColorChange,
  onLineHeightChange,
  t = (key) => key,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const controls = (
    <ReadingControls
      settings={settings}
      onClearHighlight={onClearHighlight}
      onFontSizeChange={onFontSizeChange}
      onHighlightColorChange={onHighlightColorChange}
      onLineHeightChange={onLineHeightChange}
      t={t}
    />
  );

  if (dropdown) {
    return (
      <div className="reading-toolbar-dropdown" onBlur={() => window.setTimeout(() => setIsOpen(false), 120)}>
        <button
          aria-expanded={isOpen}
          aria-haspopup="true"
          className="reading-settings-trigger"
          type="button"
          onClick={() => setIsOpen((current) => !current)}
        >
          <SlidersHorizontal size={15} />
          {t("reading.aria")}
          <ChevronDown size={14} />
        </button>
        {isOpen && <div className="reading-toolbar-popover">{controls}</div>}
      </div>
    );
  }

  return (
    <section className={`reading-toolbar ${compact ? "compact" : ""}`} aria-label={t("reading.aria")}>
      {controls}
    </section>
  );
}

function ReadingControls({
  settings,
  onClearHighlight,
  onFontSizeChange,
  onHighlightColorChange,
  onLineHeightChange,
  t,
}) {
  return (
    <>
      <div className="toolbar-group">
        <span>{t("reading.fontSize")}</span>
        <SegmentedControl
          options={[
            ["small", t("reading.small")],
            ["medium", t("reading.medium")],
            ["large", t("reading.large")],
          ]}
          value={settings.fontSize}
          onChange={onFontSizeChange}
        />
      </div>
      <div className="toolbar-group">
        <span>{t("reading.lineHeight")}</span>
        <SegmentedControl
          options={[
            ["compact", t("reading.compact")],
            ["standard", t("reading.standard")],
            ["loose", t("reading.loose")],
          ]}
          value={settings.lineHeight}
          onChange={onLineHeightChange}
        />
      </div>
      <div className="toolbar-group">
        <span>{t("reading.highlightColor")}</span>
        <div className="color-swatches">
          {highlightColors.map((color) => (
            <button
              aria-label={t(`preview.color.${color.id}`)}
              className={`color-swatch ${settings.highlightColor === color.id ? "active" : ""}`}
              key={color.id}
              style={{ "--swatch-color": color.value }}
              title={t(`preview.color.${color.id}`)}
              type="button"
              onClick={() => onHighlightColorChange(color.id)}
            >
              <Highlighter size={14} />
            </button>
          ))}
        </div>
      </div>
      <button className="clear-highlight-button" type="button" onClick={onClearHighlight}>
        <PaintBucket size={15} />
        {t("preview.color.clear")}
      </button>
    </>
  );
}

function SegmentedControl({ onChange, options, value }) {
  return (
    <div className="segmented-control">
      {options.map(([id, label]) => (
        <button className={value === id ? "active" : ""} key={id} type="button" onClick={() => onChange(id)}>
          {label}
        </button>
      ))}
    </div>
  );
}
