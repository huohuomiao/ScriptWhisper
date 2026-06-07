import { chromium } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";

const targetUrl = process.env.VISUAL_CHECK_URL || "http://127.0.0.1:5173";
const outputDir = process.env.VISUAL_CHECK_DIR || path.join("artifacts", "visual-check");
const headless = process.env.PW_HEADLESS !== "0";

const checks = [];
const issues = [];

async function main() {
  await fs.mkdir(outputDir, { recursive: true });
  const browser = await launchBrowser();
  const page = await browser.newPage({ viewport: { width: 1365, height: 900 } });

  try {
    await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 15000 });
    await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
    await expectVisibleText(page, ["ScriptWhisper"]);

    await clickAny(page, [
      () => page.getByRole("button", { exact: true, name: "预览" }),
      () => page.getByRole("button", { exact: true, name: "Preview" }),
    ]);
    await expectVisibleText(page, ["剧本正文", "Script Lines"]);

    await auditPreviewWorkspace(page);
    await page.screenshot({ fullPage: true, path: path.join(outputDir, "preview-workspace.png") });

    await auditProjectMenu(page);
    await page.screenshot({ fullPage: false, path: path.join(outputDir, "project-dialog.png") });

    await auditMobilePreview(browser);

    const unnamedButtons = await page.evaluate(() =>
      Array.from(document.querySelectorAll("button"))
        .filter((button) => {
          const rect = button.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        })
        .filter((button) => !button.textContent.trim() && !button.getAttribute("aria-label") && !button.getAttribute("title"))
        .map((button) => button.outerHTML.slice(0, 140)),
    );
    if (unnamedButtons.length) {
      issues.push({
        area: "accessibility",
        detail: `${unnamedButtons.length} visible icon button(s) have no aria-label/title.`,
        examples: unnamedButtons.slice(0, 3),
      });
    } else {
      checks.push("All visible icon-only buttons found in the audit path have labels.");
    }

    const report = {
      ok: issues.length === 0,
      targetUrl,
      screenshots: [
        path.join(outputDir, "preview-workspace.png"),
        path.join(outputDir, "project-dialog.png"),
        path.join(outputDir, "preview-mobile.png"),
      ],
      checks,
      issues,
    };
    console.log(JSON.stringify(report, null, 2));
    if (issues.length) {
      process.exitCode = 1;
    }
  } finally {
    await browser.close();
  }
}

async function auditMobilePreview(browser) {
  const page = await browser.newPage({ isMobile: true, viewport: { width: 390, height: 844 } });
  try {
    await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 15000 });
    await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
    await page.locator(".sidebar-nav-item").nth(2).click();
    await page.locator(".scene-detail-card").waitFor({ state: "visible", timeout: 5000 });
    const audit = await page.evaluate(() => ({
      horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 2,
      scriptHeaderHeight: Math.round(document.querySelector(".script-section-header")?.getBoundingClientRect().height || 0),
    }));
    if (audit.horizontalOverflow) {
      issues.push({ area: "mobile layout", detail: "Preview workspace has horizontal overflow at 390px viewport." });
    } else {
      checks.push("Preview workspace has no horizontal overflow at 390px viewport.");
    }
    if (audit.scriptHeaderHeight > 260) {
      issues.push({ area: "mobile layout", detail: `Script toolbar stack is too tall on mobile (${audit.scriptHeaderHeight}px).` });
    } else {
      checks.push(`Script toolbar remains usable on mobile (${audit.scriptHeaderHeight}px high).`);
    }
    await page.screenshot({ fullPage: true, path: path.join(outputDir, "preview-mobile.png") });
  } finally {
    await page.close();
  }
}

async function auditPreviewWorkspace(page) {
  const toolbarPlacement = await page.evaluate(() => ({
    topToolbarCount: document.querySelectorAll(".preview-command-bar .reading-toolbar").length,
    scriptToolbarCount: document.querySelectorAll(".script-section-header .reading-toolbar").length,
    horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 2,
  }));

  if (toolbarPlacement.topToolbarCount > 0) {
    issues.push({ area: "preview", detail: "Reading toolbar is still rendered in the top command bar." });
  } else {
    checks.push("Reading toolbar is no longer rendered in the top command bar.");
  }

  if (toolbarPlacement.scriptToolbarCount === 0) {
    issues.push({ area: "preview", detail: "Reading toolbar was not found in the script section header." });
  } else {
    checks.push("Reading toolbar is rendered beside script line controls.");
  }

  if (toolbarPlacement.horizontalOverflow) {
    issues.push({ area: "layout", detail: "Preview workspace has horizontal overflow at 1365px viewport." });
  } else {
    checks.push("Preview workspace has no horizontal overflow at 1365px viewport.");
  }

  const sourceSummary = page.locator(".source-evidence-summary p");
  await sourceSummary.waitFor({ state: "visible", timeout: 5000 });
  const summaryText = (await sourceSummary.innerText()).trim();
  if (summaryText.length > 240) {
    issues.push({ area: "source evidence", detail: `Source evidence summary is still too long (${summaryText.length} chars).` });
  } else {
    checks.push(`Source evidence summary is compact (${summaryText.length} chars).`);
  }

  await clickAny(page, [
    () => page.getByRole("button", { exact: true, name: "查看完整原文" }),
    () => page.getByRole("button", { exact: true, name: "View Full Source" }),
  ]);
  await page.locator(".source-evidence-reader").waitFor({ state: "visible", timeout: 5000 });
  checks.push("Full source drawer opens from the source evidence summary.");
}

async function auditProjectMenu(page) {
  await page.locator(".project-current-card").click();
  await clickAny(page, [
    () => page.getByRole("button", { exact: true, name: "新建项目" }),
    () => page.getByRole("button", { exact: true, name: "New Project" }),
  ]);
  await expectVisibleText(page, ["项目名称", "Project Name"]);
  checks.push("New project opens the naming dialog before creation.");
}

async function clickAny(page, locatorFactories) {
  const errors = [];
  for (const createLocator of locatorFactories) {
    const locator = createLocator();
    try {
      if ((await locator.count()) === 1 && (await locator.isVisible())) {
        await locator.click();
        return;
      }
    } catch (error) {
      errors.push(error.message);
    }
  }
  throw new Error(`No clickable locator matched. ${errors.join(" | ")}`);
}

async function expectVisibleText(page, candidates) {
  for (const text of candidates) {
    const locator = page.getByText(text, { exact: false });
    const count = await locator.count();
    for (let index = 0; index < count; index += 1) {
      const candidate = locator.nth(index);
      if (await candidate.isVisible().catch(() => false)) {
        return;
      }
    }
  }
  throw new Error(`Expected one of these texts to be visible: ${candidates.join(", ")}`);
}

async function launchBrowser() {
  const attempts = [
    process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : null,
    {},
    { channel: "msedge" },
    { channel: "chrome" },
  ].filter(Boolean);
  const errors = [];

  for (const options of attempts) {
    try {
      return await chromium.launch({ ...options, headless });
    } catch (error) {
      const label = options.channel || "bundled chromium";
      errors.push(`${label}: ${error.message.split("\n")[0]}`);
    }
  }

  throw new Error(
    [
      "Unable to launch a browser for UI verification.",
      "Run `npm run playwright:install`, or set PW_CHANNEL=msedge / PW_CHANNEL=chrome if a system browser is installed.",
      ...errors,
    ].join("\n"),
  );
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
