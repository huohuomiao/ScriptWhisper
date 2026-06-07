import { useEffect, useState } from "react";

const STORAGE_KEY = "scriptwhisper.readingSettings";

export const highlightColors = [
  { id: "yellow", label: "黄色", value: "#f6c453" },
  { id: "blue", label: "蓝色", value: "#4c7dff" },
  { id: "green", label: "绿色", value: "#35b779" },
  { id: "red", label: "红色", value: "#ef6a5b" },
  { id: "purple", label: "紫色", value: "#8b5cf6" },
];

const defaultSettings = {
  fontSize: "medium",
  lineHeight: "standard",
  highlightColor: "yellow",
};

export function useReadingSettings() {
  const [settings, setSettings] = useState(loadReadingSettings);

  useEffect(() => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        fontSize: settings.fontSize,
        lineHeight: settings.lineHeight,
      }),
    );
  }, [settings.fontSize, settings.lineHeight]);

  return {
    settings,
    setFontSize: (fontSize) => setSettings((current) => ({ ...current, fontSize })),
    setLineHeight: (lineHeight) => setSettings((current) => ({ ...current, lineHeight })),
    setHighlightColor: (highlightColor) => setSettings((current) => ({ ...current, highlightColor })),
  };
}

export function readingClassName(settings) {
  return `reading-surface reading-font-${settings.fontSize} reading-line-${settings.lineHeight}`;
}

export function selectedHighlightValue(settings) {
  return highlightColors.find((color) => color.id === settings.highlightColor)?.id || highlightColors[0].id;
}

function loadReadingSettings() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}");
    return {
      ...defaultSettings,
      fontSize: saved.fontSize || defaultSettings.fontSize,
      lineHeight: saved.lineHeight || defaultSettings.lineHeight,
    };
  } catch {
    return defaultSettings;
  }
}
