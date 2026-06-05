import { Highlighter, PaintBucket } from "lucide-react";

import { highlightColors } from "../src/readingSettings.js";

export default function ReadingToolbar({
  settings,
  onClearHighlight,
  onFontSizeChange,
  onHighlightColorChange,
  onLineHeightChange,
}) {
  return (
    <section className="reading-toolbar" aria-label="阅读设置">
      <div className="toolbar-group">
        <span>字号</span>
        <SegmentedControl
          options={[
            ["small", "小"],
            ["medium", "中"],
            ["large", "大"],
          ]}
          value={settings.fontSize}
          onChange={onFontSizeChange}
        />
      </div>
      <div className="toolbar-group">
        <span>行距</span>
        <SegmentedControl
          options={[
            ["compact", "紧凑"],
            ["standard", "标准"],
            ["loose", "宽松"],
          ]}
          value={settings.lineHeight}
          onChange={onLineHeightChange}
        />
      </div>
      <div className="toolbar-group">
        <span>标记颜色</span>
        <div className="color-swatches">
          {highlightColors.map((color) => (
            <button
              aria-label={color.label}
              className={`color-swatch ${settings.highlightColor === color.id ? "active" : ""}`}
              key={color.id}
              style={{ "--swatch-color": color.value }}
              title={color.label}
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
        清除标记
      </button>
    </section>
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
