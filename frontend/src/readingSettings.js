import { useEffect, useState } from "react";

const STORAGE_KEY = "scriptwhisper.readingSettings";

export const highlightColors = [
  { id: "yellow", label: "黄色", value: "#fff3a3" },
  { id: "blue", label: "蓝色", value: "#cfe8ff" },
  { id: "green", label: "绿色", value: "#d8f5d2" },
  { id: "red", label: "红色", value: "#ffd8d2" },
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
  return highlightColors.find((color) => color.id === settings.highlightColor)?.value || highlightColors[0].value;
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
